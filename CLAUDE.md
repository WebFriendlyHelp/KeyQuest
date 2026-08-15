# CLAUDE.md

## Session Start
Read `docs/dev/HANDOFF.md` and the top entry of `docs/dev/CHANGELOG.md` only when:
- Making code changes
- Preparing a release
- Investigating a bug

## Commands
```bash
pip install -r requirements.txt                                          # install deps
py -3.11 keyquest.pyw                                                    # run app
py -3.11 -m pytest -q                                                    # all tests
py -3.11 -m pytest tests/test_streak_manager.py -q                      # single test
powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1   # contrast + lint
powershell -ExecutionPolicy Bypass -File tools/build.ps1 -Target all -Clean  # build exe + source
powershell -ExecutionPolicy Bypass -File tools/build.ps1 -Target installer   # installer only (requires Inno Setup 6)
powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1         # release (bump, changelog, push+tag)
py -3.11 tests/run_lesson_playthrough.py                                # play every lesson as a perfect typist
py -3.11 tests/run_focus_guard.py                                       # real-window focus check (PowerShell, not Git Bash)
```

## Shipping
Before running `tools/ship_updates.ps1`:
- Stash or commit unrelated WIP first — the release script stages everything (`git add -A`), so stray files land in the release commit.
- Run `py -3.11 tests/run_focus_guard.py` from PowerShell and require exit 0. CI cannot run it (see the Focus Guard section), so this is the only place the real-window check happens. Exit 2 means it could not measure, which is not a pass.
- Run `py -3.11 tools/dev/check_env_matches_ci.py --strict` and require exit 0. `requirements.txt` carries floors and CI installs fresh, so a dev machine drifts behind what actually ships. On 2026-08-15 v1.27.1 went out built on wxPython 4.3.1 while this machine had 4.2.5, meaning the accessible dialogs users received were built on a version never run here. If it reports drift, upgrade and then exercise whatever the changed package owns.

After the script pushes the tag, the release is not done until verified:
1. Watch the GitHub Release workflow to green (`gh run watch` or `gh run list`).
2. Confirm all four release assets exist on the new release (installer exe, portable zip, source zip, checksums).
3. Smoke-test the installer exe from the release download.

## Architecture
**Platform:** Windows-only, Python 3.11, Pygame.

**Entry point:** `keyquest.pyw` → `modules/keyquest_app.py` (Pygame event loop). This file is being reduced — do not add features to it directly.

**Source packages:**
- `modules/` — business logic, state, feature managers
- `ui/` — pure rendering; each `render_*.py` draws one screen
- `games/` — minigames; all inherit `games/base_game.py`

**Key modules:**
| Module | Purpose |
|---|---|
| `modules/state_manager.py` | Dataclasses (`Settings`, `AdaptiveTracker`, `KeyPerformance`) + save/load |
| `modules/config.py` | Screen dimensions, font size constants |
| `modules/app_paths.py` | App root resolution for source and frozen `.exe` |
| `modules/speech_manager.py` | `Speech` class; use `priority=True` + `protect_seconds` for important announcements |
| `modules/theme.py` | Color theme management |
| `modules/update_manager.py` | GitHub release check, download, SHA-256 verify, bat launcher templates, temp cleanup |
| `modules/update_controller.py` | App-level update orchestration: background check/download, fallback layers, post-restart verification |
| `ui/a11y.py` | `draw_controls_hint`, `draw_focus_frame` |
| `ui/layout.py` | `center_x`, `get_footer_y`, `get_screen_size` |

`dist/` is build output — always edit source files.

## Updater Architecture
- Update launchers are **pure `.bat`** files — no PowerShell dependency. Uses `robocopy`, `tar`, `tasklist`/`taskkill`.
- Three fallback layers: primary bat launcher → direct apply → re-download to `~/Downloads/`.
- Every failure path restarts the old app so the user is never stranded.
- `pending_update.json` marker enables post-restart version verification.
- Integration test: `py -3.11 tests/run_local_updater_integration.py` — **strict by default** (35 steps): builds two distinguishable fixture exes, simulates real installer + portable update cycles, both direct fallbacks, and a rollback, stopping and relaunching a live process each time, with real bsdtar, real exe replacement, and a SHA-256 check proving `KeyQuest.exe` actually changed. Fixture builds are cached (`--rebuild` to force). `--fast` re-enables the test-only overrides (34 steps, skips the exe copy) and is a diagnostic, not release assurance. Runs automatically in CI on any updater change (`.github/workflows/updater-harness.yml`).

## Lesson Playthrough Harness
- `py -3.11 tests/run_lesson_playthrough.py` boots the real app headless (SDL dummy video/audio) and plays every lesson as a **perfect typist**: decode what the app just announced back into keystrokes, type exactly those, assert the app never reports an error. 1,569 items across all 33 lessons, exit 1 on any disagreement.
- **This exists because unit tests cannot catch the bug class it targets.** The formatter and the lesson generator were each correct in isolation; their *agreement* was wrong, which is how a prompt came to say "type a a" for a target needing A, space, A.
- Its decoder knows both readings of a word, so a prompt that decodes two ways is reported as ambiguous. That is how lesson 8's "gag dash" was found ("dash" is also the spoken name of the hyphen key).
- `--lessons 0-8` and `--attempts 5` narrow or deepen a run. Runs in CI on any lesson or speech change (`.github/workflows/lesson-playthrough.yml`).
- Never writes user data: saving is stubbed and the progress file is redirected to a temp path.

## Speech Transcript (diagnostics)
- `modules/speech_log.py`. **Off by default.** Turn it on with the "Speech Log" setting in Options, or set `KEYQUEST_SPEECH_LOG=1` before launch (the env var also covers startup announcements, which the setting cannot because settings load later). Writes `keyquest_speech.log` beside the error log.
- **The point is the DROPPED lines, not the SPOKE lines.** `Speech.say` has several paths that return without speaking (duplicate debounce, priority protection window, speech disabled, no engine, no backend) and every one is silent by design. A user cannot tell a dropped announcement from one never requested. Each is now recorded with its reason and the numbers behind it.
- SAPI lines carry the flags, the stream number returned by `Speak`, and how long the call took. `Speak` is async, so a duration above a few ms is itself the finding.
- Dialog text is logged too (`DIALOG`). wx dialogs are read by the screen reader through UI Automation, so that text never passes through `Speech.say` and would otherwise be a hole in the transcript.
- **About > Report a Problem never opens anything unasked.** v1.27.0 launched Explorer with the file selected, which throws a screen reader user out of KeyQuest and into another window: the same disruption as the v1.26.0 focus bug, self-inflicted. Opening the folder is now a question asked after the file is written (`diagnostics.open_folder_question`), with buttons named "Open the Downloads folder" and "Stay in KeyQuest" rather than Yes and No. It is still worth offering, because `explorer /select` lands focus on the file itself.
- **Do not speak a message and then raise a dialog carrying the same message.** They talk over each other: the screen reader announces the dialog on the focus change and cuts the spoken line off partway. Pick one channel. Report a Problem puts everything in the dialog, and speaks only where wx is unavailable and there is no dialog to read.
- **Narrator:** there is nothing Narrator-side to log. Tolk does not expose Narrator, so KeyQuest detects it and speaks through SAPI instead; the transcript says so in its header. Everything the app says is captured as `backend=sapi`.
- Cost measured, not assumed: ~5 microseconds per line with the handle held open, against ~102 if opened and closed each time. Hence the open handle. A failing log switches itself off and never propagates into speech.

## Focus Guard
- `py -3.11 tests/run_focus_guard.py` opens a REAL window and asserts the Narrator probe creates no window of its own. Exit 0 pass, 1 regressed, 2 cannot verify.
- **Covers what the playthrough harness structurally cannot.** That one runs on SDL's dummy driver, so it has no real window and can never see focus theft, freezes, or "I pressed a key and nothing happened."
- **It asserts on window CREATION, not on foreground.** Windows refuses `SetForegroundWindow` to a process that does not already own the foreground, so a focus-based assertion silently measures nothing from a background shell or a CI runner. Window creation is the mechanism underneath and is environment independent.
- **It runs the OLD unguarded pattern first and requires it to create a window.** If the environment cannot demonstrate the bug, it reports cannot-verify instead of a pass it did not earn. Never weaken that check to make the test go green.
- Re-launches itself under `pythonw` when started with a console, because a parent that owns a console lends it to console children and the bug then cannot reproduce. Run it from PowerShell, not Git Bash: MinTTY is a pty rather than a console, so the relaunch does not trigger.
- **LOCAL ONLY, and not for want of trying.** It was wired to a GitHub Actions `windows-latest` runner and the runner cannot reproduce the mechanism: a real window was created and even reached the foreground, but the unguarded control spawn produced **0** windows across 4 attempts, the same as the guarded one. The two are indistinguishable there. The control check caught that and reported cannot-verify; without it CI would have shown a confident green while measuring nothing. The workflow was deleted rather than left as a job that can never pass. Run it locally before a release instead.

## Accessibility Patterns
- **No emoji in speech strings.** `Speech.say()` strips them via `_EMOJI_RE`, but keep source strings in `results_formatter.py`, `key_analytics.py`, and new modules plain ASCII (visual dialogs too).
- **Tolk lifecycle:** Call `self.speech.shutdown()` explicitly in `_quit_app()` before `pygame.quit()`. Never rely on `__del__`.
- **Dialog focus:** `show_dialog()` / `show_yes_no_dialog()` focus `TextCtrl` via `wx.CallAfter(text_ctrl.SetFocus)`. Do not change to button focus.
- **Yes/No Enter key:** `on_key` checks `dlg.FindFocus()` before mapping Enter. Do not revert to always-Yes.
- **Dialog labels:** Both dialog functions add `wx.StaticText(panel, label=title)` so UIA can name the text area.
- **Pygame canvas:** Opaque to Windows UI Automation — test game screens by code inspection only.

## Conventions
- Keep speech and visible text aligned.
- New games: copy `games/GAME_TEMPLATE.py`; subclass `BaseGame`; define `NAME`, `DESCRIPTION`, `INSTRUCTIONS`, `HOTKEYS`; override `start_playing`, `handle_game_input`, `update_game`, `draw_game`.
- Prefer pure modules (no audio/display deps) when extracting from `keyquest_app.py`.
- Meaningful changes: update `docs/dev/CHANGELOG.md`, `docs/user/WHATS_NEW.md`, `docs/dev/HANDOFF.md`.
- Prefer updating existing docs over creating new files.
- Consult `docs/dev/RELEASE_POLICY.md` to decide between plain push and shipped release.
