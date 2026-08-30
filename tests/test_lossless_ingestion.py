import json, os, shutil, sqlite3, subprocess, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "candidate_bundle" / "tickets.json"
sys.path.insert(0, str(ROOT))


def run(work, *args):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          env={**os.environ, "MERIDIAN_WORK": str(work)},
                          capture_output=True, text=True, check=True)


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    path = tmp_path_factory.mktemp("lossless-base")
    run(path, "ingest.py")
    return path


@pytest.fixture
def work(base, tmp_path):
    shutil.copy(base / "store.sqlite", tmp_path / "store.sqlite")
    return tmp_path


def ticket(ticket_id):
    return {
        "ticket_id": ticket_id,
        "created_at": "2026-08-20T10:00:00",
        "vehicle": "CH40IK6238",
        "origin_hub": "Chandigarh",
        "destination": "Delhi",
        "issue": "tyre burst",
        "client": "Internal",
    }


def output_rows(work, name):
    path = work / "outputs" / name
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_normal_startup_restart_preserves_approval(work):
    run(work, "pipeline.py", str(TICKETS))
    sent = json.loads(run(work, "approve.py", "TKT-0009", "--by", "Ramesh Kumar").stdout)
    run(work, "ingest.py")
    run(work, "pipeline.py", str(TICKETS))

    row = sqlite3.connect(work / "store.sqlite").execute(
        "select status, approved_by, sent_at from comms where ticket_id='TKT-0009'"
    ).fetchone()
    assert row == ("sent", "Ramesh Kumar", sent["sent_at"])
    assert output_rows(work, "comms_sent.jsonl")[0]["approved_by"] == "Ramesh Kumar"


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        (".json", lambda record: record),
        (".json", lambda record: [record]),
        (".json", lambda record: {"tickets": [record]}),
        (".jsonl", lambda record: json.dumps(record) + "\n"),
    ],
    ids=["single-object", "array", "wrapped-list", "jsonl"],
)
def test_supported_json_shapes_produce_one_record(work, tmp_path, suffix, payload):
    record = ticket("TKT-SHAPE")
    path = tmp_path / f"tickets{suffix}"
    data = payload(record)
    path.write_text(data if isinstance(data, str) else json.dumps(data))

    summary = json.loads(run(work, "pipeline.py", str(path)).stdout)

    assert summary["records"] == 1
    assert [row["ticket_id"] for row in output_rows(work, "work_orders.jsonl")] == ["TKT-SHAPE"]


def test_single_ticket_with_list_field_is_not_unwrapped(work, tmp_path):
    record = ticket("TKT-TAGS")
    record["tags"] = ["roadside", "urgent"]
    path = tmp_path / "ticket-with-tags.json"
    path.write_text(json.dumps(record))

    summary = json.loads(run(work, "pipeline.py", str(path)).stdout)

    assert summary["records"] == 1
    assert [row["ticket_id"] for row in output_rows(work, "work_orders.jsonl")] == ["TKT-TAGS"]


def test_existing_wrapped_surprise_input_still_loads(work):
    run(work, "pipeline.py", str(ROOT / "surprise_test.json"))

    assert {row["ticket_id"] for row in output_rows(work, "work_orders.jsonl")} == {"TKT-2001", "TKT-2002"}


def test_failed_duplicate_does_not_suppress_valid_copy(work, tmp_path):
    bad = ticket("TKT-DUP")
    bad["vehicle"] = ""
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps([bad, ticket("TKT-DUP")]))

    summary = json.loads(run(work, "pipeline.py", str(path)).stdout)

    assert summary["duplicates_skipped"] == 0
    assert any(row["ticket_id"] == "TKT-DUP" for row in output_rows(work, "work_orders.jsonl"))
    assert any(row["ticket_id"] == "TKT-DUP" and row["reason"] == "missing_field"
               for row in output_rows(work, "quarantine.jsonl"))


def test_unknown_destination_is_quarantined(work, tmp_path):
    record = ticket("TKT-NOWHERE")
    record["destination"] = "Atlantis"
    path = tmp_path / "unknown-destination.json"
    path.write_text(json.dumps(record))

    run(work, "pipeline.py", str(path))

    quarantine = output_rows(work, "quarantine.jsonl")
    assert len(quarantine) == 1
    assert quarantine[0]["reason"] == "unknown_destination"
    assert not output_rows(work, "work_orders.jsonl")


def test_nested_pii_is_masked_on_every_failure_surface(work, tmp_path):
    raw = ["+91 98765 43210", "1234 5678 9012", "DL09 12345678901"]
    record = ticket("TKT-PII")
    record["destination"] = "Atlantis"
    record["issue"] = {"contact": raw[0], "identity": [raw[1], {"licence": raw[2]}]}
    path = tmp_path / "9876543210.json"
    path.write_text(json.dumps(record))

    result = run(work, "pipeline.py", str(path))
    api = run(work, "-c", "import json, server; print(json.dumps(server.attention()))").stdout
    stored = sqlite3.connect(work / "store.sqlite").execute(
        "select source_file, detail, record from quarantine where ticket_id='TKT-PII'"
    ).fetchone()
    surfaces = result.stdout + api + "".join(stored)
    surfaces += (work / "outputs" / "quarantine.jsonl").read_text()
    surfaces += (work / "audit" / "audit.jsonl").read_text()
    surfaces += (work / "logs" / "pipeline.jsonl").read_text()

    assert all(value not in surfaces for value in raw)
    assert "9876543210.json" not in surfaces
    assert run(work, "pii_scan.py").returncode == 0


def test_logs_are_scoped_to_each_run(work, tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps([ticket("TKT-LOG-1"), ticket("TKT-LOG-1")]))
    second.write_text(json.dumps(ticket("TKT-LOG-2")))
    script = (
        "import json, pipeline, sys; "
        "print(json.dumps([pipeline.run(sys.argv[1]), pipeline.run(sys.argv[2])]))"
    )

    summaries = json.loads(run(work, "-c", script, str(first), str(second)).stdout)

    assert summaries[0]["duplicates_skipped"] == 1
    assert summaries[1]["duplicates_skipped"] == 0
    assert "duplicate_skipped" not in (work / "logs" / "pipeline.jsonl").read_text()


def test_atomic_jsonl_failure_keeps_previous_projection(tmp_path, monkeypatch):
    import common

    target = tmp_path / "projection.jsonl"
    target.write_text('{"state": "old"}\n')
    replacement = {}

    def fail_replace(source, destination):
        replacement.update(source=Path(source), destination=Path(destination))
        raise OSError("interrupted")

    monkeypatch.setattr(common.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        common.atomic_write_jsonl(target, [{"state": "new"}])

    assert replacement["source"].parent == target.parent
    assert replacement["destination"] == target
    assert target.read_text() == '{"state": "old"}\n'
    assert not replacement["source"].exists()
