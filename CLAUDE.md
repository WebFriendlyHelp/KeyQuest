# CLAUDE.md

## Session Start
Read `docs/dev/HANDOFF.md` and the top entry of `docs/dev/CHANGELOG.md` before making any changes.

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
```

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
| `ui/a11y.py` | `draw_controls_hint`, `draw_focus_frame` |
| `ui/layout.py` | `center_x`, `get_footer_y`, `get_screen_size` |

`dist/` is build output — always edit source files.

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
