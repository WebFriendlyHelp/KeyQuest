# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Session Start

At the start of a new session, read `docs/dev/HANDOFF.md` and the top entry of `docs/dev/CHANGELOG.md` for current context before making any changes.

## Commands

```bash
# Run the app
py -3.11 keyquest.pyw

# Run all tests
py -3.11 -m pytest -q

# Run a single test file
py -3.11 -m pytest tests/test_streak_manager.py -q

# Quality checks (contrast, lint)
powershell -ExecutionPolicy Bypass -File tools/run_quality_checks.ps1

# Build exe + source package
powershell -ExecutionPolicy Bypass -File tools/build.ps1 -Target all -Clean

# Ship a release (version bump, changelog, push main + tag)
powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1
```

## Architecture

**Platform:** Windows-only, Python 3.11, Pygame.

**Entry point:** `keyquest.pyw` → `modules/keyquest_app.py` (the main application class). The app is a Pygame event loop. `keyquest_app.py` is a large central file being gradually reduced by extracting cohesive features into separate modules — do not add new features to it directly.

**Three source packages:**
- `modules/` — all business logic, state, and feature managers
- `ui/` — pure rendering functions; each `render_*.py` draws one screen/view
- `games/` — minigames; all inherit from `games/base_game.py`

**Key modules:**
- `modules/state_manager.py` — all dataclasses (`Settings`, `AdaptiveTracker`, `KeyPerformance`) and save/load logic
- `modules/config.py` — screen dimensions and font size constants
- `modules/app_paths.py` — resolves app root for both source (`py keyquest.pyw`) and frozen (`.exe`) modes
- `modules/speech_manager.py` — screen reader speech via `Speech` class; use `priority=True` + `protect_seconds` for important announcements
- `modules/theme.py` — color theme management
- `ui/a11y.py` — shared accessibility helpers (`draw_controls_hint`, `draw_focus_frame`)
- `ui/layout.py` — layout utilities (`center_x`, `get_footer_y`, `get_screen_size`)

**`dist/` directory** mirrors the source tree — it is build output, not the source of truth. Always edit source files.

## Accessibility Patterns

- **Emoji in spoken strings:** Never pass emoji to `speech.say()` — NVDA/JAWS read them as their Unicode name ("party popper", "star", etc.). `Speech.say()` strips emoji via `_EMOJI_RE` automatically, but source strings in `results_formatter.py`, `key_analytics.py`, and any new modules should be kept plain ASCII so the visual dialog text is also clean.
- **Tolk lifecycle:** Never rely on `__del__` for `tolk.unload()`. Call `self.speech.shutdown()` explicitly in `_quit_app()` before `pygame.quit()`.
- **Dialog focus:** `show_dialog()` and `show_yes_no_dialog()` move focus to the `TextCtrl` via `wx.CallAfter(text_ctrl.SetFocus)` so screen readers read content immediately on open. Do not change this to focus a button by default.
- **Yes/No Enter key:** `on_key` in `show_yes_no_dialog` checks `dlg.FindFocus()` before mapping Enter to Yes/No — it respects whichever button the user has tabbed to. Do not revert to always-Yes behaviour.
- **Dialog labels:** Both dialog functions add a `wx.StaticText(panel, label=title)` above the `TextCtrl` so UIA can infer the text area's accessible name.
- **Pygame canvas:** The Pygame display surface is opaque to Windows UI Automation — pywinauto/UIA-based testing cannot inspect game state. Accessibility review for game screens must be done by code inspection, not automated tools.

## Conventions

- Keep speech announcements and visible text aligned.
- New games must subclass `BaseGame` and define `NAME`, `DESCRIPTION`, `INSTRUCTIONS`, `HOTKEYS`, and override `start_playing`, `handle_game_input`, `update_game`, `draw_game`.
- Prefer "pure" modules (no audio/display dependencies) when extracting logic from `keyquest_app.py` — these are easier to unit test.
- For meaningful behavior changes, update `docs/dev/CHANGELOG.md`, `docs/user/WHATS_NEW.md`, and `docs/dev/HANDOFF.md`.
- Prefer updating existing docs over creating new one-off markdown files.
- Consult `docs/dev/RELEASE_POLICY.md` to decide between a plain push and a shipped release.
