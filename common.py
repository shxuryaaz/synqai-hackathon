"""Shared bits: paths, PII masking, canonical ids, sqlite handle."""
import hashlib, json, os, re, sqlite3, tempfile
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


def mask_data(value):
    """Recursively mask PII before structured data crosses a persistence or output boundary."""
    if isinstance(value, dict):
        return {mask(str(k)): mask_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_data(v) for v in value]
    if isinstance(value, tuple):
        return tuple(mask_data(v) for v in value)
    return mask(value)


def has_pii(text):
    return bool(PHONE.search(text) or AADHAAR.search(text) or DL.search(text))


PLATE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$")


def canon_vehicle(s):
    """CH-40-IK-6238 / ch40ik6238 / 'CH 40 IK 6238' -> CH40IK6238. None if it isn't a plate."""
    if not s:
        return None
    c = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return c if PLATE.match(c) else None


def pretty_plate(canon):
    """CH40IK6238 -> CH-40-IK-6238 for display."""
    m = re.match(r"^([A-Z]{2})(\d{2})([A-Z]{1,2})(\d{4})$", canon or "")
    return "-".join(m.groups()) if m else canon


def canon_client(s):
    if not s:
        return None
    key = re.sub(r"[^a-z]", "", str(s).lower())
    for canon, aliases in CLIENT_ALIASES.items():
        if key in aliases:
            return canon
    try:  # persisted fuzzy-match proposals (llm.py job 4); re-runs read the table, never re-ask
        row = db().execute("select canon from entity_map where kind='client' and original=?", (key,)).fetchone()
        return row[0] if row else None
    except Exception:
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


def _stage_file(path, mode, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode, encoding="utf-8" if "b" not in mode else None, dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            temp = Path(f.name)
            write(f)
            f.flush()
            os.fsync(f.fileno())
        return temp
    except Exception as stage_error:
        if temp:
            try:
                temp.unlink(missing_ok=True)
            except Exception as cleanup_error:
                cleanup_error.add_note(f"failed to clean staged file {temp}")
                raise ExceptionGroup("staging and cleanup failed", [stage_error, cleanup_error])
        raise


def atomic_write_jsonls(writes, sanitize=True):
    """Stage and replace a set of JSONL files, restoring every destination if replacement fails."""
    staged = []
    preserved_backups = set()
    failure = None
    try:
        for target, rows in writes.items():
            target = Path(target)

            def write_jsonl(f):
                for row in rows:
                    f.write(json.dumps(mask_data(row) if sanitize else row, ensure_ascii=False, sort_keys=True) + "\n")

            replacement = _stage_file(target, "w", write_jsonl)
            staged.append([target, replacement, None])
        for item in staged:
            if item[0].exists():
                item[2] = _stage_file(item[0], "wb", lambda f, target=item[0]: f.write(target.read_bytes()))
        replaced = []
        try:
            for item in staged:
                os.replace(item[1], item[0])
                item[1] = None
                replaced.append(item)
        except Exception as replacement_error:
            restore_errors = []
            for item in reversed(replaced):
                try:
                    if item[2]:
                        os.replace(item[2], item[0])
                        item[2] = None
                    else:
                        item[0].unlink(missing_ok=True)
                except Exception as error:
                    if item[2]:
                        preserved_backups.add(item[2])
                        detail = f"failed to restore {item[0]}; prior bytes preserved at {item[2]}: {error}"
                    else:
                        detail = f"failed to remove newly created {item[0]} during recovery: {error}"
                    restore_errors.append(RuntimeError(detail))
            if restore_errors:
                failure = ExceptionGroup("projection failed and recovery was incomplete",
                                         [replacement_error, *restore_errors])
            else:
                failure = replacement_error
    except Exception as error:
        failure = error

    cleanup_errors = []
    for _, replacement, backup in staged:
        for path in (replacement, backup):
            if path and path not in preserved_backups:
                try:
                    path.unlink(missing_ok=True)
                except Exception as error:
                    error.add_note(f"failed to clean staged file {path}")
                    cleanup_errors.append(error)
    if cleanup_errors:
        active_errors = list(failure.exceptions) if isinstance(failure, ExceptionGroup) else ([failure] if failure else [])
        errors = active_errors + cleanup_errors
        raise ExceptionGroup("projection and cleanup failed" if failure else "projection cleanup failed", errors)
    if failure:
        raise failure


def atomic_write_jsonl(path, rows, sanitize=True):
    """Replace one JSONL file only after its complete replacement is durable."""
    atomic_write_jsonls({path: rows}, sanitize)
