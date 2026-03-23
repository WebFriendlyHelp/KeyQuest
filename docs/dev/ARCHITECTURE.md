# KeyQuest Architecture

## Overview

KeyQuest is an accessible keyboard-learning application for Windows, with partial Linux support, that teaches touch typing through adaptive lessons, games, quests, and a pet/reward system. It runs on Python 3.11+, uses Pygame as the primary rendering and event loop, wxPython for accessible modal dialogs, Tolk and pyttsx3 for speech output, and numpy for audio synthesis.

## Module Map

### Entry Point

| File | Description |
|---|---|
| `keyquest.pyw` | Thin launcher that calls `modules/keyquest_app.py:main()` |

### Core App

| File | Description |
|---|---|
| `modules/keyquest_app.py` | `KeyQuestApp` class, Pygame event loop, mode dispatch, and cross-mode wiring |
| `modules/flash_manager.py` | `FlashState` for visual keystroke flash feedback |
| `modules/font_manager.py` | DPI detection and scaled font creation |

### State and Data

| File | Description |
|---|---|
| `modules/state_manager.py` | `AppState`, `Settings`, lesson tracking, and `progress.json` load/save |
| `modules/error_logging.py` | Error and diagnostic logging |
| `modules/app_paths.py` | Runtime-safe path resolution for source and frozen builds |
| `modules/version.py` | Single `__version__` source of truth |
| `modules/config.py` | Screen dimensions, font names, and constants |
| `modules/theme.py` | Theme detection and color selection |

### Audio and Speech

| File | Description |
|---|---|
| `modules/audio_manager.py` | Synthesizes tones and sound effects in memory |
| `modules/speech_manager.py` | Speech routing, queueing, debounce, and fallback handling |
| `modules/speech_format.py` | Speech formatting helpers for prompts and feedback |
| `modules/sound_catalog.py` | Named sound registry |
| `modules/sound_demo.py` | In-app sound preview logic |

### Lesson System

| File | Description |
|---|---|
| `modules/lesson_manager.py` | Stage definitions, lesson names, targets, thresholds, and prompt vocabulary |
| `modules/lesson_mode.py` | Active lesson loop, adaptive batching, and error recovery |
| `modules/lesson_intro_mode.py` | Key-finding intro shown before supported lessons |
| `modules/learn_sounds_mode.py` | Learn-the-Sounds sub-mode |

### Game System

| File | Description |
|---|---|
| `games/base_game.py` | Base class for games |
| `games/letter_fall.py` | Letter Fall game |
| `games/word_typing.py` | Word Typing game |
| `games/hangman.py` | Hangman with dictionary and sentence-practice bridge |
| `games/sounds.py` | Shared game audio helpers |

### UI and Rendering

| File | Description |
|---|---|
| `ui/a11y.py` | Accessibility overlays and focus helpers |
| `ui/layout.py` | Shared screen-size, centering, wrapped-text, and footer layout helpers |
| `ui/game_layout.py` | Shared game title and status-stack layout helpers |
| `ui/render_menus.py` | Main menu, lesson menu, and games menu rendering |
| `ui/render_lesson.py` | Active lesson screen |
| `ui/render_lesson_intro.py` | Lesson intro screen |
| `ui/render_test_setup.py` | Test and practice setup screens |
| `ui/render_test_active.py` | Active test and sentence-practice screens |
| `ui/render_results.py` | Post-session results and choice menu screen |
| `ui/render_tutorial.py` | Tutorial screen |
| `ui/render_keyboard_explorer.py` | Keyboard Explorer screen |
| `ui/render_free_practice_ready.py` | Free Practice ready screen |
| `ui/render_learn_sounds.py` | Learn-the-Sounds menu screen |
| `ui/render_options.py` | Options screen |
| `ui/render_shop.py` | Pet shop screen |
| `ui/render_pet.py` | Pet screen |
| `ui/render_updating.py` | In-app update progress screen |
| `ui/text_wrap.py` | Text wrapping helpers |
| `ui/pet_visuals.py` | Pet drawing helpers |

### Features and Managers

| File | Description |
|---|---|
| `modules/badge_manager.py` | Achievement badges |
| `modules/challenge_manager.py` | Daily challenge generation and tracking |
| `modules/currency_manager.py` | Coin earn and spend logic |
| `modules/pet_manager.py` | Pet ownership, happiness, and progression |
| `modules/pet_mode.py` | Active pet interaction mode |
| `modules/pet_ui_data.py` | Static pet descriptions and labels |
| `modules/quest_manager.py` | Quest unlock and progress tracking |
| `modules/shop_manager.py` | Shop inventory and purchase validation |
| `modules/shop_mode.py` | Active shop navigation mode |
| `modules/xp_manager.py` | XP and level progression |
| `modules/dashboard_manager.py` | Progress dashboard aggregation |
| `modules/key_analytics.py` | Per-key performance analytics |
| `modules/results_formatter.py` | Results summary text formatting |
| `modules/progress_views.py` | Progress and stats views |
| `modules/streak_manager.py` | Practice streak tracking |
| `modules/update_manager.py` | GitHub release checks and update flow |

### Input and Navigation

| File | Description |
|---|---|
| `modules/menu_handler.py` | Shared menu navigation, including Home and End support |
| `modules/dialog_manager.py` | wxPython modal dialogs |
| `modules/input_utils.py` | Key normalization and modifier helpers |
| `modules/escape_guard.py` | Escape x3 exit guard |
| `modules/notifications.py` | Badge and level-up notifications |
| `modules/keyboard_explorer.py` | Keyboard Explorer input and announcement logic |

## App Modes

```text
MENU
|- TUTORIAL -> MENU
|- LESSON_INTRO -> LESSON -> RESULTS -> MENU
|- TEST_SETUP -> TEST -> RESULTS -> MENU
|- PRACTICE_SETUP -> PRACTICE -> RESULTS -> MENU
|- FREE_PRACTICE_READY -> FREE_PRACTICE -> RESULTS -> MENU
|- GAMES -> GAME -> RESULTS -> MENU
|- KEYBOARD_EXPLORER -> MENU
|- PET -> MENU
|- SHOP -> MENU
|- ABOUT -> MENU
`- UPDATING -> MENU
```

Active non-menu modes support Escape x3 to return safely to the main menu.

## Rendering Loop

`KeyQuestApp.run()` drives Pygame at about 30 FPS using `self.clock.tick(30)`. Each frame, `draw()` checks `self.state.mode` and dispatches to the matching `ui/render_*.py` helper with the current fonts, colors, and relevant state slices. The render modules are stateless draw helpers; mutable state lives in `AppState`.

The current layout split is:

- `ui/layout.py`: geometry and flow only. Use it for live screen size, safe content width, centered placement, wrapped text blocks, and footer row placement.
- `ui/game_layout.py`: shared game chrome only. Use it for centered game titles and simple status stacks.
- `ui/a11y.py`: accessibility emphasis only. Focus frames, active panels, and controls hints stay here instead of being folded into generic layout helpers.

This separation is intentional: layout helpers should position content, while accessibility helpers should emphasize already-positioned content.

wxPython dialogs from `modules/dialog_manager.py` are shown synchronously outside the main Pygame draw path. They are used for accessible summaries and information screens, while the in-app results screen now handles choice menus with normal up and down navigation.

## Speech Pipeline

`modules/speech_manager.py` owns the speech queue and fallback chain:

1. Debounce drops identical consecutive messages in a short window.
2. If Tolk is available and a screen reader is active, text is sent there first.
3. Otherwise pyttsx3 speaks through SAPI.
4. If neither path is available, the call fails silently instead of crashing the app.

Priority announcements can use `protect_seconds` to suppress lower-priority speech briefly and keep key prompts readable.

## Data Flow

`progress.json` is the main persistence file:

1. Startup load populates `AppState.settings` and related feature state.
2. In-session updates mutate `AppState` directly.
3. Save writes to a temporary file and atomically renames it over `progress.json`.
4. Saves happen on key user actions such as lesson completion, settings changes, purchases, and clean exit.

## Current Navigation Conventions

- Use `self.speech.say("...", priority=True, protect_seconds=2.0)` for important spoken announcements.
- Keep spoken and visual instructions aligned.
- Use `get_app_dir()` for runtime-safe path resolution.
- Shared list-style navigation should support Up, Down, Home, End, Enter, Space, and Escape where appropriate.
- New screens should use `ui/layout.py` instead of hardcoded `900`, `600`, `450`, or single-line footer assumptions unless there is a documented gameplay reason not to.
