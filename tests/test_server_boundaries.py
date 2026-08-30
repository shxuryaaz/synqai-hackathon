import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server


def test_server_starts_on_loopback():
    run_script = (ROOT / "run.sh").read_text()
    assert "uvicorn server:app --host 127.0.0.1 --port 8000" in run_script


def test_spa_rejects_plain_encoded_and_symlink_traversal(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (dist / "escape").symlink_to(outside)
    monkeypatch.setattr(server, "DIST", dist.resolve())

    with pytest.raises(HTTPException) as plain:
        server.spa("../secret.txt")
    assert plain.value.status_code == 404

    client = TestClient(server.app)
    assert client.get("/%2e%2e/secret.txt").status_code == 404
    assert client.get("/escape").status_code == 404
    assert client.get("/missing-route").text == "index"
    (dist / "index.html").unlink()
    (dist / "index.html").symlink_to(outside)
    assert client.get("/missing-route").status_code == 404


def test_run_ignores_client_filesystem_paths(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(server.pipeline, "run", lambda path: calls.append(path) or {"result": "ok"})
    client = TestClient(server.app)

    assert client.post("/api/run", json={}).status_code == 200
    assert client.post("/api/run", json={"file": str(tmp_path / "secret.json")}).status_code == 200
    expected = str(server.ROOT / "candidate_bundle" / "tickets.json")
    assert calls == [expected, expected]
