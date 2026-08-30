# [TITAN] Plan: Meridian Ops hardening

- Project: TITAN - Meridian Ops hardening
- Label: titan
- Label color: purple
- Status: Approved for build
- Tracking: Local filesystem

## Request

Fix the audited Meridian Ops issues. Run Agent Titan locally without Linear.

## Plan

### 1. Secure local server boundaries

Owner: [Backend]

- Bind to `127.0.0.1` by default.
- Contain SPA paths inside `ui/dist`, including encoded and symlink traversal.
- Remove client-controlled filesystem paths from `/api/run`.

Acceptance:

- Plain, encoded, and symlink traversal attempts return 404.
- The default server binding is loopback only.
- `/api/run` cannot read arbitrary server paths.

### 2. Make ingestion deterministic and lossless

Owner: [Backend]

- Preserve approvals and persistent state across normal startup.
- Accept JSONL, arrays, and single-object JSON.
- Validate a record before adding its ID to duplicate tracking.
- Reject unknown destinations.
- Mask PII before quarantine, logging, persistence, or API serialization.
- Replace process-global logs with run-scoped logs.
- Write JSONL through temporary files and atomic replacement.

Acceptance:

- A restart retains approvals.
- A malformed duplicate cannot suppress a later valid record.
- Single-object JSON produces one record.
- Unknown destinations are quarantined.
- Raw PII never appears in failure surfaces.
- Interrupted projection does not expose partial JSONL.

### 3. Correct policy chronology

Owner: [Backend]

- Make R5 fail closed when maintenance evidence is missing.
- Implement R6 until the first valid permanent repair event.
- Evaluate R9 from chronological dispatch history, independent of input order.
- Define deterministic behavior for equal or invalid timestamps.

Acceptance:

- R5 blocks candidates with absent maintenance data.
- R6 covers unrepaired, repair-before, and repair-after cases.
- R9 returns the same result for shuffled input.
- Timestamp boundaries have explicit tests.

### 4. Make approval transitions atomic

Owner: [Backend]  
Depends on: 2

- Run one conditional SQLite update inside a transaction.
- Return success only when `rowcount == 1`.
- Return HTTP 409 when another request already won.
- Write the winner's audit row only.
- Regenerate JSONL with the atomic projection helper from piece 2.

Acceptance:

- Two concurrent approvals produce one success and one conflict.
- The winning reviewer and timestamp remain stored.
- Missing or transitioned records return conflict.
- Projection failure cannot corrupt SQLite or expose partial JSONL.

### 5. Complete frontend workflows

Owner: [Frontend]  
Depends on: 1, 4

- Add loading and visible error states to requests.
- Clear busy state with `finally`.
- Make Review file open useful record context without accepting a path.
- Require a local reviewer identity instead of hardcoding one.
- Add accessible labels, keyboard focus behavior, and announced errors.
- Fix narrow viewport overflow and mobile Evaluator access.

Acceptance:

- Failed requests show an error and permit retry.
- Pending actions block duplicate submissions.
- Review file performs a visible action.
- Approval uses the entered reviewer identity.
- Keyboard and mobile viewport checks pass.

### 6. Add regression and local integration coverage

Owner: [QA]  
Depends on: 1, 2, 3, 4, 5

- Add focused tests for each repaired defect.
- Run integration tests in isolated temporary directories.
- Add a local smoke test for ingest, review, approval, restart, and rerun.
- Confirm the suite uses no Linear service or SDK.

Acceptance:

- The existing nine tests still pass.
- New security, ingestion, rule, approval, and UI tests pass.
- The smoke test preserves state across a second run.
- The suite requires no network service.

### 7. README and run guide

Owner: [Docs]  
Depends on: 6

Write the README in this order:

1. One-sentence app description.
2. Exact copy-paste quickstart.
3. URL and expected screen.
4. Requirements.
5. Two or three troubleshooting cases.
6. One-line project structure entries.

Acceptance:

- Every documented command is run exactly as written.
- A clean local run works without Linear.
- Reset instructions distinguish generated outputs from persistent state.

## Dependency order

Pieces 1, 2, and 3 can run together. Piece 4 follows 2. Piece 5 follows 1 and 4. QA runs after implementation. Docs runs last.

## Out of scope

- Production authentication and remote hosting
- Multi-user identity management
- Database replacement or unrelated refactoring
- New business rules beyond correcting R5, R6, and R9
- Restoration of state already deleted before this work
- A visual redesign

## Comments

[Planner] Seven pieces cover containment, persistent ingestion, rule fixes, approval safety, frontend repair, QA, and docs. Linear stays out of the build.

[Reviewer] Planner, step 4 stacks file locks, revisions, and SQLite locking for one state transition. Use one conditional transaction and check rowcount for the 409.

[Planner] Agreed. Step 4 now uses one conditional SQLite update. SQLite handles serialization, and the atomic projection helper covers the file boundary.

[Reviewer] Plan approved.
Watch that only the winning approval transaction writes its audit row and projects JSONL.
