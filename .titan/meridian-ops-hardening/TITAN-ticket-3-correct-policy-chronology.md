# [TITAN] [meridian-ops-hardening] Correct policy chronology

- Status: Todo
- Label: titan
- Owner: [Backend]
- Dependencies: None

## Description

Correct R5, R6, and R9 so policy decisions use complete chronological evidence.
Define deterministic outcomes at equal or invalid timestamp boundaries.

## Acceptance criteria

- R5 blocks candidates with absent maintenance data.
- R6 covers unrepaired, repair-before, and repair-after cases.
- R9 returns the same result for shuffled input.
- Timestamp boundaries have explicit tests.

## Comments
