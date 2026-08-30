# [TITAN] [meridian-ops-hardening] Complete frontend workflows

- Status: Done
- Label: titan
- Owner: [Frontend]
- Dependencies: 1, 4

## Description

Complete request, review, and approval workflows with visible loading, error, retry, and reviewer states.
Add accessible keyboard behavior and correct narrow viewport access without accepting filesystem paths.

## Acceptance criteria

- Failed requests show an error and permit retry.
- Pending actions block duplicate submissions.
- Review file performs a visible action.
- Approval uses the entered reviewer identity.
- Keyboard and mobile viewport checks pass.

## Comments

- [Frontend] Added resilient shared API errors, retryable loading and mutation states, local reviewer identity, safe in-page file review, and keyboard and dialog accessibility.
- [Frontend] Exposed Evaluator on mobile and verified no horizontal overflow at 320px or 768px.
- [Frontend] `npm run build` passed. `npm run lint` passed with three existing Fast Refresh warnings for mixed exports in `ui.jsx`.
- [Frontend] Reviewer follow-up: hardening tick-driven loaders so stale requests cannot replace current data or loading state.
- [Frontend] Added request sequencing and cleanup invalidation to every data loader. Only the newest request can update data, errors, or loading state. Build and lint passed after the fix.
- [QA] Live mobile review found the fixed navigation overlapping Attention actions at 390px.
- [Frontend] Increased mobile content clearance so the final action row scrolls fully above the fixed navigation.
