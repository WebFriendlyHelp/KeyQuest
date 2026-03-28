---
name: release-ship
description: Use when preparing or completing a KeyQuest release on Windows. Follows the repo's release policy, verifies Python 3.11 and PowerShell host assumptions, runs the release tooling, and checks dist artifacts plus release-facing docs.
---

# Release Ship

Use this skill for release preparation and shipping.

## Workflow
1. Read:
   - `docs/dev/HANDOFF.md`
   - `docs/dev/CHANGELOG.md`
   - `docs/dev/RELEASE_POLICY.md`
2. Confirm shell health with `tools/codex_exec_diagnostics.ps1` if the host looks unusual.
3. Run baseline validation:
   - `py -3.11 -m pytest -q`
   - `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`
4. Prefer:
   - `powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1`
5. If doing the release manually:
   - bump `modules/version.py`
   - run `powershell -ExecutionPolicy Bypass -File tools/release.ps1`
6. Verify:
   - local `dist/` assets
   - `README.html`
   - `docs/dev/CHANGELOG.md`
   - `docs/user/WHATS_NEW.md`
   - `docs/dev/HANDOFF.md`

## Notes
- The repo is Windows-only and expects Python 3.11.
- Reuse the current PowerShell host rather than assuming Windows PowerShell 5.1 is healthy.

