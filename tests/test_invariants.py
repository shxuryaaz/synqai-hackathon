"""The six invariants. Each test gets its own copy of a freshly ingested store under a temp MERIDIAN_WORK."""
import json, os, shutil, subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "candidate_bundle" / "tickets.json"


def run(work, *args, check=True):
    return subprocess.run([sys.executable, *args], cwd=ROOT, env={**os.environ, "MERIDIAN_WORK": str(work)}, capture_output=True, text=True, check=check)


@pytest.fixture(scope="session")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("base")
    run(d, "ingest.py")
    return d


@pytest.fixture
def work(base, tmp_path):
    shutil.copy(base / "store.sqlite", tmp_path / "store.sqlite")
    return tmp_path


def lines(p):
    return [json.loads(l) for l in p.read_text().splitlines()]


def test_duplicates_produce_one_work_order(work):
    run(work, "pipeline.py", str(TICKETS))
    ids = [w["ticket_id"] for w in lines(work / "outputs" / "work_orders.jsonl")]
    assert len(ids) == len(set(ids))
    queue = json.load(open(TICKETS))
    assert len({t["ticket_id"] for t in queue}) == len(ids) + len(lines(work / "outputs" / "quarantine.jsonl"))


def test_double_run_identical(work):
    run(work, "pipeline.py", str(TICKETS))
    first = {p.name: p.read_bytes() for p in (work / "outputs").glob("*.jsonl")} | {"audit": (work / "audit" / "audit.jsonl").read_bytes()}
    run(work, "pipeline.py", str(TICKETS))
    second = {p.name: p.read_bytes() for p in (work / "outputs").glob("*.jsonl")} | {"audit": (work / "audit" / "audit.jsonl").read_bytes()}
    assert first == second


def test_broken_records_quarantined_with_reason(work):
    run(work, "pipeline.py", str(TICKETS))
    q = {r["ticket_id"]: r for r in lines(work / "outputs" / "quarantine.jsonl")}
    assert q["TKT-9101"]["reason"] == "missing_field" and "vehicle" in q["TKT-9101"]["detail"]
    assert all(r["alert"] for r in q.values())


def test_pii_scanner_catches_planted_leak(work):
    run(work, "pipeline.py", str(TICKETS))
    assert run(work, "pii_scan.py").returncode == 0
    (work / "outputs" / "leak.jsonl").write_text('{"body": "call driver on +91 93118 40522"}\n')
    r = run(work, "pii_scan.py", check=False)
    assert r.returncode == 1 and "LEAK phone" in r.stdout and "40522" not in r.stdout


def test_unknown_schema_quarantined_not_crashed(work, tmp_path):
    bad = tmp_path / "weird.json"
    bad.write_text(json.dumps([{"foo": 1, "bar": "x"}, {"foo": 2}]))
    out = json.loads(run(work, "pipeline.py", str(bad)).stdout)
    assert out["unrecognized"] is True
    q = lines(work / "outputs" / "quarantine.jsonl")
    assert len(q) == 2 and all(r["reason"] == "unrecognized_format" for r in q)


def test_surprise_format_is_mapped(work):
    run(work, "pipeline.py", str(ROOT / "surprise_test.json"))
    wos = {w["ticket_id"]: w for w in lines(work / "outputs" / "work_orders.jsonl")}
    assert set(wos) == {"TKT-2001", "TKT-2002"}
    assert wos["TKT-2001"]["created_at"] == "2026-08-19T07:45:00" and wos["TKT-2001"]["vehicle_reg"] == "HR16SP9238"
    assert lines(work / "outputs" / "quarantine.jsonl")[0]["ticket_id"] == "TKT-2003"


def test_double_approval_does_not_double_send(work):
    run(work, "pipeline.py", str(TICKETS))
    a = json.loads(run(work, "approve.py", "TKT-0009", "--by", "Ramesh Kumar").stdout)
    b = run(work, "approve.py", "TKT-0009", "--by", "Someone Else", check=False)
    assert a["result"] == "sent"
    assert b.returncode != 0 and "already sent by Ramesh Kumar" in b.stderr
    sent = lines(work / "outputs" / "comms_sent.jsonl")
    assert len(sent) == 1 and sent[0]["approved_by"] == "Ramesh Kumar"
    approvals = [l for l in lines(work / "audit" / "audit.jsonl")
                 if l["ticket_id"] == "TKT-0009" and l["step"] == "Approved and sent"]
    assert len(approvals) == 1
    assert run(work, "pii_scan.py").returncode == 0


def test_cold_then_warm_llm_cache_identical(work, tmp_path):
    """Run 1 calls the (fake) model, run 2 must hit the cache. The fake returns a different draft on every real call."""
    counter = tmp_path / "calls"
    env = {"MERIDIAN_LLM_FAKE": str(counter)}
    subprocess.run([sys.executable, "pipeline.py", str(TICKETS)], cwd=ROOT, env={**os.environ, "MERIDIAN_WORK": str(work), **env}, check=True, capture_output=True)
    first = (work / "outputs" / "comms_pending.jsonl").read_bytes()
    calls_after_cold = int(counter.read_text())
    subprocess.run([sys.executable, "pipeline.py", str(TICKETS)], cwd=ROOT, env={**os.environ, "MERIDIAN_WORK": str(work), **env}, check=True, capture_output=True)
    assert (work / "outputs" / "comms_pending.jsonl").read_bytes() == first
    assert int(counter.read_text()) == calls_after_cold and calls_after_cold > 0
    assert b"FAKE DRAFT" in first and b'"drafted_by": "gpt-4o"' in first


def test_llm_down_falls_back_and_audits(work):
    env = {**os.environ, "MERIDIAN_WORK": str(work)}
    env.pop("OPENAI_API_KEY", None)
    subprocess.run([sys.executable, "pipeline.py", str(TICKETS)], cwd=ROOT, env=env | {"OPENAI_API_KEY": ""}, check=True, capture_output=True)
    pend = lines(work / "outputs" / "comms_pending.jsonl")
    assert pend and all(p["drafted_by"] == "template" for p in pend)
    assert any(l["step"] == "Draft fallback" for l in lines(work / "audit" / "audit.jsonl"))
