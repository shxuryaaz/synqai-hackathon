# [TITAN] [meridian-ops-hardening] Atomic approval transitions

- Status: Todo
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
