# [TITAN] [meridian-ops-hardening] Regression and local integration coverage

- Status: Done
- Label: titan
- Owner: [QA]
- Dependencies: 1, 2, 3, 4, 5

## Description

Add focused regression tests and isolated local integration coverage for every repaired defect.
Exercise ingest, review, approval, restart, and rerun without Linear or another network service.

## Acceptance criteria

- The existing nine tests still pass.
- New security, ingestion, rule, approval, and UI tests pass.
- The smoke test preserves state across a second run.
- The suite requires no network service.

## Comments

- [QA] PASS: 58 backend tests; no-network integration preserved TKT-2001 approval across an ingest restart.
  Frontend lint/build passed with 3 existing Fast Refresh warnings. Isolated PII scan found 0 leaks; rerun found 0 differences across 5 files.
  No Linear imports, dependencies, service markers, or socket connections were observed.