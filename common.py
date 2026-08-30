"""Shared bits: paths, PII masking, canonical ids, sqlite handle."""
import hashlib, json, os, re, sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
BUNDLE = ROOT / "candidate_bundle"
WORK = Path(os.environ.get("MERIDIAN_WORK", ROOT))  # tests point this at a temp dir
DB = WORK / "store.sqlite"
OUT = WORK / "outputs"
AUDIT = WORK / "audit"
LOGS = WORK / "logs"

# PII patterns. Lookarounds instead of \b so 10-digit runs inside long ids (trip ids) don't match.
PHONE = re.compile(r"(?:\+91[\s-]?)?(?<!\d)[6-9]\d{4}[\s-]?\d{5}(?!\d)")
AADHAAR = re.compile(r"(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)")
DL = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}[\s-]?\d{11}(?!\d)")


def mask(text):
    """Mask phones, aadhaar, DL numbers in any string. Keeps a 3-4 digit tail so a human can match records."""
    if not isinstance(text, str):
        return text
    text = PHONE.sub(lambda m: "+91 •••• ••" + re.sub(r"\D", "", m.group())[-3:], text)
    text = AADHAAR.sub(lambda m: "•••• •••• " + m.group()[-4:], text)
    text = DL.sub(lambda m: m.group()[:4] + " ••••••••" + m.group()[-3:], text)
    return text


def has_pii(text):
    return bool(PHONE.search(text) or AADHAAR.search(text) or DL.search(text))


PLATE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$")


def canon_vehicle(s):
    """CH-40-IK-6238 / ch40ik6238 / 'CH 40 IK 6238' -> CH40IK6238. None if it isn't a plate."""
    if not s:
        return None
    c = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return c if PLATE.match(c) else None


def canon_client(s):
    if not s:
        return None
    key = re.sub(r"[^a-z]", "", str(s).lower())
    for canon, aliases in CLIENT_ALIASES.items():
        if key in aliases:
            return canon
    return None


CLIENT_ALIASES = {
    "Shakti Cement": {"shakticement", "shakti", "shakticementltd", "shakticements"},
    "Vertex Retail": {"vertexretail", "vertex", "vertexretailltd"},
    "Apex Chemicals": {"apexchemicals", "apex", "apexchem", "apexchemical"},
    "Orion Pharma": {"orionpharma", "orion", "orionpharmaceuticals"},
    "Internal": {"internal", "meridian", "meridianfreight", "own"},
}


def stable_id(prefix, *parts):
    """Hash-based id. Same inputs, same id, every run."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12]
    return f"{prefix}-{h}"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def jsonl_append(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
