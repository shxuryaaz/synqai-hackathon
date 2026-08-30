"""The only door to OpenAI. Cached, temperature 0, PII firewall, never raises.
Every call: hash(model+prompt+input) -> llm_cache.sqlite. Cache hit makes no API call. Failure returns None and
the caller falls back to its regex/template path and audits the degradation.
Set MERIDIAN_LLM_FAKE=<counter file> to use a deterministic-per-call fake (tests). Unset OPENAI_API_KEY to force fallback.
"""
import hashlib, json, os, re, sqlite3
from pathlib import Path
from dotenv import load_dotenv
from common import ROOT, WORK, has_pii, mask

load_dotenv(ROOT / ".env")
EXTRACT_MODEL, DRAFT_MODEL = "gpt-4o-mini", "gpt-4o"
CACHE = WORK / "llm_cache.sqlite"
last_error = None


def _cache():
    con = sqlite3.connect(CACHE)
    con.execute("create table if not exists cache(key primary key, model, response)")
    return con


def _call(model, system, user):
    fake = os.environ.get("MERIDIAN_LLM_FAKE")
    if fake:
        n = int(Path(fake).read_text() or 0) + 1 if Path(fake).exists() else 1
        Path(fake).write_text(str(n))
        if "field mapping" in system:   # ponytail: name heuristics so tests never need the network
            cols = json.loads(user)["unknown"]
            guess = lambda c: next((t for pat, t in [("reg|plate", "vehicle"), ("km|dist", "km_from_origin_hub"), ("ref|ticket", "ticket_id"), ("log|creat|date|time", "created_at"), ("pilot|driver", "driver_id"), ("base|hub", "origin_hub"), ("going|dest|to", "destination"), ("fault|issue|prob", "issue"), ("urg|sev|prio", "severity"), ("cust|client", "client"), ("state|status", "status")] if re.search(pat, c.lower())), None)
            return json.dumps({"mapping": {c: {"target": guess(c), "confidence": 0.9 if guess(c) else 0.2} for c in cols}})
        return json.dumps({"kinds": ["repaired"]}) if "JSON" in system else f"FAKE DRAFT #{n}"
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("no OPENAI_API_KEY")
    from openai import OpenAI
    client = OpenAI(timeout=20, max_retries=1)
    r = client.chat.completions.create(model=model, temperature=0, seed=7,
                                       messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content


def ask(model, system, user):
    """Cached, firewalled call. Returns text or None (caller must fall back)."""
    global last_error
    if has_pii(system) or has_pii(user):
        last_error = "refused: input matches a PII pattern"
        return None
    key = hashlib.sha256(f"{model}\n{system}\n{user}".encode()).hexdigest()
    con = _cache()
    row = con.execute("select response from cache where key=?", (key,)).fetchone()
    if row:
        return row[0]
    try:
        out = mask(_call(model, system, user))
    except Exception as e:
        last_error = f"{type(e).__name__}: {str(e)[:120]}"
        return None
    con.execute("insert or replace into cache values(?,?,?)", (key, model, out))
    con.commit()
    return out


# ---- the four jobs -------------------------------------------------------------------------------
EXTRACT_SYS = ("You read Hinglish truck maintenance notes. Return JSON only: {\"kinds\": [...]} with any of "
               "brake_work, jugaad, permanent_fix_pending, replaced, repaired, service, other. jugaad = temporary fix. "
               "permanent_fix_pending = permanent repair still owed.")


def extract_note(note):
    out = ask(EXTRACT_MODEL, EXTRACT_SYS, note)
    try:
        kinds = json.loads(out.strip().strip("`").removeprefix("json"))["kinds"]
        return [k for k in kinds if isinstance(k, str)] or None
    except Exception:
        return None


DRAFT_SYS = ("You write short, plain client notices for Meridian Freight, a North India trucking company. "
             "Use only the facts given. Never invent times, names or numbers. No phone numbers. Plain English, "
             "no marketing tone, under 120 words. Sign off as 'Meridian Freight, <hub> desk'.")


def draft(facts):
    return ask(DRAFT_MODEL, DRAFT_SYS, json.dumps(facts, ensure_ascii=False, sort_keys=True))


QUERY_SYS = ("Answer the question using ONLY the retrieved rows below. Cite the source of every fact in brackets. "
             "If the rows do not answer the question, reply exactly: insufficient data.")


def grounded_answer(question, rows):
    if not rows:
        return None
    ctx = "\n".join(f"[{ref}] {text}" for ref, text in rows)
    return ask(EXTRACT_MODEL, QUERY_SYS, f"Question: {question}\n\nRetrieved rows:\n{ctx}")


MATCH_SYS = "Map the given name to exactly one of the canonical names, or NONE. Reply with the canonical name only."


def propose_match(name, canonicals):
    out = ask(EXTRACT_MODEL, MATCH_SYS, f"Name: {name}\nCanonical: {', '.join(canonicals)}")
    return out.strip() if out and out.strip() in canonicals else None


MAP_SYS = ("You propose a field mapping from a client's breakdown-ticket file to our ticket schema. Return JSON only: "
           "{\"mapping\": {\"<column>\": {\"target\": <schema field or null>, \"confidence\": 0..1}}}. "
           "Schema fields: ticket_id (ticket reference), created_at (when the breakdown was logged), vehicle (truck registration plate), "
           "driver_id (driver code like DRV-001), origin_hub (the hub/base/depot the truck left from, a city name), km_from_origin_hub (distance from that hub in km), "
           "destination (city the truck was going to), issue (free-text fault description), severity (urgency/priority), client (customer name), status (ticket state), "
           "resolution_note. Use the sample values to decide. Map every unknown column; each schema field at most once. Use null only when nothing fits.")


def propose_mapping(unknown, samples, targets):
    """Column names + 2 masked sample rows -> {col: {target, confidence}} or None when the model is unavailable."""
    out = ask(DRAFT_MODEL, MAP_SYS, json.dumps({"unknown": unknown, "schema": targets, "samples": samples}, ensure_ascii=False, sort_keys=True))
    try:
        m = json.loads(out.strip().strip("`").removeprefix("json"))["mapping"]
        return {c: {"target": (v.get("target") if v.get("target") in targets else None), "confidence": float(v.get("confidence") or 0)} for c, v in m.items() if c in unknown}
    except Exception:
        return None
