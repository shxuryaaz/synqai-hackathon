import ast
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


SMOKE = r"""
import json
import os
import socket
from pathlib import Path

root = Path.cwd()
work = Path(os.environ["MERIDIAN_WORK"])
network_attempts = []

def block_network(*args, **kwargs):
    network_attempts.append(repr(args[1:] or args))
    raise AssertionError("network access attempted")

socket.socket.connect = block_network
socket.socket.connect_ex = block_network
socket.create_connection = block_network

import ingest
from fastapi.testclient import TestClient
import server

ingest.main()
with TestClient(server.app) as client:
    run = client.post("/api/run")
    assert run.status_code == 200
    assert run.json()["exceptions"] == 0

    upload = client.post(
        "/api/upload",
        files={"file": ("surprise.json", (root / "surprise_test.json").read_bytes(), "application/json")},
    )
    assert upload.status_code == 200
    assert upload.json()["records"] == 4
    assert upload.json()["duplicates_skipped"] == 1
    assert (work / "uploads" / "surprise.json").is_file()

    attention = client.get("/api/attention")
    assert attention.status_code == 200
    held = {item["ticket_id"]: item for item in attention.json()["quarantined"]}
    assert held["TKT-2003"]["source_file"] == "surprise.json"

    approvals = client.get("/api/approvals")
    assert approvals.status_code == 200
    assert "TKT-2001" in {item["ticket_id"] for item in approvals.json()["pending"]}
    approved = client.post("/api/approve", json={"ticket_id": "TKT-2001", "by": "QA Local"})
    assert approved.status_code == 200
    sent_at = approved.json()["sent_at"]

    before_restart = client.get("/api/history/TKT-2001")
    assert before_restart.status_code == 200
    assert any(step["step"] == "Approved and sent" for step in before_restart.json()["steps"])

    ingest.main()
    after_restart = client.get("/api/approvals")
    sent = {item["ticket_id"]: item for item in after_restart.json()["sent"]}
    assert sent["TKT-2001"]["approved_by"] == "QA Local"
    assert sent["TKT-2001"]["sent_at"] == sent_at

    history = client.get("/api/history/TKT-2001")
    assert history.status_code == 200
    assert any(step["step"] == "Approved and sent" and "approved by QA Local" in step["decision"]
               for step in history.json()["steps"])

    precedence = client.get("/api/precedence")
    graph = client.get("/api/graph")
    replay = client.get("/api/random-ticket")
    assert precedence.status_code == graph.status_code == replay.status_code == 200
    assert precedence.json()["order"][0] == "fleet_master"
    assert graph.json()["nodes"]
    assert replay.json()["steps"]

    rerun = client.post("/api/rerun-check")
    assert rerun.status_code == 200
    assert rerun.json()["identical"] is True
    assert rerun.json()["differences"] == []
    rerun_history = client.get("/api/history/TKT-2001").json()["rerun"]
    assert rerun_history["identical"] is True

    scan = client.post("/api/pii-scan", json={"plant": False})
    assert scan.status_code == 200
    assert scan.json()["leaks"] == 0

assert network_attempts == []
print(json.dumps({"work": str(work), "rerun_files": rerun.json()["files_compared"]}))
"""


def test_no_network_local_operator_smoke(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", SMOKE],
        cwd=ROOT,
        env={**os.environ, "MERIDIAN_WORK": str(tmp_path), "OPENAI_API_KEY": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_linear_sdk_or_service_dependency():
    imports = set()
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0].lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0].lower())
    assert "linear" not in imports

    manifests = (ROOT / "pyproject.toml", ROOT / "ui" / "package.json")
    assert all("linear" not in path.read_text().lower() for path in manifests)

    app_sources = [*ROOT.glob("*.py"), *(ROOT / "ui" / "src").glob("*.*")]
    service_markers = ("api.linear.app", "linear.app", "linear_client", "linearclient")
    assert not {
        str(path.relative_to(ROOT)): marker
        for path in app_sources
        for marker in service_markers
        if marker in path.read_text(errors="ignore").lower()
    }
