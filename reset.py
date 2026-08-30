"""Back to a clean slate: only the original queue, processed once. Never touches .env or the LLM cache."""
import shutil, subprocess, sys
from common import DB, OUT, AUDIT, LOGS
for suffix in ("", "-wal", "-shm"):
    DB.with_name(DB.name + suffix).unlink(missing_ok=True)
for d in (OUT, AUDIT, LOGS):
    shutil.rmtree(d, ignore_errors=True)
subprocess.run([sys.executable, "ingest.py"], check=True)
subprocess.run([sys.executable, "pipeline.py", "candidate_bundle/tickets.json"], check=True)
import persist; persist.save()
print("reset: store rebuilt from candidate_bundle/tickets.json")
