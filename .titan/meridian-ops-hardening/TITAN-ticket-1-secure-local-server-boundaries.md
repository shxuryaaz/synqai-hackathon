# [TITAN] [meridian-ops-hardening] Secure local server boundaries

- Status: Done
- Label: titan
- Owner: [Backend]
- Dependencies: None

## Description

Restrict the local server to loopback and contain SPA paths inside `ui/dist`.
Remove client-controlled filesystem paths from `/api/run`.

## Acceptance criteria

- Plain, encoded, and symlink traversal attempts return 404.
- The default server binding is loopback only.
- `/api/run` cannot read arbitrary server paths.

## Comments

- [Backend] Started implementation and focused security tests.
- [Backend] Restricted server paths and loopback binding.
- [Backend] Focused and full test suites passed.
- [Backend] QA confirmed an unsafe symlinked SPA fallback. Fixing containment.
- [Backend] Resolved fallback containment. All tests pass.
