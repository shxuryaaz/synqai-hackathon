import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import approve
import common
import pipeline
import server


def exception_leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in exception_leaves(child)]
    return [error]


class ConnectionSpy:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def close(self):
        self.closed = True
        self.connection.close()


@pytest.fixture
def approval_store(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DB", tmp_path / "store.sqlite")
    monkeypatch.setattr(pipeline, "OUT", tmp_path / "outputs")
    monkeypatch.setattr(pipeline, "AUDIT", tmp_path / "audit")
    con = common.db()
    con.executescript(pipeline.PIPE_SCHEMA)
    con.execute(
        """insert into comms(message_id, ticket_id, recipient, body, context, citations, drafted_by)
           values('MSG-1', 'TKT-1', 'dispatch@example.test', 'Safe draft', '{}', '[]', 'template')"""
    )
    con.commit()
    pipeline.write_outputs(con)
    con.close()
    return tmp_path


@pytest.mark.parametrize("case", ["success", "conflict", "stored-pii", "transaction-failure", "projection-failure"])
def test_approval_connection_closes_on_every_database_path(approval_store, monkeypatch, case):
    if case == "stored-pii":
        con = sqlite3.connect(approval_store / "store.sqlite")
        con.execute("update comms set body='Call +91 98765 43210' where ticket_id='TKT-1'")
        con.commit()
        con.close()
    spy = ConnectionSpy(common.db())
    monkeypatch.setattr(approve, "db", lambda: spy)
    ticket_id = "TKT-MISSING" if case == "conflict" else "TKT-1"

    if case == "transaction-failure":
        def fail_audit(*args, **kwargs):
            raise RuntimeError("transaction failed")
        monkeypatch.setattr(approve, "audit", fail_audit)
    if case == "projection-failure":
        def fail_projection(con):
            raise OSError("projection failed")
        monkeypatch.setattr(approve, "write_outputs", fail_projection)

    errors = {
        "conflict": approve.ApprovalConflict,
        "stored-pii": approve.ApprovalValidationError,
        "transaction-failure": RuntimeError,
        "projection-failure": OSError,
    }
    if case == "success":
        assert approve.approve(ticket_id, "Reviewer")["result"] == "sent"
    else:
        with pytest.raises(errors[case]):
            approve.approve(ticket_id, "Reviewer")

    assert spy.closed
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        spy.execute("select 1")


def test_concurrent_approvals_have_one_winner_and_one_audit(approval_store, monkeypatch):
    barrier = Barrier(2)
    connections = []
    projections = []
    real_db = common.db
    real_write_outputs = approve.write_outputs

    def tracked_db():
        con = real_db()
        connections.append(con)
        return con

    def tracked_write_outputs(con):
        projections.append(con)
        real_write_outputs(con)

    def attempt(by, at):
        barrier.wait()
        try:
            return "sent", approve.approve("TKT-1", by, at=at)
        except approve.ApprovalConflict as error:
            return "conflict", str(error)

    monkeypatch.setattr(approve, "db", tracked_db)
    monkeypatch.setattr(approve, "write_outputs", tracked_write_outputs)
    contenders = [("Reviewer A", "2026-08-30T10:00:01+00:00"),
                  ("Reviewer B", "2026-08-30T10:00:02+00:00")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda args: attempt(*args), contenders))

    assert sorted(result for result, _ in outcomes) == ["conflict", "sent"]
    winner = next(payload for result, payload in outcomes if result == "sent")
    con = sqlite3.connect(approval_store / "store.sqlite")
    stored = con.execute(
        "select status, approved_by, sent_at from comms where ticket_id='TKT-1'"
    ).fetchone()
    audits = con.execute(
        "select count(*) from audit where ticket_id='TKT-1' and step='Approved and sent'"
    ).fetchone()[0]
    con.close()

    assert len(connections) == 2 and connections[0] is not connections[1]
    assert stored == ("sent", winner["approved_by"], winner["sent_at"])
    assert audits == 1
    assert len(projections) == 1
    sent = [json.loads(line) for line in
            (approval_store / "outputs" / "comms_sent.jsonl").read_text().splitlines()]
    assert len(sent) == 1
    assert sent[0]["approved_by"] == winner["approved_by"]
    assert sent[0]["sent_at"] == winner["sent_at"]


def test_missing_and_already_sent_api_approvals_are_conflicts(approval_store):
    client = TestClient(server.app)

    missing = client.post("/api/approve", json={"ticket_id": "TKT-MISSING", "by": "Reviewer"})
    sent = client.post("/api/approve", json={"ticket_id": "TKT-1", "by": "First"})
    repeated = client.post("/api/approve", json={"ticket_id": "TKT-1", "by": "Second"})

    assert missing.status_code == 409
    assert missing.json()["detail"] == "TKT-MISSING has no approval record"
    assert sent.status_code == 200
    assert repeated.status_code == 409
    assert "already sent by First" in repeated.json()["detail"]


@pytest.mark.parametrize("edit", ["Call +91 98765 43210", "Aadhaar 1234 5678 9012"])
def test_raw_pii_edit_is_rejected_before_database_or_projection(approval_store, monkeypatch, edit):
    before = {path: path.read_bytes() for directory in ("outputs", "audit")
              for path in (approval_store / directory).glob("*.jsonl")}
    monkeypatch.setattr(approve, "db", lambda: pytest.fail("database opened"))
    monkeypatch.setattr(approve, "write_outputs", lambda con: pytest.fail("projection ran"))

    with pytest.raises(approve.ApprovalValidationError, match="edited body matches"):
        approve.approve("TKT-1", "Reviewer", body=edit)

    con = sqlite3.connect(approval_store / "store.sqlite")
    assert con.execute(
        "select status, approved_by, sent_at, edited_body from comms where ticket_id='TKT-1'"
    ).fetchone() == ("pending", None, None, None)
    assert con.execute(
        "select count(*) from audit where ticket_id='TKT-1' and step='Approved and sent'"
    ).fetchone()[0] == 0
    con.close()
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("edit", ["Call +91 98765 43210", "Aadhaar 1234 5678 9012"])
def test_raw_pii_edit_api_returns_422_without_side_effects(approval_store, monkeypatch, edit):
    before = {path: path.read_bytes() for directory in ("outputs", "audit")
              for path in (approval_store / directory).glob("*.jsonl")}
    monkeypatch.setattr(approve, "write_outputs", lambda con: pytest.fail("projection ran"))
    client = TestClient(server.app)

    response = client.post("/api/approve", json={"ticket_id": "TKT-1", "by": "Reviewer", "body": edit})

    assert response.status_code == 422
    assert "edited body matches a PII pattern" in response.json()["detail"]
    con = sqlite3.connect(approval_store / "store.sqlite")
    assert con.execute(
        "select status, approved_by, sent_at, edited_body from comms where ticket_id='TKT-1'"
    ).fetchone() == ("pending", None, None, None)
    assert con.execute(
        "select count(*) from audit where ticket_id='TKT-1' and step='Approved and sent'"
    ).fetchone()[0] == 0
    con.close()
    assert {path: path.read_bytes() for path in before} == before


def test_raw_pii_edit_is_rejected_under_python_optimized_mode(approval_store):
    before = {path: path.read_bytes() for directory in ("outputs", "audit")
              for path in (approval_store / directory).glob("*.jsonl")}

    result = subprocess.run(
        [sys.executable, "-O", "approve.py", "TKT-1", "--by", "Reviewer",
         "--body", "Call +91 98765 43210"],
        cwd=ROOT, env={**os.environ, "MERIDIAN_WORK": str(approval_store)},
        capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert "ApprovalValidationError" in result.stderr
    con = sqlite3.connect(approval_store / "store.sqlite")
    assert con.execute(
        "select status, approved_by, sent_at, edited_body from comms where ticket_id='TKT-1'"
    ).fetchone() == ("pending", None, None, None)
    assert con.execute(
        "select count(*) from audit where ticket_id='TKT-1' and step='Approved and sent'"
    ).fetchone()[0] == 0
    con.close()
    assert {path: path.read_bytes() for path in before} == before


def test_late_projection_failure_keeps_committed_sqlite_and_restores_all_files(approval_store, monkeypatch):
    destinations = list((approval_store / "outputs").glob("*.jsonl"))
    destinations += list((approval_store / "audit").glob("*.jsonl"))
    (approval_store / "outputs" / "work_orders.jsonl").unlink()
    before = {path: path.read_bytes() if path.exists() else None for path in destinations}
    real_replace = common.os.replace
    replaced = []
    failed = False

    def fail_late(source, destination):
        nonlocal failed
        name = Path(destination).name
        if name == "comms_sent.jsonl" and not failed:
            failed = True
            raise OSError("late projection failure")
        real_replace(source, destination)
        replaced.append(name)

    monkeypatch.setattr(common.os, "replace", fail_late)
    client = TestClient(server.app)
    with pytest.raises(OSError, match="late projection failure"):
        client.post("/api/approve", json={"ticket_id": "TKT-1", "by": "Reviewer"})

    con = sqlite3.connect(approval_store / "store.sqlite")
    assert con.execute(
        "select status, approved_by, sent_at from comms where ticket_id='TKT-1'"
    ).fetchone()[0:2] == ("sent", "Reviewer")
    assert con.execute(
        "select count(*) from audit where ticket_id='TKT-1' and step='Approved and sent'"
    ).fetchone()[0] == 1
    con.close()
    assert failed and {"work_orders.jsonl", "comms_pending.jsonl"} <= set(replaced)
    assert {path: path.read_bytes() if path.exists() else None for path in destinations} == before
    for path, content in before.items():
        if content is not None:
            for line in path.read_text().splitlines():
                json.loads(line)


def test_failed_backup_restore_is_preserved_and_reported(tmp_path, monkeypatch):
    destinations = {tmp_path / f"{name}.jsonl": [{"state": f"new-{name}"}]
                    for name in ("first", "second", "third")}
    for path in destinations:
        path.write_text(json.dumps({"state": f"old-{path.stem}"}) + "\n")
    projection_error = OSError("replacement failed")
    real_replace = common.os.replace
    failed = False
    failed_backup = None
    restored_backup = None

    def fail_projection_and_restore(source, destination):
        nonlocal failed, failed_backup, restored_backup
        name = Path(destination).name
        if name == "third.jsonl" and not failed:
            failed = True
            raise projection_error
        if failed and name == "second.jsonl":
            failed_backup = Path(source)
            raise OSError("backup restore failed")
        if failed and name == "first.jsonl":
            restored_backup = Path(source)
        real_replace(source, destination)

    monkeypatch.setattr(common.os, "replace", fail_projection_and_restore)
    with pytest.raises(ExceptionGroup) as caught:
        common.atomic_write_jsonls(destinations)

    assert caught.value.exceptions[0] is projection_error
    assert failed_backup and failed_backup.exists()
    assert failed_backup.read_bytes() == b'{"state": "old-second"}\n'
    assert any(str(failed_backup) in str(error) for error in caught.value.exceptions)
    assert restored_backup and not restored_backup.exists()
    assert (tmp_path / "first.jsonl").read_bytes() == b'{"state": "old-first"}\n'
    assert (tmp_path / "second.jsonl").read_bytes() == b'{"state": "new-second"}\n'
    assert (tmp_path / "third.jsonl").read_bytes() == b'{"state": "old-third"}\n'
    for path in [*destinations, failed_backup]:
        json.loads(path.read_text())


def test_cleanup_failure_is_grouped_with_projection_failure(tmp_path, monkeypatch):
    destinations = {tmp_path / f"{name}.jsonl": [{"state": f"new-{name}"}]
                    for name in ("first", "second")}
    for path in destinations:
        path.write_text(json.dumps({"state": f"old-{path.stem}"}) + "\n")
    projection_error = OSError("replacement failed")
    cleanup_error = OSError("unlink failed")
    cleanup_target = None
    real_replace = common.os.replace
    real_unlink = Path.unlink

    def fail_projection(source, destination):
        nonlocal cleanup_target
        if Path(destination).name == "second.jsonl":
            cleanup_target = Path(source)
            raise projection_error
        real_replace(source, destination)

    def fail_cleanup(path, *args, **kwargs):
        if path == cleanup_target:
            raise cleanup_error
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(common.os, "replace", fail_projection)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(ExceptionGroup) as caught:
        common.atomic_write_jsonls(destinations)

    leaves = exception_leaves(caught.value)
    assert projection_error in leaves
    assert cleanup_error in leaves
    assert cleanup_target and cleanup_target.exists()
    assert any(str(cleanup_target) in note for note in cleanup_error.__notes__)
    real_unlink(cleanup_target)


def test_cleanup_only_failure_is_raised_clearly(tmp_path, monkeypatch):
    destination = tmp_path / "only.jsonl"
    destination.write_text('{"state": "old"}\n')
    cleanup_error = OSError("backup cleanup failed")
    cleanup_target = None
    real_unlink = Path.unlink

    def fail_cleanup(path, *args, **kwargs):
        nonlocal cleanup_target
        if path != destination and path.name.startswith(".only.jsonl."):
            cleanup_target = path
            raise cleanup_error
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(ExceptionGroup, match="projection cleanup failed") as caught:
        common.atomic_write_jsonls({destination: [{"state": "new"}]})

    assert exception_leaves(caught.value) == [cleanup_error]
    assert cleanup_target and cleanup_target.read_bytes() == b'{"state": "old"}\n'
    assert any(str(cleanup_target) in note for note in cleanup_error.__notes__)
    assert json.loads(destination.read_text()) == {"state": "new"}
    real_unlink(cleanup_target)


def test_pii_guard_is_explicit(approval_store):
    con = sqlite3.connect(approval_store / "store.sqlite")
    con.execute("update comms set body='Call +91 98765 43210' where ticket_id='TKT-1'")
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="refusing to send"):
        approve.approve("TKT-1", "Reviewer")
