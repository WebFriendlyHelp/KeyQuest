import pygame

from modules import input_utils
from modules import lesson_manager
from modules import phonetics
from modules import state_manager


def _build_intro_items(intro_info: dict, needed_keys: list[str]) -> list[tuple[str, str]]:
    items = [
        ("Overview", intro_info.get("description", "")),
        ("Location", intro_info.get("location", "")),
        ("Finding", intro_info.get("finding", "")),
    ]
    if needed_keys:
        keys_speech = phonetics.format_needed_keys_for_speech(needed_keys)
        start_item = ("Start Lesson", f"Press {keys_speech} to start the lesson.")
        items.insert(0, start_item)
        items.append(start_item)
    return [(heading, text) for heading, text in items if text]


def _speak_current_intro_item(app, priority: bool = True) -> None:
    intro = app.state.lesson_intro
    if not intro.intro_items:
        return

    _heading, text = intro.intro_items[intro.intro_index]
    app.speech.say(
        text,
        priority=priority,
        protect_seconds=3.0 if priority else 0.0,
    )


def show_lesson_intro(app, lesson_num: int) -> None:
    """Show lesson intro screen with key location and finding instructions."""
    app.state.mode = "LESSON_INTRO"
    intro_info = lesson_manager.KEY_LOCATIONS[lesson_num]

    required_keys_str = intro_info["keys"]
    needed_keys = sorted(list(set(required_keys_str.lower())))
    app.state.lesson_intro = state_manager.LessonIntroState(
        lesson_num=lesson_num,
        required_keys=set(required_keys_str.lower()),
        keys_found=set(),
        intro_items=_build_intro_items(intro_info, needed_keys),
        intro_index=0,
    )

    repeat_lesson_intro(app)


def repeat_lesson_intro(app) -> None:
    """Repeat the lesson intro information."""
    intro = app.state.lesson_intro
    lesson_num = intro.lesson_num
    intro_info = lesson_manager.KEY_LOCATIONS[lesson_num]

    lesson_name = lesson_manager.LESSON_NAMES[lesson_num]
    desc = intro_info["description"]
    needed_keys = sorted(list(intro.required_keys - intro.keys_found))
    intro.intro_items = _build_intro_items(intro_info, needed_keys)
    intro.intro_index = min(intro.intro_index, max(0, len(intro.intro_items) - 1))

    if needed_keys:
        keys_speech = phonetics.format_needed_keys_for_speech(needed_keys)
        app.speech.say(
            f"Lesson {lesson_num}, {lesson_name}. {desc} "
            "Use Up and Down arrows to review the lesson information one item at a time. "
            f"Press {keys_speech} to start the lesson. "
            "Control Space repeats the current item.",
            priority=True,
            protect_seconds=5.0,
        )
        _speak_current_intro_item(app, priority=False)
    else:
        app.speech.say("All keys found! Press them to continue.", priority=True)


def handle_lesson_intro_input(app, event, mods: int) -> None:
    """Handle key presses during lesson intro - looking for new keys."""
    if event.key == pygame.K_ESCAPE:
        app.state.mode = "MENU"
        app.say_menu()
        return

    if event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
        _speak_current_intro_item(app, priority=True)
        return

    intro = app.state.lesson_intro
    if event.key == pygame.K_UP and intro.intro_items:
        intro.intro_index = (intro.intro_index - 1) % len(intro.intro_items)
        _speak_current_intro_item(app, priority=False)
        return

    if event.key == pygame.K_DOWN and intro.intro_items:
        intro.intro_index = (intro.intro_index + 1) % len(intro.intro_items)
        _speak_current_intro_item(app, priority=False)
        return

    if event.key == pygame.K_HOME and intro.intro_items:
        intro.intro_index = 0
        _speak_current_intro_item(app, priority=False)
        return

    if event.key == pygame.K_END and intro.intro_items:
        intro.intro_index = len(intro.intro_items) - 1
        _speak_current_intro_item(app, priority=False)
        return

    def _wrong_key():
        needed_keys = sorted(list(intro.required_keys - intro.keys_found))
        if needed_keys:
            app.audio.beep_bad()
            keys_speech = phonetics.format_needed_keys_for_speech(needed_keys)
            app.speech.say(
                f"That's not the key. Press {keys_speech} to start the lesson.",
                priority=True,
            )

    if event.unicode and event.unicode.isprintable():
        pressed = event.unicode.lower()

        if pressed in intro.required_keys and pressed not in intro.keys_found:
            intro.keys_found.add(pressed)
            app.audio.beep_ok()
            intro_info = lesson_manager.KEY_LOCATIONS[intro.lesson_num]
            needed_keys = sorted(list(intro.required_keys - intro.keys_found))
            intro.intro_items = _build_intro_items(intro_info, needed_keys)
            intro.intro_index = min(intro.intro_index, max(0, len(intro.intro_items) - 1))

            remaining = len(intro.required_keys) - len(intro.keys_found)
            if remaining > 0:
                app.speech.say(f"Found {pressed.upper()}! {remaining} more to go.", priority=True)
            else:
                app.speech.say(f"Found {pressed.upper()}!")

            if intro.keys_found == intro.required_keys:
                app.speech.say("All keys found! Starting lesson.")
                app.begin_lesson_practice(intro.lesson_num)
        else:
            _wrong_key()
    elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_TAB):
        _wrong_key()
