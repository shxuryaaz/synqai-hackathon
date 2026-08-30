# [TITAN] [meridian-ops-hardening] README + run guide

- Status: Done
- Label: titan
- Owner: [Docs]
- Dependencies: 6

## Description

Write a concise README with the app description, exact quickstart, expected screen, and requirements.
Include troubleshooting, project structure, and clear reset guidance for generated and persistent data.

## Acceptance criteria

- Every documented command is run exactly as written.
- A clean local run works without Linear.
- Reset instructions distinguish generated outputs from persistent state.

## Comments

[Docs] Rewrote the README in the approved order and made `run.sh` require npm before running the locked `npm ci` UI build.

[Docs] Ran `./run.sh`: 35 records processed with 0 exceptions, 0 PII leaks, an identical five-file rerun, a successful UI build, and a loopback-only server. `/` and `/api/stats` returned HTTP 200. The server then shut down cleanly. Ran the exact reset command in an isolated empty work directory; it exited 0 and removed the generated directories without touching project state.

[Reviewer] Requirements match both lockfiles. Reset guidance separates generated data from persistent SQLite state.
