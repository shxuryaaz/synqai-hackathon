# [TITAN] [meridian-ops-hardening] Atomic approval transitions

- Status: Done
- Label: titan
- Owner: [Backend]
- Dependencies: 2

## Description

Use one conditional SQLite update in a transaction so only one approval request can win.
Record and project only the winning transition through the atomic helper from ticket 2.

## Acceptance criteria

- Two concurrent approvals produce one success and one conflict.
- The winning reviewer and timestamp remain stored.
- Missing or transitioned records return conflict.
- Projection failure cannot corrupt SQLite or expose partial JSONL.

## Comments

[Backend] Implemented the pending to sent transition as one conditional SQLite update. Success requires rowcount 1. The winning transaction writes the only approval audit row and runs atomic JSONL projection before commit, so projection errors propagate and roll back SQLite. Missing and transitioned records raise approval conflicts, and the FastAPI endpoint returns HTTP 409. Replaced the PII assert with explicit validation. Added separate connection and thread concurrency coverage, winner identity checks, API conflict checks, audit count checks, and projection rollback coverage. Focused tests: 5 passed in 0.68s. Full tests: 43 passed in 2.95s.

[Backend] Reopened after QA and Reviewer identified that a late multi-file replacement failure could leave JSONL ahead of rolled back SQLite state. Moving projection after the winner transaction commits and upgrading the shared projection helper to stage every destination before replacement and restore prior destinations on failure.

[Backend] Fixed the late projection failure. SQLite now commits the winning approval and audit before projection. The shared JSONL batch helper fully stages replacements and backups, then restores every replaced destination to its prior bytes or prior absence if any later replacement fails. Projection exceptions still propagate, so the API cannot report success. The regression fails comms_sent replacement after work_orders and comms_pending were replaced, then verifies the committed SQLite winner, one audit row, exact restoration of all JSONL destinations, prior absence restoration, and parseable files. Focused tests: 6 passed in 0.71s. Full tests: 43 passed in 3.24s.

[Backend] Reopened after Reviewer found that cleanup removed a backup when its restoration failed. Preserving failed recovery backups and reporting their paths alongside the original projection error.

[Backend] Fixed recovery cleanup. Backups consumed by successful restoration are cleaned, while a backup whose restore fails is preserved at its temporary path. Recovery now raises an ExceptionGroup containing the original projection exception and clear restore failure details with the preserved backup path. Added a focused double-failure test that verifies the original exception identity, prior backup bytes, exposed recovery path, successful backup cleanup, and complete parseable destinations. Focused tests: 7 passed in 0.70s. Full tests: 44 passed in 3.74s.

[Backend] Reopened after Reviewer found that an unlink error during final cleanup could replace the active projection or recovery error. Collecting cleanup failures with the active error and preserving all original exception objects.

[Backend] Fixed cleanup error handling. Every eligible temp and backup cleanup is attempted, with failures collected instead of replacing the active projection or recovery error. Combined failures are raised in one ExceptionGroup, cleanup-only failures raise a clear ExceptionGroup, original exception objects remain inspectable, and preserved failed-restore backups are never unlinked. Added regressions for projection plus unlink failure and cleanup-only failure. Focused tests: 9 passed in 0.64s. Full tests: 46 passed in 2.90s.

[Backend] Reopened after Reviewer found edited body PII was masked before validation and therefore silently accepted. Moving raw edit validation ahead of masking and database access, retaining final draft validation, and adding a distinct API client error.

[Backend] Fixed edited body validation order. Raw edits are checked for recognized PII before masking or database access, and the final stored or draft body is still checked before the approval transaction. ApprovalValidationError maps to HTTP 422 while state conflicts remain HTTP 409. Added direct and API phone and Aadhaar rejection tests plus a python -O regression, all proving pending state, audit rows, and projections remain unchanged. Focused tests: 14 passed in 0.76s. Full tests: 51 passed in 3.02s.

[Backend] Reopened after Reviewer found approval database handles were not closed. Wrapping the full database-backed flow in an explicit closing context while retaining the inner transaction and post-commit projection.

[Backend] Fixed approval connection lifetime with contextlib.closing around the complete database-backed flow. The SQLite transaction still commits before projection, and success, conflict, final stored-body PII rejection, transaction failure, and projection failure all close the handle. Added a connection spy test that verifies close and proves the underlying connection rejects later use. Focused tests: 19 passed in 0.80s. Full tests: 56 passed in 3.09s.
