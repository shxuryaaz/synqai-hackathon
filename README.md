# Meridian Ops

Meridian Ops turns freight breakdown tickets into work orders and client message drafts for local dispatcher review.

## Quickstart

```bash
./run.sh
```

## What works

Open http://localhost:8000 to see the Operations screen with a North India map, breakdown cards, replacement dispatches, and links to Approvals, Attention, Evaluator, and ticket history.

The server binds to `127.0.0.1`, so it is available only on this computer. It uses no Linear service or SDK. Approving a draft records a local workflow transition but does not deliver a real external message. Normal reruns rebuild source data and generated files while preserving approvals and other operational state in `store.sqlite`.

`outputs/`, `audit/`, and `logs/` are generated. `store.sqlite` and its sidecar files hold persistent state. To reset both:

```bash
rm -rf "${MERIDIAN_WORK:-$PWD}"/{store.sqlite,store.sqlite-shm,store.sqlite-wal,outputs,audit,logs}
```

## Requirements

- Python `==3.12.*`, as locked in `uv.lock` and constrained by `pyproject.toml`
- uv with support for lockfile format version 1, revision 3
- Node.js `^20.19.0 || >=22.12.0`, as required by the locked UI packages
- npm with support for package-lock format version 3

## Troubleshooting

| Error | Fix |
|---|---|
| `install uv first` | Install uv from https://docs.astral.sh/uv/ and rerun `./run.sh`. |
| `install npm first` or a Node engine error | Install a supported Node.js version listed above, then rerun `./run.sh`. |
| `Address already in use` for port 8000 | Stop the process using port 8000, then rerun `./run.sh`. |

## Project structure

- `run.sh`: Installs locked dependencies, runs the pipeline checks, builds the UI, and starts the local server.
- `common.py`: Defines work paths, SQLite access, masking, and atomic file writes.
- `ingest.py`: Loads source data while preserving operational state.
- `pipeline.py`: Validates tickets and creates work orders, drafts, audit entries, and projections.
- `approve.py`: Applies one local approval transition safely.
- `server.py`: Provides the loopback-only FastAPI API and serves the built UI.
- `ui/`: Contains the React, Vite, and Tailwind dispatcher console.
- `tests/`: Covers security boundaries, ingestion, policy chronology, approvals, and local integration.
