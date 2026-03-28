---
name: session-start
description: Use when starting a new KeyQuest session in Codex, the CLI, or the app. Reads the canonical handoff and latest changelog entry, confirms the repo root and Python 3.11 baseline, and runs the standard local validation commands before feature work.
---

# Session Start

Use this skill at the beginning of a KeyQuest work session.

## Workflow
1. Confirm the repo root contains `.git`, `pyproject.toml`, and `keyquest.pyw`.
2. Read `docs/dev/HANDOFF.md`.
3. Read the newest entry in `docs/dev/CHANGELOG.md`.
4. Confirm Python 3.11 is the active project baseline.
5. Run:
   - `py -3.11 -m pytest -q`
   - `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`
6. Summarize:
   - current repo state
   - any failing checks
   - files most relevant to the requested task

## Notes
- If shell behavior looks stripped down or broken on Windows, use the `windows-shell-repair` skill first.
- If the task is release-related, also load `release-ship`.

