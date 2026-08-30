# [TITAN] [meridian-ops-hardening] Correct policy chronology

- Status: Done
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

[Backend] Implemented R5 maintenance evidence rejection, R6 permanent repair chronology with the 7-day deadline, and R9 issue-to-next-dispatch chronology. Ticket records now process in deterministic timestamp order, mixed ISO timestamps normalize to UTC, issue events precede dispatches at equal timestamps, and invalid evidence timestamps do not affect policy decisions. Maintenance is date-only in the source, so a repair on the dispatch date does not prove it occurred before dispatch.

[Backend] Added direct coverage for missing and invalid maintenance history, the 30-day service boundary, unrepaired and repaired jugaad cases, repairs before, on, and after dispatch, patches older than 7 days, shuffled records, latest-event selection, cancelled and invalid dispatches, and equal timestamps. Focused result: 9 passed. Full result: 33 passed.

[QA] Reopened after finding out-of-range numeric timestamps can raise OverflowError during sorting.

[Reviewer] Reopened because R6 must match the repaired component to the latest patch and fail closed when the component cannot be identified.

[Backend] Fixed numeric timestamp overflow by treating out-of-range values as invalid evidence, so sorting remains deterministic and ticket processing quarantines them as bad dates. R6 now extracts one of the 20 component phrases present in maintenance notes and only clears the latest patch for a later-day repaired or replaced event naming the same component. Unknown components fail closed, and repairs dated on the dispatch day do not clear a patch because maintenance has day precision.

[Backend] Added regressions for unrelated and matching component repairs, latest-patch selection, unknown components, strict later-day repair chronology, and out-of-range timestamp sorting and quarantine. Focused result: 12 passed in 0.03s. Full result: 36 passed in 3.14s.

[Reviewer] Reopened because R6 must evaluate every temporary patch, not only the latest patch across all components.

[Backend] R6 now evaluates every temporary patch up to dispatch. Each known component patch requires a strict later-day matching repaired or replaced event before dispatch, a later patch reopens that component, and each unknown-component patch remains unresolved. Cross-region rejection reports the earliest unresolved patch by maintenance date and source row, giving a stable deadline.

[Backend] Added coverage for a repaired newest component with an older component still open, all components repaired, and repair followed by a new patch. Focused result: 15 passed in 0.04s. Full result: 39 passed in 3.03s.
