"""AI-assisted format gate: one proposal per column set, nothing processes until a human approves."""
import json, os, subprocess, sys, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "tests" / "data" / "final_hour_test_2.jsonl"


def pipe(work, counter, path=FILE):
    env = {**os.environ, "MERIDIAN_WORK": str(work), "MERIDIAN_LLM_FAKE": str(counter)}
    subprocess.run([sys.executable, "ingest.py"], cwd=ROOT, env=env, check=True, capture_output=True)
    return json.loads(subprocess.run([sys.executable, "pipeline.py", str(path)], cwd=ROOT, env=env, check=True, capture_output=True).stdout)


def test_same_file_twice_asks_once_and_processes_nothing(tmp_path):
    work, counter = tmp_path / "w", tmp_path / "calls"; work.mkdir()
    first = pipe(work, counter)
    assert first["unrecognized"] is True and int(counter.read_text()) == 1
    second = pipe(work, counter)
    assert second["unrecognized"] is True and int(counter.read_text()) == 1
    con = sqlite3.connect(work / "store.sqlite")
    assert con.execute("select count(*) from format_maps where status='proposed'").fetchone()[0] == 1
    assert con.execute("select count(*) from work_orders").fetchone()[0] == 0


APPROVE = r"""
import json, sqlite3, os
from pathlib import Path
from fastapi.testclient import TestClient
import server
work = Path(os.environ["MERIDIAN_WORK"])
con = sqlite3.connect(work / "store.sqlite")
key, mapping = con.execute("select key, mapping from format_maps").fetchone()
m = json.loads(mapping)
assert m["Reg_No"]["target"] == "vehicle" and m["Dist_KM"]["target"] == "km_from_origin_hub", m
with TestClient(server.app) as c:
    assert [x["key"] for x in c.get("/api/attention").json()["format_maps"]] == [key]
    assert c.post("/api/format-map", json={"key": key, "by": "Ramesh Kumar"}).json()["result"] == "processed"
    assert c.get("/api/attention").json()["format_maps"] == []
print("ok")
"""


def test_approved_mapping_processes_five_of_seven(tmp_path):
    work, counter = tmp_path / "w", tmp_path / "calls"; work.mkdir()
    pipe(work, counter)
    env = {**os.environ, "MERIDIAN_WORK": str(work), "MERIDIAN_LLM_FAKE": str(counter)}
    r = subprocess.run([sys.executable, "-c", APPROVE], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    wos = {w["ticket_id"] for w in map(json.loads, (work / "outputs" / "work_orders.jsonl").read_text().splitlines())}
    # 7 records: 5 pass validation (TKT-8103 twice, processed once) -> 4 work orders; bad date and blank id are held
    assert wos == {"TKT-8101", "TKT-8102", "TKT-8103", "TKT-8106"}, wos
    q = [json.loads(l) for l in (work / "outputs" / "quarantine.jsonl").read_text().splitlines()]
    assert {x["reason"] for x in q} == {"bad_date", "missing_field"} and len(q) == 2
    before = (work / "outputs" / "work_orders.jsonl").read_bytes()
    pipe(work, counter)
    assert (work / "outputs" / "work_orders.jsonl").read_bytes() == before
