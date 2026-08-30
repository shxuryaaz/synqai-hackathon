#!/usr/bin/env bash
# One command: deps, ingest, pipeline, PII scan, double-run check, server. Safe to run repeatedly.
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo "install uv first: https://docs.astral.sh/uv/"; exit 1; }
uv sync -q
[ -f .env ] || cp .env.example .env
uv run python ingest.py
uv run python pipeline.py "${1:-candidate_bundle/tickets.json}"
uv run python pii_scan.py
uv run python rerun_check.py "${1:-candidate_bundle/tickets.json}"
if [ -f server.py ]; then
  if [ -d ui ]; then
    command -v npm >/dev/null || { echo "install npm first"; exit 1; }
    (cd ui && npm ci --silent && npm run build --silent)
  fi
  echo "Meridian Ops: http://localhost:8000"
  uv run uvicorn server:app --host 127.0.0.1 --port 8000
fi
