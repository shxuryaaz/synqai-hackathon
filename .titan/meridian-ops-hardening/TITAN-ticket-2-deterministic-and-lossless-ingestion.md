# [TITAN] [meridian-ops-hardening] Deterministic and lossless ingestion

- Status: Todo
- Label: titan
- Owner: [Backend]
- Dependencies: None

## Description

Preserve approvals and persistent state while accepting JSONL, arrays, and single-object JSON safely.
Validate, quarantine, mask, log, and project records deterministically without exposing partial data.

## Acceptance criteria

- A restart retains approvals.
- A malformed duplicate cannot suppress a later valid record.
- Single-object JSON produces one record.
- Unknown destinations are quarantined.
- Raw PII never appears in failure surfaces.
- Interrupted projection does not expose partial JSONL.

## Comments
