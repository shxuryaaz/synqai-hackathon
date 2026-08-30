# [TITAN] [meridian-ops-hardening] Deterministic and lossless ingestion

- Status: Done
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

- [Backend] Started implementation and focused ingestion tests.
- [Backend] Preserved operational tables, hardened ingestion boundaries, and made JSONL projection atomic.
- [Backend] Focused tests passed: 10 passed.
- [Backend] Full test suite passed: 22 passed.
- [Backend] QA and Reviewer reproduced list fields being mistaken for wrapper payloads. Fixing wrapper detection and adding regression coverage.
- [Backend] Valid ticket objects now take precedence over explicit wrapper keys. Focused tests passed: 12 passed. Full suite passed: 24 passed.
