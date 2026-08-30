# [TITAN] [meridian-ops-hardening] Regression and local integration coverage

- Status: Todo
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
