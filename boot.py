"""Container start: restore the store from Neon, or build it from the bundle on a fresh deploy. Then project the output files."""
import subprocess, sys
import persist, pipeline
from common import db

if persist.restore():
    print("boot: restored store from Neon")
else:
    subprocess.run([sys.executable, "ingest.py"], check=True)
    subprocess.run([sys.executable, "pipeline.py", "candidate_bundle/tickets.json"], check=True)
    persist.save()
    print("boot: built store from bundle")
con = db(); con.executescript(pipeline.PIPE_SCHEMA); pipeline.write_outputs(con)
