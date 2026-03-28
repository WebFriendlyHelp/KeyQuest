---
name: updater-harness
description: Use when changing or verifying KeyQuest's updater on Windows. Runs the local updater integration harness, checks strict portable coverage, and summarizes the saved report and evidence files under tests/logs/local_updater.
---

# Updater Harness

Use this skill for updater changes, regressions, or release verification.

## Workflow
1. Read the updater status in `docs/dev/HANDOFF.md`.
2. Review the latest updater-related changelog entry in `docs/dev/CHANGELOG.md`.
3. Run focused tests first:
   - `py -3.11 -m pytest -q tests/test_update_manager.py`
4. For integration coverage, run:
   - `powershell -ExecutionPolicy Bypass -File tools/run_local_updater_integration.ps1`
   - include strict portable mode when relevant
5. Summarize:
   - installer result
   - portable result
   - strict portable result if run
   - saved evidence paths under `tests/logs/local_updater/`

## Evidence paths
- `tests/logs/local_updater/REPORT.md`
- `tests/logs/local_updater/result.json`
- `tests/logs/local_updater/REPORT_strict_portable.md`
- `tests/logs/local_updater/result_strict_portable.json`
