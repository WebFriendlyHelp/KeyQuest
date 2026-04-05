# KeyQuest Handoff (Canonical Context)

This is the single starting point for any human or AI working on KeyQuest.

## Snapshot

- **Last updated**: 2026-04-05 (updater reliability fixes — .bat shim for execution policy, temp cleanup, .keyquest-installed marker)
- **Version**: see `modules/version.py` (single source of truth)
- **Platform**: Windows only
- **Accessibility**: See user accessibility docs in `docs/user/`.
- **Git status**: previous notes about GitHub push being blocked by hostname-resolution errors are stale. A March 27, 2026 verification from this machine showed `git status --short --branch` reporting `## main...origin/main` once missing Windows environment variables were restored in the embedded Codex shell.

## Next Session Checklist

1. Open `docs/dev/HANDOFF.md` and `docs/dev/CHANGELOG.md` top entry.
2. Run baseline checks before editing:
   - `py -3.11 -m pytest -q`
   - `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`
3. If changing user-visible behavior, update:
   - `README.html` (and pointer `README.md` only if needed)
   - `docs/dev/CHANGELOG.md` — technical detail (file names, functions, implementation notes)
4. For release work:
   - Update `docs/user/WHATS_NEW.md` — plain English only, no code/file names
   - Prefer `powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1`
   - Or bump `modules/version.py` manually and run `powershell -ExecutionPolicy Bypass -File tools/release.ps1`
   - Both scripts skip local builds — CI builds and publishes all artifacts automatically
   - Monitor the release at: https://github.com/WebFriendlyHelp/KeyQuest/actions
5. Before handoff:
   - Update this handoff file snapshot + recent changes
   - Commit and push to `main`
   - If releasing, verify GitHub release page and asset links

## Quick Start (For New Sessions)

1. Read this file.
2. Read the top entry in `docs/dev/CHANGELOG.md`.
3. Start implementation from `modules/keyquest_app.py` and the relevant `modules/*` or `games/*` file.

## Repo Map (Where Things Live)

- `keyquest.pyw`: thin entrypoint (runs `modules/keyquest_app.py`).
- `modules/keyquest_app.py`: main application event loop and screen wiring.
- `modules/`: state, lessons, audio, dialogs, menu, shop/pets, etc.
- `games/`: game implementations (`base_game.py`, `letter_fall.py`, `word_typing.py`).
- `ui/`: rendering helpers.
- `Sentences/`: sentence/topic text pools.
- `.codex/config.toml`: tracked Codex project config for repo-root detection and handoff fallback when `AGENTS.md` is absent.
- `docs/`: user and developer docs.
- `tools/build/`: batch build scripts and PyInstaller spec.
- `tools/quality/`: quality scripts (contrast audit).

## Run / Test / Build

- Install deps: `pip install -r requirements.txt`
- Run app: `py -3.11 keyquest.pyw`
- Run tests: `py -3.11 -m pytest -q`
- Local quality checks: `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`
- Build exe: `tools/build/build_exe.bat`
- Build installer: `tools/build/build_installer.bat` (requires Inno Setup 6)
- Full release: `powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1`
- Build source package: `tools/build/create_source_package.bat`
- Single build entrypoint:
  - `powershell -ExecutionPolicy Bypass -File tools/build.ps1 -Target all -Clean` (exe + source)
  - `powershell -ExecutionPolicy Bypass -File tools/build.ps1 -Target installer` (installer only)
- EXE packaging docs policy: include `README.md`, `README.html`, and user-facing docs under `dist/KeyQuest/docs/`.
- Release policy: `docs/dev/RELEASE_POLICY.md`
- Windows source-launch safeguard: `keyquest.pyw` now relaunches itself with Python 3.11 if file association starts it with a different Python install.
- Python baseline policy: keep source, workflows, linting, and packaging aligned to Python 3.11 for consistency and TTS compatibility.
- Codex environment note: this machine was updated to Codex `0.117.0` on 2026-03-27. That upstream release changed plugin/skill loading behavior, so if a future session hits `skipped loading skill`, compare the exact wording against the post-0.117.0 behavior before assuming it is a repo issue.
- Repo-shared Codex workflow assets now exist:
  - `AGENTS.md`
  - `docs/dev/CODEX_GITHUB_WORKFLOW.md`
  - `.codex/skills/session-start/SKILL.md`
  - `.codex/skills/windows-shell-repair/SKILL.md`
  - `.codex/skills/updater-harness/SKILL.md`
  - `.codex/skills/docs-sync/SKILL.md`
  - `.codex/skills/release-ship/SKILL.md`
  - `.codex/skills/maintainer-inbox/SKILL.md`
  - `tools/codex_exec_diagnostics.ps1`
- Default GitHub-side pair for maintainer work:
  - `pr-review` for PRs
  - `issue-tracker` for issues and contributor-comment follow-up
- Recommended Codex permission-rule allowlist for this repo:
  - safe to approve persistently: `py -3.11 -m pytest -q`, `powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1`, `powershell -ExecutionPolicy Bypass -File tools/codex_exec_diagnostics.ps1`, `powershell -ExecutionPolicy Bypass -File tools/run_local_updater_integration.ps1`
  - generally safe when prompts appear: read-only inspection commands such as `git status --short`, `git diff -- ...`, and `rg ...`
  - keep one-off approval for destructive or publishing commands (`Remove-Item`, `git reset`, build cleanup, tag/release publication)
- Recommended parallel-agent pattern for this repo:
  - only split tasks that are independent and have disjoint write sets
  - strong candidates: code change plus docs sync, updater changes plus harness verification, GitHub triage plus local implementation
  - keep immediate blockers in the main session instead of waiting on a delegated result
  - avoid parallel edits in the same file set unless the task is explicitly organized that way
- For OpenAI API, Codex-product, or model-selection questions:
  - use the `openai-docs` skill first
  - prefer current official OpenAI docs over repo memory
  - use `docs/dev/CODEX_GITHUB_WORKFLOW.md` for stable-vs-alpha guidance, model-selection defaults, and GitHub-agent routing
- Skill organization rule:
  - keep general Windows/Codex workflows in global skills
  - keep repo-local skills lean and KeyQuest-specific

## Current Status (High Level)

- Core app + Phases 1-4 features implemented.
- Updater local integration harness is now passing for both installer and portable paths.
- Current saved run is the stricter portable configuration with both harness-only portable overrides disabled:
  - `tests/logs/local_updater/REPORT.md`
  - `tests/logs/local_updater/result.json`
  - `tests/logs/local_updater/REPORT_strict_portable.md`
  - `tests/logs/local_updater/result_strict_portable.json`
  - `modules/update_manager.py`: added local release URL override support (`KEYQUEST_UPDATE_RELEASE_URL`), explicit installed-layout detection (`unins*.exe` / `.keyquest-installed`), and installer launcher now passes `/DIR="%APP_DIR%"`.
  - `modules/update_controller.py`: update checks now honor the local release URL override.
  - `tests/run_local_updater_integration.py`, `tests/updater_fixture_app.py`, `tools/run_local_updater_integration.ps1`: added a repeatable local installer-path updater harness that uses a fake local feed and fixture executables instead of GitHub.
  - `tests/test_update_manager.py`: added assertions for `/DIR="%APP_DIR%"`, installed-layout detection, and the update URL override.
  - `tools/build/KeyQuest-RootFolders.spec`: temporary packaging change to exclude `pkg_resources` / `setuptools` / `jaraco` from the built EXE while debugging a local packaging crash (`pyi_rth_pkgres` / missing `jaraco`).
  - `modules/update_manager.py` launcher scripts now prefer `cmd start` for restart and only fall back to PowerShell if `start` fails, which made the local harness pass on this machine.
- `modules/update_manager.py` portable launcher now:
  - skips sentence merge cleanly if either source or target folder is missing
  - validates that extraction actually produced `%EXTRACT_DIR%\KeyQuest`; if PowerShell `Expand-Archive` exits without creating that tree, the launcher logs the condition and falls back to `tar`
  - copies `KeyQuest.exe` as a separate retried step after `robocopy`, instead of letting a transient EXE lock fail the whole portable update
  - uses `ping`-based sleeps in the detached helper instead of `timeout /t`, because `timeout` is unreliable in this environment and was collapsing retry loops
- Current saved harness result: pass for installer and portable paths with strict portable mode enabled. The saved artifacts show detection, download, update handoff, and relaunch into `1.9.1` for both layouts even when both portable test-only overrides are disabled.
- Release prep status:
  - `modules/version.py` is now staged at `1.15.1` for the updater relaunch fix release.
  - `docs/user/WHATS_NEW.md` has a new top `1.15.1` plain-language entry telling users this patch fixes the close-and-never-reopen updater failure and that older affected installs may need one manual install first.
  - `tests/run_local_updater_integration.py` now writes PowerShell launcher scripts as `.ps1`, launches them through PowerShell, and writes strict portable evidence to dedicated files instead of overwriting the default report paths.
  - Push/PR GitHub automation is now consolidated into `.github/workflows/ci.yml`; the overlapping `.github/workflows/tests.yml` workflow was removed after folding its quality-check coverage into `ci.yml`.
  - `tools/ship_updates.ps1` now blocks accidental double bumps: if `modules/version.py` is already modified, maintainers must publish with `tools/release.ps1` instead of the auto-bump wrapper.
- New user-facing guide is now `README.html` (plain-language, WCAG-friendly structure). `README.md` is a pointer.
- Built-in sentence topics are now driven by `Sentences/manifest.json` with schema/docs in `docs/dev/CONTENT_MANIFEST.md` and `docs/dev/schemas/sentences-manifest.schema.json`.
- Speed Test setup now uses a single source list with `Random Topic` plus the regular manifest-driven practice topics; the separate dedicated speed-test branch was removed from the UI.
- Speed Test source ordering now keeps `General`, `Random Topic`, and `General Spanish` grouped together near the top. Random-topic mode for both Speed Test and Sentence Practice is English-only by topic name, but still includes other extra English sentence files.
- Keyboard command sentence files were cleaned up for clearer, less technical wording.
- Blog-post helper content is now maintained locally outside Git and should not be treated as a tracked repo asset.
- Hangman is fully integrated and significantly expanded:
  - offline dictionary-backed words/definitions
  - weighted word-length selection centered on common lengths, with occasional short and very long words
  - 10 wrong-guess visual stages with spoken stage descriptions
  - comma-separated spoken word progress tokens for clearer SR pacing
  - Left/Right/Home/End cursor navigation across word-progress positions with visual focus highlight
  - results menu with `Word`, `Definition`, copy action, replay, and sentence-practice bridge
  - sentence-practice prompts use varied style templates (story/mystery/science/etc.) instead of plain repetitive lines
  - sentence-practice `Ctrl+Space` reads remaining text from current typing position
  - `Alt+L` reports letters left and total letters
- Speech formatting is now consistent for repeated letters, spaces, and mismatch feedback.
- Lesson prompts now speak authored practice words naturally, while drill patterns such as `asas` or `aass` are spelled out.
- Early lessons now front-load simpler 2, 3, and 4 key repeated drills before mixed patterns.
- Sentence Practice `Random Topic` excludes Spanish topics; Spanish is still available via `Choose Topic`.
- `Escape x3` return to Main Menu is implemented across active non-menu modes.
  - Escape handling is centralized via `modules/escape_guard.py` + policy routing in `modules/keyquest_app.py`.
- Main menu labels/order updated (`Quests`, `Pets`, `Pet Shop`, `Badges`).
- Main menu now includes `About` (menu-driven info screen with website launch action).
- Word Typing countdown stutter at 10s/5s fixed.
- Startup speech ordering stabilized (title first via SR, then first menu item).
- Fixed slow first down-arrow announcement caused by startup speech protection window.
- Added fixed 250 ms duplicate-speech debounce to reduce stutter/repeats.
- Added spoken/visual goodbye message on app exit.

## Active TODOs / Open Issues

1. Continue modularization of `modules/keyquest_app.py` where practical — `flash_manager` and `font_manager` are extracted; mode dispatch and cross-mode wiring remain candidates.
2. Keep docs in sync with active file layout under `tools/build/` and `tools/quality/`.
3. Keep the local updater evidence current:
   - Review `tests/logs/local_updater/REPORT.md` and `tests/logs/local_updater/result.json`.
   - Current saved run passes all 22 stages with `--strict-portable`, including relaunch into the new version after a real `tar` fallback and EXE-copy retry.
   - Saved evidence:
     - `tests/logs/local_updater/REPORT.md`
     - `tests/logs/local_updater/result.json`
     - `tests/logs/local_updater/REPORT_strict_portable.md`
     - `tests/logs/local_updater/result_strict_portable.json`
     - `tests/logs/local_updater/installed_app/keyquest_error.log`
     - `tests/logs/local_updater/installed_app/fake_installer_trace.json`
     - `tests/logs/local_updater/portable_app/keyquest_error.log`
     - `tests/logs/local_updater/portable_app/keyquest_error_strict_portable.log`
   - Previous machine-level blockers (now resolved after Winsock reset + reboot):
     - `py -3.11 -m pytest` and `asyncio` imports previously failed with `OSError: [WinError 10106]`. Fixed after `netsh winsock reset` + reboot.
     - `py -3.11 -m pytest -q` now passes all 331 tests green.
   - Remaining known quirk: Windows PowerShell 5.1 still fails to initialize (`8009001d`) in this environment, but the portable updater tolerates it (tar fallback + `start` restart).
   - The harness still supports the two portable test-only env vars, but the current strict run proves they are no longer required.

## Key Conventions

- Use `self.speech.say("...", priority=True, protect_seconds=2.0)` for important announcements.
- Keep visual and spoken content aligned.
- Use `get_app_dir()` for runtime-safe path resolution (source and frozen exe).
- **Two-changelog pattern** — both files must be updated on every release; neither replaces the other:
  - `docs/dev/CHANGELOG.md` — developer/technical changelog. Updated for every meaningful change with file names, function names, and implementation detail. This is the file AI assistants should update during feature/fix work.
  - `docs/user/WHATS_NEW.md` — user-facing plain-English summary. Updated at release time only, describing what changed in terms a non-technical user can understand. No file names or code details.
  - The in-app **What's New** menu item links to `changelog.html` on GitHub Pages (generated from these files), not the raw markdown directly. The URL is `PAGES_CHANGELOG_URL` in `modules/keyquest_app.py`.
- Update `docs/dev/CHANGELOG.md`, `docs/user/WHATS_NEW.md`, and `docs/dev/HANDOFF.md` for meaningful behavior changes.
- For new screens, use `ui/layout.py` for screen size, centering, wrapped blocks, and footer placement.
- For new game chrome, use `ui/game_layout.py` for titles and status stacks.
- Do not hardcode `900`, `600`, `450`, or assume a single-line controls footer in new render code unless there is a documented reason.

## Recent Changes

### 2026-03-28: Tracked AGENTS.md, Repo-Shared Skills, and Diagnostics Script

- Added tracked root `AGENTS.md` so Codex has a repo-native instruction entrypoint.
- Added repo-shared Codex skills under `.codex/skills/` for:
  - session start
  - Windows shell repair
  - updater harness runs
  - docs sync
  - release shipping
  - maintainer inbox passes
- Added `tools/codex_exec_diagnostics.ps1`:
  - dot-sources `tools/env_bootstrap.ps1`
  - reports PowerShell host details, PATH, repaired environment variables, command availability, UTF-8 state, and repo marker detection
- Follow-up tooling hardening:
  - `tools/codex_exec_diagnostics.ps1` now falls back cleanly when Windows PowerShell 5.1 does not expose `[Environment]::ProcessPath`
  - `tools/env_bootstrap.ps1` now normalizes console/pipeline encoding to UTF-8
  - `tools/env_bootstrap.ps1` now adds a discovered `rg.exe` path from the local Codex or Dyad install if present
- This reduces repeated session setup work and turns the earlier recommendations for repo-shared Codex workflow assets into tracked project files.

### 2026-03-27: Codex 0.117.0 environment note

- This machine's Codex install was updated to `0.117.0` on 2026-03-27.
- Upstream release notes for the corresponding `rust-v0.117.0` tag call out plugin-first workflows, plugin-backed mention fixes, and default rollout of plugin/app flags.
- Practical implication for future sessions: a `skipped loading skill` message may now reflect Codex/plugin gating behavior rather than a KeyQuest repo regression, so capture the exact post-update error text before changing repo files.

### 2026-03-24: Strict Portable Updater Pass and Detached-Helper Fallbacks

- `modules/update_manager.py`:
  - Portable extraction now validates that `%EXTRACT_DIR%\KeyQuest` exists after `Expand-Archive`; if not, it logs the missing tree and falls back to `tar` even when PowerShell does not return a useful non-zero exit code.
  - Portable replacement now copies `KeyQuest.exe` as a separate retried step after `robocopy` so a transient EXE lock does not fail the whole update.
  - Detached helper sleeps now use `ping` instead of `timeout /t`, because `timeout` is unreliable in this environment and was collapsing the retry loops.
- `tests/run_local_updater_integration.py`: added `--strict-portable` so the same harness can rerun the portable path with both test-only overrides disabled.
- `tools/run_local_updater_integration.ps1`: added `-StrictPortable` passthrough.
- `tests/logs/local_updater/REPORT.md`, `tests/logs/local_updater/result.json`: current saved result is now a full 22/22 pass with strict portable mode enabled.
- `tests/logs/local_updater/portable_app/keyquest_error.log`: shows the real portable sequence on this machine:
  - `Expand-Archive did not produce the extracted app tree. Trying tar fallback.`
  - `Portable KeyQuest.exe replacement is still locked. Retrying.`
  - `Portable KeyQuest.exe replacement succeeded.`
  - `Portable update launcher finished.`

### 2026-03-24: Winsock Fixed Post-Reboot

- Winsock reset (`netsh winsock reset`) + reboot resolved `OSError: [WinError 10106]` for `_overlapped` / `asyncio`.
- `py -3.11 -m pytest -q` now passes all 331 tests green.
- Fixed one stale test assertion in `tests/test_update_manager.py`: the portable launcher robocopy exclusion check now correctly matches the `%ROBOCOPY_EXCLUDES%` variable form used in the generated script.

### 2026-03-24: Local Updater Harness, Install-Kind Detection, and Portable Coverage

- `modules/update_manager.py`:
  - Added `UPDATE_URL_OVERRIDE_ENV = "KEYQUEST_UPDATE_RELEASE_URL"` and `get_configured_release_url()` so the updater can target a fake local release feed without changing production defaults.
  - Added `is_installed_layout()` and changed `is_portable_layout()` to return `False` for installer-based layouts that contain `unins*.exe` or `.keyquest-installed`.
  - Updated the generated installer launcher to pass `/DIR="%APP_DIR%"` when starting `KeyQuestSetup.exe`, so local and real installers are told exactly which app folder to replace.
  - Updated both generated launcher scripts to restart KeyQuest with `start "" "%APP_EXE%"` first and only fall back to PowerShell if `start` fails. This avoids the local PowerShell-host failure from blocking relaunch.
  - Added `UPDATER_TEST_PYTHON_ENV = "KEYQUEST_UPDATER_TEST_PYTHON"` and `UPDATER_TEST_SKIP_EXE_COPY_ENV = "KEYQUEST_UPDATER_SKIP_EXE_COPY"` for harness-only portable-path fallbacks.
  - Portable launcher now skips sentence merge when either side is missing, tries the optional Python ZIP extraction override before PowerShell / `tar`, and can optionally exclude `KeyQuest.exe` from the portable `robocopy` step in harness runs.
- `modules/update_controller.py`: `check_for_update()` now receives `update_manager.get_configured_release_url()` so the running app can be pointed at a local feed through the environment.
- `tests/updater_fixture_app.py`: Added a tiny frozen-fixture app used by the updater harness.
- `tests/run_local_updater_integration.py`: Added a repeatable local updater harness for both installer and portable flows. It builds a fixture app exe and a fake installer exe with PyInstaller, creates a local file-based release feed (`release.json`, installer asset, portable zip, SHA-256 sidecars), stages installed-layout and portable-layout fixture apps, runs the real updater download + launcher paths, and saves a report to `tests/logs/local_updater/`.
- `tools/run_local_updater_integration.ps1`: One-command wrapper for rerunning the local harness with the missing home-directory env vars populated.
- `tests/test_update_manager.py`: Added coverage for the `/DIR=` launcher argument, installed-layout detection, release URL override, and the new portable launcher fallback content.
- `tools/build/KeyQuest-RootFolders.spec`: Added temporary excludes for `pkg_resources`, `setuptools`, and `jaraco` while debugging a local packaged-EXE startup failure (`Failed to execute script 'pyi_rth_pkgres' ... The 'jaraco' package is required`).
- `tests/logs/local_updater/REPORT.md`, `tests/logs/local_updater/result.json`: current saved result is a full pass for both installer and portable paths. The harness verifies detection of the new version, asset selection, local download, SHA-256 verification, update handoff, and relaunch into `1.9.1`.

### 2026-03-24: Automatic Update Scheduling, Idle-Gate, and Retry

- `Sentences/manifest.json`: Added a canonical built-in sentence manifest so topic names, backing files, display labels, and explanations are data-driven instead of being hard-coded in app logic.
- `modules/sentences_manager.py`: Added manifest loading, fallback handling, topic metadata helpers, and speed-test file lookup via the manifest while still tolerating extra `.txt` files dropped into `Sentences/`. Follow-up cleanup removed the duplicated built-in manifest from Python; missing or invalid manifests now fall back by inferring topic entries from the actual sentence files on disk.
- `modules/test_modes.py`, `modules/keyquest_app.py`, `ui/render_test_setup.py`: Speed Test setup now uses one scrollable source list: `Random Topic` plus the regular topic entries using the same manifest-driven labels as Sentence Practice.
- `modules/test_modes.py`: Random-topic filtering now excludes Spanish and other non-English topic names for both Speed Test and Sentence Practice, while leaving other extra English `.txt` topics eligible.
- `tests/test_sentences_manifest.py`: Added coverage for manifest validity and runtime fallback behavior, including inference when the manifest is absent.
- `tests/test_test_modes.py`: Added focused coverage for the new Speed Test setup flow.
- `docs/dev/CONTENT_MANIFEST.md`, `docs/dev/schemas/sentences-manifest.schema.json`: Added developer documentation and a JSON schema for the sentence manifest format.
- `modules/update_manager.py`: Added `_fetch_with_retry()` — retries `fetch_latest_release` up to 3 times with exponential backoff (3 s, 6 s) on `UpdateNetworkError`. `UpdateHttpError` and parse errors fail immediately. `check_for_update()` now calls this instead of calling `fetch_latest_release` directly.
- `modules/keyquest_app.py`:
  - Updates now check automatically every **4 hours** while the app is running (periodic timer in `_poll_update_work`).
  - Updates also check each time the user reaches the **main menu**, rate-limited to once per hour.
  - A found update is held until the user has been **idle for 30 minutes** (no keypresses), then installs silently. This prevents interrupting an active session.
  - `_last_user_activity` resets on every `KEYDOWN`; `_update_periodic_last_check` resets whenever a check thread starts.
- `tests/test_update_manager.py`: 7 new tests for `_fetch_with_retry` (retry logic, backoff timing, no-retry on non-transient errors).
- `tests/test_update_idle_logic.py`: New file — 18 tests for the idle-gate and periodic-timer logic using a minimal app stub; includes `TestConstantsMatchSource` which parses `keyquest_app.py` with `ast` to ensure the test constants stay in sync.

### 2026-03-22: Sentence Merge Fix and Spanish Compose Escape Fix

- `modules/update_manager.py`: Fixed `_sentence_merge_powershell()` — it was using `{{` and `}}` instead of `{` and `}` in plain Python strings. The batch file was passing literal `{{` to PowerShell, causing the sentence merge step to silently do nothing. Users' custom sentence files were not being preserved across any update.
- `modules/test_modes.py`: `handle_practice_input` now clears `pending_compose_mark` on Escape, matching the behavior of `handle_test_input`. Without this, starting a Spanish compose sequence and then Escaping left a stale compose mark that would misfired unexpectedly in the next typing session.
- `tests/test_update_manager.py`: Added `assertNotIn('{{')` / `assertNotIn('}}')` to both launcher tests.
- `docs/dev/HANDOFF.md`: Removed stale TODO about re-shipping the portable updater fix (already done in 1.5.13).

### 2026-03-22: Release Guardrails and Portable Updater Fix

- Confirmed from the installed log at `C:\Users\csm12\AppData\Local\Programs\KeyQuest\keyquest_error.log` that portable updates were still stalling after download on the line `Waiting for KeyQuest process ... to exit before applying the portable update.`
- Confirmed the generated helper script on disk already had the 15-second force-close wait logic, so the stall was not the old no-timeout bug.
- Root cause: `modules/update_manager.py` generated a malformed portable launcher after the wait loop by starting one PowerShell command and then injecting a second full `powershell -Command` block for sentence merging. That left the helper `cmd.exe` process alive without reaching extraction/copy/restart.
- Fixed `modules/update_manager.py` to emit one valid merge command using `%EXTRACT_DIR%\KeyQuest\Sentences` directly.
- Tightened `tests/test_update_manager.py` to assert the portable launcher only contains one `powershell -Command` block in that section.
- `.githooks/pre-push` now runs `ruff check .` before `pytest -q` for release tags, matching GitHub’s CI gate and preventing another `v1.5.12`-style lint-only release failure.
- `tools/dev/install_git_hooks.ps1` now warns when Ruff is missing locally, in addition to pytest.

### 2026-03-19: Shared Layout Helpers and Responsive Screen Pass

- Added `ui/layout.py` for shared screen geometry:
  - live screen size lookup
  - safe content width
  - centered placement helpers
  - wrapped centered and left-aligned text blocks
  - footer row placement
- Added `ui/game_layout.py` for shared game chrome:
  - centered game titles
  - centered status-line stacks
- Refactored `games/base_game.py` and `ui/render_menus.py` to use the shared layout helpers instead of repeating centering and footer math.
- Refactored `games/word_typing.py`, `games/letter_fall.py`, and `games/hangman.py` to use the shared helpers for title, wrapped text, status, and footer placement while keeping gameplay-specific visuals local.
- Added `tests/test_layout.py` to lock in the new helper behavior.
- Accessibility review outcome: keep geometry in layout helpers, keep focus/emphasis in `ui/a11y.py`, and keep gameplay meaning local to each screen.

### 2026-03-07: Code Quality, Test Coverage, and Modularisation Pass

- Extracted `modules/flash_manager.py` (`FlashState`) and `modules/font_manager.py` (`detect_dpi_scale`, `build_fonts`) from `keyquest_app.py`.
- `progress.json` save is now atomic (temp-file + rename) — no data loss on crash.
- `error_logging.py` gained log rotation (2 MB cap) and `log_message()` helper; `dialog_manager.py` now routes errors there instead of a separate file.
- Pet happiness decays 5 pts/day since last fed (applied at load time in `state_manager.py`).
- `keyquest.pyw` now supports `--version` flag; CI EXE smoke test uses it.
- Ruff lint step and EXE smoke test were added to the release workflow.
- `requirements.lock` and `pyproject.toml` (ruff + pytest config) added.
- Test count: 100 → 179 (audio, speech, schema migration, file-not-found paths all covered).
- `docs/dev/ARCHITECTURE.md` added (module map, mode state machine, conventions).
- See top entry in `docs/dev/CHANGELOG.md` for full detail.

### 2026-03-06: Docs, Command Wording, and Release Workflow Refresh

- Added `tools/ship_updates.ps1` as the preferred release entrypoint when you want version bump selection handled for you.
- Added `tools/dev/release_bump.py` to suggest and apply conservative `patch` or `minor` bumps.
- Added `docs/dev/RELEASE_POLICY.md` so `update git` and `ship updates` have distinct meanings.
- Added `docs/dev/CONTENT_STYLE_GUIDE.md` to keep guide, changelog, blog, and sentence wording consistent.
- Audited and simplified Windows, NVDA, and JAWS command sentence files for clearer learner-facing wording.
- Expanded release/process notes in `docs/dev/DEVELOPER_SETUP.md` and refreshed this handoff file.

### 2026-02-25: Accessibility Enhancement Pass (complete)

All items from the accessibility recommendations audit are now implemented. `docs/dev/ACCESSIBILITY_RECOMMENDATIONS.md` has been deleted. `docs/user/ACCESSIBILITY_COMPLIANCE_SUMMARY.md` updated.

**Final three items completed this session:**

**`modules/state_manager.py`**
- Added `font_scale: str = "auto"` to `Settings` dataclass; persisted via `load`/`save`.

**`modules/menu_handler.py`**
- Added `get_font_scale_explanation(scale)` and `cycle_font_scale(current, direction)` helpers.

**`modules/keyquest_app.py`**
- Added `_detect_dpi_scale()` module-level function (ctypes `GetDpiForSystem` / 96).
- Added `_rebuild_fonts()` method: recreates `title_font`, `text_font`, `small_font` at the effective scale; propagates new font objects to all cached game instances.
- `_rebuild_fonts()` called at startup (after `load_progress`) and on Font Size option change.
- Added `Font Size` option to Options menu (`auto` / `100%` / `125%` / `150%`).
- Added `_escape_remaining` / `_escape_noun` instance state.
- `_handle_escape_shortcut()` sets `_escape_remaining` on partial press, clears on completion or reset.
- `draw()` renders a centered top-of-screen text counter while `_escape_remaining > 0` (visual complement to the existing speech announcement).

**`tests/test_test_modes.py`**
- Added `trigger_flash` stub to `_DummyApp` (required by `test_modes._record_typing_error`).

**`README.html`**
- Options section expanded from one line to a full itemized list of all 8 settings (including Font Size).
- Quick Start Escape note updated to mention the on-screen remaining press counter.
- Accessibility section expanded with four new bullets: HC auto-detection, font size/DPI scaling, visual keystroke flash, escape press counter.

**Earlier items (same session):**

**`ui/a11y.py`**
- Added `draw_keystroke_flash(screen, color, alpha, screen_w, screen_h)` — semi-transparent color overlay for visual keystroke feedback.

**`ui/render_results.py`**
- Added `small_font`, `screen_h`, `accent` parameters.
- Added `draw_controls_hint()` at bottom ("Space/Enter continue; Esc menu") — this was the only render screen missing a controls hint.

**`ui/render_tutorial.py`**
- Added `screen_h` parameter.
- Fixed tutorial intro controls hint Y from hardcoded `540` to `screen_h - 60`, matching all other screens.

**`ui/render_menus.py`**
- `draw_lesson_menu()`: silently truncated lesson list now shows "v  more below  v" when items exceed screen height.

**`modules/theme.py`**
- `detect_theme()` now checks Windows High Contrast mode (via `ctypes` / `SPI_GETHIGHCONTRAST`) before `darkdetect`. Users with HC enabled in Windows Settings get the in-app `high_contrast` theme automatically.
- Dark theme HILITE nudged from `(80, 120, 180)` ? `(90, 130, 190)`: contrast ratio improved from 4.69:1 to 5.77:1, giving comfortable margin above the 4.5:1 WCAG AA minimum.

**`modules/notifications.py`**
- Removed emoji characters (`??`, `??`, `badge['emoji']` prefix) from badge and level-up dialog text content. Screen readers that intercept wx TextCtrl content directly no longer expand emoji verbosely. Speech announcement paths (which already used clean text) unchanged.

**`modules/keyquest_app.py`**
- Added `_flash_color` / `_flash_until` state and `trigger_flash(color, duration=0.12)` method.
- `draw()` renders a fading flash overlay after all content when a flash is active.
- `draw_results()` call updated with new `small_font`, `screen_h`, `accent` params.
- `draw_tutorial()` call updated with new `screen_h` param.
- Tutorial correct/incorrect handlers call `self.trigger_flash()` (green / red).

**`modules/lesson_mode.py`**
- `process_lesson_typing()`: calls `app.trigger_flash((0, 80, 0), 0.12)` on correct keystroke, `app.trigger_flash((100, 0, 0), 0.12)` on error.

**`modules/test_modes.py`**
- `_record_typing_error()`: calls `app.trigger_flash((100, 0, 0), 0.12)` on typing error.

**Not implemented (future work — documented in `docs/dev/ACCESSIBILITY_RECOMMENDATIONS.md`):**
- User-adjustable font size (`modules/config.py`) — requires Options menu entry + font re-creation on change.
- DPI scaling — should be paired with font size work; risk of layout regressions across all screens.
- Escape guard visual count — speech already announces remaining presses; visual overlay is low priority.

### 2026-02-19: Version 1.0 Release + About Screen

- Declared milestone release as `Version 1.0` (`modules/version.py`).
- Added `About: A` to the bottom of the main menu (`modules/state_manager.py`).
- Added new `ABOUT` mode in `modules/keyquest_app.py`:
  - menu-driven about items (app/version, name, company, tagline, copyright, license, website, credits, back)
  - website item opens `https://webfriendlyhelp.com` via default browser on Enter/Space
  - Escape returns to Main Menu
- Added `LICENSE` file with MIT terms for open collaboration and redistribution.
- Added Windows installer build path with Inno Setup:
  - `tools/build/installer/KeyQuest.iss`
  - `tools/build/build_installer.bat`
  - `tools/build.ps1 -Target installer`
- Updated `README.html` main menu docs with About details and Version 1.0 marker.

### 2026-02-19: GitHub Publish + Release Assets + README Contact Link

- Initialized git repo in workspace and published source to GitHub:
  - Repo: `https://github.com/WebFriendlyHelp/KeyQuest`
  - Default branch: `main`
- Created and published release tag `v1.0` with downloadable assets:
  - `KeyQuestSetup-1.0.exe`
  - `KeyQuest-1.0-win64.zip`
  - Release page: `https://github.com/WebFriendlyHelp/KeyQuest/releases/tag/v1.0`
- Updated README feedback links to include email subject:
  - `mailto:help@webfriendlyhelp.com?subject=KeyQuest%20Feedback`
- Removed dedicated Hangman item from the user-facing Games list in `README.html` while keeping Hangman implemented in app.
- Performed a source-comment wording pass for public-facing clarity in a few modules (`dialog_manager`, `currency_manager`, `key_analytics`, `lesson_manager`, `ui/pet_visuals`).

### 2026-02-19: Hangman UX + Escape Handler Unification

- Added shared escape press tracker: `modules/escape_guard.py`.
- Moved active-mode Escape behavior to centralized policy/handler in `modules/keyquest_app.py`.
  - Keyboard Explorer uses `Escape x3` via the shared path.
  - Sentence Practice finish-on-Escape-x3 now routes through the same centralized handler.
- `games/hangman.py` updates:
  - Word progress speech now uses comma separators (`c, blank, t`) for better SR clarity.
  - Added word-position cursor navigation (`Left/Right/Home/End`) with spoken position feedback and visual focus highlight.
  - Sentence-practice `Ctrl+Space` now announces remaining text based on current typing position.
  - Replaced simple sentence-practice templates with randomized style-based prompts for higher-quality, less repetitive lines.
  - Removed fixed max word length; max is now derived from dictionary data.
  - Updated word selection to favor common lengths while still allowing short and rare very long words.
- Documentation:
  - Updated `README.html` Hangman controls/details.
  - Updated `docs/dev/CHANGELOG.md` with this change set.

### 2026-02-18: User Guide HTML + Packaging + Escape/Hotkey Doc Alignment

- Documentation:
  - Replaced user-facing readme content with `README.html` (plain-language, main-menu organized).
  - Added WCAG-oriented page structure for the guide (landmarks, skip link, focus-visible styles).
  - Simplified `README.md` to a pointer to `README.html`.
  - Updated `docs/dev/CHANGELOG.md` with latest Hangman/readme/build notes.
- Build/distribution:
  - Updated `tools/build/KeyQuest-RootFolders.spec` to copy `README.html` to:
    - `dist/KeyQuest/README.html`
    - `dist/KeyQuest/docs/README.html`
- In-app docs text alignment:
  - Updated gameplay hotkey/instruction text for `Letter Fall`, `Word Typing`, and `Hangman` to reflect `Escape x3` exit behavior.

### 2026-02-16: Prompt Clarity + Early Lesson Sequence Length + Random Topic Rule

- `modules/speech_format.py`:
  - Added `spell_text_for_typing_instruction()` for clearer `Type ...` prompts.
  - Uses `then` separators when sequence order is likely important (special keys/spaces or repeated characters).
- `modules/lesson_mode.py`, `modules/keyquest_app.py`, `modules/lesson_manager.py`:
  - Unified typing-prompt formatting on the new helper.
  - Kept mismatch/remaining feedback format unchanged (`Missing: ... Remaining text: ...`).
- `modules/lesson_mode.py`:
  - Early stages (0-5) now normalize practice targets to 3-4 keys for easier recall.
- `modules/test_modes.py`:
  - `Random Topic` now picks from non-Spanish topics only (fallback to all topics if needed).
- Tests:
  - Updated/added coverage in `tests/test_speech_format.py`, `tests/test_lesson_mode.py`, and `tests/test_test_modes.py`.
- Docs:
  - Updated `README.md` and `docs/dev/CHANGELOG.md` to match implemented behavior.

### 2026-02-14: Accessibility + Structure Follow-Through

- Added shared speech-format helpers and consistent mismatch announcements.
- Updated menu labels/order and Word Typing countdown behavior.
- Reorganized root helper/build files into `tools/build/`, `tools/quality/`, and `docs/`.
- Added targeted regression tests in `tests/test_test_modes.py` and `tests/test_word_typing.py`.
- Added adaptive tutorial flow (space-first onboarding, phase pacing based on performance, extra reps for troublesome keys).
- Added typing sound intensity option (`subtle` / `normal` / `strong`) with persistence.
- Updated PyInstaller spec for reorganized repo layout and stabilized Python 3.9 compatibility.
- Updated exe distribution docs policy to include `README.md`, `README.html`, and user-facing docs in `dist/KeyQuest/docs/`.

### 2026-02-14: Startup Speech and Exit UX Follow-Up

- `modules/keyquest_app.py`:
  - Startup menu announcement is timer-driven to avoid racing with screen-reader title announcement.
  - Startup announcement uses non-interrupting speech for first menu item.
  - Removed startup priority protection that delayed first menu arrow navigation speech.
  - Quit path now shows and speaks a brief goodbye message before exiting.
- `modules/speech_manager.py`:
  - Added fixed duplicate-speech debounce (`0.25s`) for identical rapid repeats.

For full details, see the top entry in `docs/dev/CHANGELOG.md`.
