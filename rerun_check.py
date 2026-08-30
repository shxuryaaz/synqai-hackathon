"""Run the pipeline twice on the same file and diff every output byte. Run: python rerun_check.py [ticket_file]"""
import hashlib, json, sys
from datetime import datetime, timezone
from common import OUT, AUDIT, db
import pipeline


def snapshot():
    return {str(p.relative_to(p.parent.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for d in (OUT, AUDIT) if d.exists() for p in sorted(d.glob("*.jsonl"))}


def check(path="candidate_bundle/tickets.json"):
    pipeline.run(path); a = snapshot()
    pipeline.run(path); b = snapshot()
    diffs = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    con = db()
    con.execute("create table if not exists meta(key primary key, value)")
    con.execute("insert or replace into meta values('last_rerun_check', ?)", (json.dumps({"identical": not diffs, "differences": diffs, "files": len(a), "at": datetime.now(timezone.utc).isoformat(timespec='seconds'), "file": path}),))
    con.commit()
    return {"identical": not diffs, "differences": diffs, "files_compared": len(a)}


if __name__ == "__main__":
    r = check(sys.argv[1] if len(sys.argv) > 1 else "candidate_bundle/tickets.json")
    print(json.dumps(r))
    sys.exit(0 if r["identical"] else 1)
