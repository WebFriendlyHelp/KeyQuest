# KeyQuest Agent Guide

Start here for any Codex, CLI, or app session in this repo.

Primary sources of truth
- Read `docs/dev/HANDOFF.md` first.
- Read the top entry in `docs/dev/CHANGELOG.md` next.
- Treat `modules/version.py` as the version source of truth.

Session-start baseline
1. Confirm you are at the repo root.
2. Read `docs/dev/HANDOFF.md`.
3. Read the newest `docs/dev/CHANGELOG.md` entry.
4. Run:
   - `py -3.11 -m pytest -q`
   - `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`

Windows and environment rules
- This project is Windows-only.
- Prefer PowerShell-based tooling already in the repo.
- If shell commands behave as if core Windows env vars are missing, use `tools/env_bootstrap.ps1`.
- If Codex shell health is in doubt, run `powershell -ExecutionPolicy Bypass -File tools/codex_exec_diagnostics.ps1`.
- Keep source, tests, packaging, and release workflows aligned to Python 3.11.

Recommended Codex permission rules
- Safe candidates for persistent approval are the repo's repeatable validation and diagnostics commands:
  - `py -3.11 -m pytest -q`
  - `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`
  - `powershell -ExecutionPolicy Bypass -File tools/codex_exec_diagnostics.ps1`
  - `powershell -ExecutionPolicy Bypass -File tools/run_local_updater_integration.ps1`
- Read-only inspection commands are also good candidates when the host still prompts for them:
  - `git status --short`
  - `git diff -- ...`
  - `rg ...`
- Do not persist approval for destructive or publishing commands unless the current task explicitly requires them:
  - `Remove-Item`, `git reset`, installer cleanup, release publishing, or commands that push tags/releases to GitHub

Parallel workflow guidance
- Use parallel agent work only when tasks are independent and have disjoint write sets.
- Good parallel splits in this repo:
  - code change plus docs sync
  - updater code change plus local harness verification
  - GitHub triage plus local implementation
- Keep the blocking task in the main session when the next action depends on it immediately.
- Avoid parallel edits against the same files unless the user explicitly wants coordinated merge work.
- For GitHub-heavy sessions, prefer this pattern:
  - one agent gathers remote state (PRs, issues, CI, comments)
  - one local workflow handles repo-specific validation or implementation

Repo workflow rules
- For user-visible behavior changes, update:
  - `README.html`
  - `docs/dev/CHANGELOG.md`
- For release work, also update:
  - `docs/user/WHATS_NEW.md`
  - `docs/dev/HANDOFF.md`
- Do not treat local-only helper content under `local/` as tracked product assets unless explicitly asked.

Codex workflow assets in this repo
- Repo config: `.codex/config.toml`
- Workflow guide: `docs/dev/CODEX_GITHUB_WORKFLOW.md`
- Default GitHub-side pair for maintainer work: `pr-review` for PRs and `issue-tracker` for issues/comments
- Repo-shared skills:
  - `.codex/skills/session-start/`
  - `.codex/skills/windows-shell-repair/`
  - `.codex/skills/updater-harness/`
  - `.codex/skills/docs-sync/`
  - `.codex/skills/release-ship/`
  - `.codex/skills/maintainer-inbox/`

Implementation focus
- Main entrypoint: `modules/keyquest_app.py`
- Games: `games/`
- UI helpers: `ui/`
- Build and release tooling: `tools/`
- Canonical developer context: `docs/dev/`

Search and verification notes
- Prefer `rg` when available.
- If `rg` is unavailable in the active shell, note that in your summary and use PowerShell fallback commands.
- For OpenAI API, Codex-product, or model-selection questions, use the `openai-docs` skill and prefer current official docs.
- Keep general Windows/Codex workflows in global skills and keep repo-local skills lean and KeyQuest-specific.
