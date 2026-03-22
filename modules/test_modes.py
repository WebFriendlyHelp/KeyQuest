"""Speed test and sentence practice mode implementations.

These routines are extracted from `keyquest.pyw` to keep the main file focused on
app wiring + event loop, while preserving behavior.
"""

import random
import time
import unicodedata

import pygame

from modules import challenge_manager
from modules import currency_manager
from modules import dashboard_manager
from modules import error_logging
from modules import input_utils
from modules import results_formatter
from modules import sentences_manager
from modules import speech_format
from modules import state_manager


COMPOSE_MARK_NAMES = {
    "acute": "acute accent",
    "tilde": "tilde",
    "diaeresis": "diaeresis",
}

COMPOSED_CHARACTERS = {
    "acute": {
        "a": "á",
        "e": "é",
        "i": "í",
        "o": "ó",
        "u": "ú",
        "A": "Á",
        "E": "É",
        "I": "Í",
        "O": "Ó",
        "U": "Ú",
    },
    "tilde": {
        "n": "ñ",
        "N": "Ñ",
    },
    "diaeresis": {
        "u": "ü",
        "U": "Ü",
    },
}

COMPOSE_PUNCTUATION = {
    (pygame.K_1, True): "¡",
    (pygame.K_SLASH, True): "¿",
}


def _is_spanish_topic(topic: str) -> bool:
    """Return True when a practice topic represents Spanish content."""
    return topic.strip().lower().startswith("spanish")


def _get_random_topic_pool(topics):
    """Random-topic pool excludes Spanish, with safe fallback."""
    non_spanish = [topic for topic in topics if not _is_spanish_topic(topic)]
    return non_spanish if non_spanish else list(topics)


def _clear_compose_state(app) -> None:
    app.pending_compose_mark = None


def _normalize_for_match(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _is_shifted(mods: int) -> bool:
    return bool(mods & pygame.KMOD_SHIFT)


def _begin_compose_mark(app, mark: str) -> bool:
    app.pending_compose_mark = mark
    app.speech.say(COMPOSE_MARK_NAMES[mark], priority=True)
    return True


def _handle_spanish_compose_shortcut(app, event, mods: int, *, practice_mode: bool) -> bool:
    if not input_utils.mod_ctrl(mods):
        return False

    if event.key == pygame.K_QUOTE:
        return _begin_compose_mark(app, "diaeresis" if _is_shifted(mods) else "acute")

    if event.key == pygame.K_BACKQUOTE:
        return _begin_compose_mark(app, "tilde")

    punct = COMPOSE_PUNCTUATION.get((event.key, _is_shifted(mods)))
    if punct:
        _clear_compose_state(app)
        if practice_mode:
            process_practice_character(app, punct)
        else:
            process_test_character(app, punct)
        return True

    return False


def _resolve_pending_compose_character(app, ch: str):
    mark = getattr(app, "pending_compose_mark", None)
    if not mark:
        return ch

    mapped = COMPOSED_CHARACTERS.get(mark, {}).get(ch)
    _clear_compose_state(app)
    if mapped:
        return mapped

    app.speech.say(f"{COMPOSE_MARK_NAMES[mark]} canceled.", priority=True)
    return None


def start_test(app) -> None:
    """Start speed test - ask for duration first."""
    app.state.mode = "TEST_SETUP"
    app.state.test = state_manager.TestState(
        running=False,
        start_time=0.0,
        duration_seconds=60,  # Default
        duration_input="",
        remaining=[],
        current="",
        typed="",
        correct_chars=0,
        total_chars=0,
        sentences_completed=0,
        sentences_started=0,
    )
    app.test_setup_view = "topic"
    app.test_setup_topic_options = ["English", "Spanish"]
    current_topic = app.state.settings.sentence_language
    app.test_setup_topic_index = 1 if _is_spanish_topic(current_topic) else 0
    selected = app.test_setup_topic_options[app.test_setup_topic_index]
    app.speech.say(
        f"Speed test setup. {selected}. Use Up and Down to choose English or Spanish. Press Enter to continue. Escape returns to menu.",
        priority=True,
        protect_seconds=3.0,
    )


def handle_test_setup_input(app, event) -> None:
    """Handle duration input for speed test - user types any number."""
    if event.key == pygame.K_ESCAPE:
        if getattr(app, "test_setup_view", "duration") == "duration":
            app.test_setup_view = "topic"
            topic = app.test_setup_topic_options[app.test_setup_topic_index]
            app.speech.say(
                topic,
                priority=True,
            )
        else:
            app.state.mode = "MENU"
            app.say_menu()
        return

    t = app.state.test

    if getattr(app, "test_setup_view", "duration") == "topic":
        if event.key == pygame.K_UP:
            app.test_setup_topic_index = (app.test_setup_topic_index - 1) % len(app.test_setup_topic_options)
            topic = app.test_setup_topic_options[app.test_setup_topic_index]
            app.speech.say(topic, priority=True)
            return
        if event.key == pygame.K_DOWN:
            app.test_setup_topic_index = (app.test_setup_topic_index + 1) % len(app.test_setup_topic_options)
            topic = app.test_setup_topic_options[app.test_setup_topic_index]
            app.speech.say(topic, priority=True)
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            app.test_setup_view = "duration"
            topic = app.test_setup_topic_options[app.test_setup_topic_index]
            topic_name = topic
            app.speech.say(
                f"{topic_name}. How many minutes? Type a number and press Enter.",
                priority=True,
                protect_seconds=2.5,
            )
            return
        return

    if event.key == pygame.K_BACKSPACE:
        if t.duration_input:
            t.duration_input = t.duration_input[:-1]
            app.speech.say(t.duration_input if t.duration_input else "Empty", priority=True)
        return

    if event.key == pygame.K_RETURN:
        if t.duration_input and t.duration_input.isdigit():
            minutes = int(t.duration_input)
            if 1 <= minutes <= 60:
                t.duration_seconds = minutes * 60
                begin_test_typing(app)
            else:
                app.speech.say("Please enter a number between 1 and 60 minutes", priority=True)
        else:
            app.speech.say("Please enter a valid number", priority=True)
        return

    if event.unicode and event.unicode.isdigit():
        t.duration_input += event.unicode
        app.speech.say(event.unicode, priority=True)


def begin_test_typing(app) -> None:
    """Start the actual typing test after duration is selected."""
    app.state.mode = "TEST"
    t = app.state.test
    topic = app.test_setup_topic_options[app.test_setup_topic_index]
    topic_name = topic
    app.state.settings.sentence_language = topic
    app.speed_test_sentences = sentences_manager.load_practice_sentences(
        topic,
        fallback_sentences=sentences_manager.load_speed_test_sentences(),
    )
    t.remaining = random.sample(app.speed_test_sentences, k=len(app.speed_test_sentences))
    minutes = t.duration_seconds // 60
    plural = "minute" if minutes == 1 else "minutes"
    app.speech.say(
        f"Speed test. {topic_name}. {minutes} {plural}. Type each sentence exactly as shown, including capitalization and punctuation. Remember to use capital letters and punctuation. Control Space repeats the remaining text.",
        priority=True,
        protect_seconds=3.0,
    )
    load_next_sentence(app)


def load_next_sentence(app) -> None:
    if not app.state.test.remaining:
        finish_test(app)
        return
    app.state.test.current = app.state.test.remaining.pop(0)
    app.state.test.typed = ""
    app.state.test.sentences_started += 1
    app.speech.say(app.state.test.current, priority=True, protect_seconds=2.0)


def finish_test(app) -> None:
    app.state.test.running = False
    t = app.state.test
    prev_highest_wpm = app.state.settings.highest_wpm

    acc = 0.0
    if t.total_chars:
        acc = (t.correct_chars / t.total_chars) * 100.0

    if t.start_time > 0.0:
        elapsed = max(1e-3, time.time() - t.start_time)
    else:
        elapsed = t.duration_seconds

    words_typed = t.correct_chars / 5.0
    minutes = elapsed / 60.0
    wpm = words_typed / minutes if minutes > 0 else 0.0
    gross_words_typed = t.total_chars / 5.0
    gross_wpm = gross_words_typed / minutes if minutes > 0 else 0.0

    time_minutes = elapsed / 60.0

    app.audio.play_victory()

    errors = t.total_chars - t.correct_chars
    partial_sentences = t.sentences_started - t.sentences_completed
    challenge_summary = ""
    coins_earned = currency_manager.award_coins(app.state.settings, "speed_test_finished")
    earned_parts = []
    if coins_earned:
        earned_parts.append(f"Coins +{coins_earned}")

    challenge = challenge_manager.get_today_challenge()
    if not app.state.settings.daily_challenge_completed and challenge["type"] in (
        "speed_test",
        "speed_test_duration",
    ):
        progress_data = {"duration": elapsed, "words_typed": words_typed, "wpm": wpm}
        progress = challenge_manager.check_challenge_progress(
            challenge["type"],
            challenge["target"],
            progress_data,
        )
        if progress["completed"]:
            challenge_result = challenge_manager.complete_daily_challenge(app.state.settings)
            challenge_coins = currency_manager.award_coins(app.state.settings, "daily_challenge_completed")
            challenge_summary = (
                f"Daily challenge complete. Earned {challenge_result['xp_earned']} XP"
                f"{f' and {challenge_coins} coins' if challenge_coins else ''}."
            )

    results_for_dialog = results_formatter.ResultsFormatter.format_speed_test_results(
        wpm=wpm,
        gross_wpm=gross_wpm,
        accuracy=acc,
        time_minutes=time_minutes,
        sentences_completed=t.sentences_completed,
        partial_sentences=partial_sentences,
        words_typed=words_typed,
        correct_chars=t.correct_chars,
        errors=errors,
        total_chars=t.total_chars,
    )
    pet_result = None

    try:
        pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, results_for_dialog.encode("utf-8"))
    except Exception as e:
        error_logging.log_exception(e)

    if wpm > app.state.settings.highest_wpm:
        app.state.settings.highest_wpm = wpm

    if hasattr(app, "apply_pet_session_progress"):
        pet_result = app.apply_pet_session_progress(
            recent_performance={
                "new_best_wpm": wpm > prev_highest_wpm,
                "new_best_accuracy": False,
                "accuracy": acc,
                "session_duration": time_minutes,
                "streak_broken": False,
            },
            xp_amount=max(8, int(words_typed) + int(t.sentences_completed * 2)),
        )

    if challenge_summary:
        earned_parts.append(challenge_summary)
    if pet_result and pet_result.get("has_pet"):
        results_for_dialog += f"\n\nPet status: {pet_result.get('summary', '')}"
        earned_parts.append(f"Pet XP +{pet_result.get('xp_awarded', 0)}")
    if coins_earned:
        results_for_dialog += f"\n\n{currency_manager.get_coin_announcement('speed_test_finished', coins_earned)}"

    dashboard_manager.record_session(
        app.state.settings,
        {
            "type": "speed_test",
            "summary": (
                f"Speed Test ({sentences_manager.get_practice_topic_display_name(app.state.settings.sentence_language)})"
            ),
            "wpm": wpm,
            "accuracy": acc,
            "duration": elapsed,
            "earned": " ".join(earned_parts).strip(),
        },
    )

    if challenge_summary:
        results_for_dialog += f"\n\n{challenge_summary}"

    app.show_results_dialog(results_for_dialog)

    app.save_progress()

    app.state.mode = "MENU"
    app.speech.say(
        f"Speed test complete! Corrected words per minute {wpm:.1f}. Total words per minute {gross_wpm:.1f}. Accuracy {acc:.1f} percent.",
        priority=True,
        protect_seconds=3.0,
    )
    app.say_menu()


def handle_test_input(app, event, mods: int) -> None:
    if event.key == pygame.K_ESCAPE:
        _clear_compose_state(app)
        app.state.mode = "MENU"
        app.say_menu()
    elif event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
        speak_test_remaining(app)
    elif _handle_spanish_compose_shortcut(app, event, mods, practice_mode=False):
        return
    elif getattr(app, "pending_compose_mark", None) and event.key == pygame.K_BACKSPACE:
        app.speech.say(f"{COMPOSE_MARK_NAMES[app.pending_compose_mark]} canceled.", priority=True)
        _clear_compose_state(app)
    else:
        process_test_typing(app, event)


def process_test_typing(app, event) -> None:
    ch = None
    if event.unicode and event.unicode.isprintable():
        ch = _resolve_pending_compose_character(app, event.unicode)
    elif event.key == pygame.K_BACKSPACE:
        _clear_compose_state(app)
        _record_typing_error(app, app.state.test)
        return
    else:
        return

    if ch:
        process_test_character(app, ch)


def process_test_character(app, ch: str) -> None:
    t = app.state.test
    if not t.running:
        t.start_time = time.time()
        t.running = True
    pos = len(t.typed)
    current = _normalize_for_match(t.current)
    if pos < len(current) and _normalize_for_match(ch) == current[pos]:
        t.typed += ch
        t.correct_chars += 1
        t.total_chars += 1

        if _normalize_for_match(t.typed) == current:
            app.audio.play_success()
            t.sentences_completed += 1
            load_next_sentence(app)
    else:
        _record_typing_error(app, t)


def speak_test_remaining(app) -> None:
    current = app.state.test.current
    typed = app.state.test.typed
    remaining = current[len(typed) :] if current.startswith(typed) else current
    app.speech.say(
        speech_format.build_remaining_text_feedback(remaining),
        priority=True,
        protect_seconds=2.0,
    )


def start_practice(app) -> None:
    """Show sentence practice setup with random/select topic options."""
    app.state.mode = "PRACTICE_SETUP"
    app.practice_topic_options = sentences_manager.get_sentence_topics_from_folder()
    if not app.practice_topic_options:
        app.practice_topic_options = sentences_manager.get_practice_topics()
    app.practice_setup_options = ["Random Topic", "Choose Topic"]
    app.practice_setup_index = 0
    app.practice_topic_index = 0
    app.practice_setup_view = "menu"
    app.speech.say(
        "Sentence practice setup. Random Topic. Use Up and Down arrows. Press Enter to select. Remember to use capital letters and punctuation. Escape returns to menu.",
        priority=True,
        protect_seconds=3.0,
    )


def handle_practice_setup_input(app, event, mods: int) -> None:
    """Handle sentence practice setup input."""
    if app.practice_setup_view == "menu":
        if event.key == pygame.K_ESCAPE:
            app.state.mode = "MENU"
            app.say_menu()
            return
        if event.key == pygame.K_UP:
            app.practice_setup_index = (app.practice_setup_index - 1) % len(app.practice_setup_options)
            app.speech.say(app.practice_setup_options[app.practice_setup_index])
            return
        if event.key == pygame.K_DOWN:
            app.practice_setup_index = (app.practice_setup_index + 1) % len(app.practice_setup_options)
            app.speech.say(app.practice_setup_options[app.practice_setup_index])
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = app.practice_setup_options[app.practice_setup_index]
            if choice == "Random Topic":
                pool = _get_random_topic_pool(app.practice_topic_options)
                topic = random.choice(pool)
                _begin_practice_session(app, topic)
            else:
                app.practice_setup_view = "topics"
                app.practice_topic_index = 0
                current = app.practice_topic_options[app.practice_topic_index]
                current_name = sentences_manager.get_practice_topic_display_name(current)
                app.speech.say(
                    f"Choose topic. {current_name}. Use Up and Down arrows. Press Enter to start. Escape returns.",
                    priority=True,
                    protect_seconds=3.0,
                )
            return
        return

    if event.key == pygame.K_ESCAPE:
        app.practice_setup_view = "menu"
        app.speech.say(app.practice_setup_options[app.practice_setup_index], priority=True)
        return
    if event.key == pygame.K_UP:
        app.practice_topic_index = (app.practice_topic_index - 1) % len(app.practice_topic_options)
        app.speech.say(
            sentences_manager.get_practice_topic_display_name(
                app.practice_topic_options[app.practice_topic_index]
            )
        )
        return
    if event.key == pygame.K_DOWN:
        app.practice_topic_index = (app.practice_topic_index + 1) % len(app.practice_topic_options)
        app.speech.say(
            sentences_manager.get_practice_topic_display_name(
                app.practice_topic_options[app.practice_topic_index]
            )
        )
        return
    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
        topic = app.practice_topic_options[app.practice_topic_index]
        _begin_practice_session(app, topic)


def _begin_practice_session(app, topic: str) -> None:
    """Start sentence practice mode - type sentences until pressing Escape 3 times."""
    app.state.settings.sentence_language = topic
    app.practice_sentences = sentences_manager.load_practice_sentences(topic)
    app.state.mode = "PRACTICE"
    app.state.test = state_manager.TestState(
        running=True,
        start_time=time.time(),
        duration_seconds=0,  # No time limit
        duration_input="",
        remaining=[],
        current="",
        typed="",
        correct_chars=0,
        total_chars=0,
        sentences_completed=0,
        sentences_started=0,
    )

    if app.practice_sentences:
        app.state.test.remaining = random.sample(
            app.practice_sentences,
            k=min(len(app.practice_sentences), 500),
        )
    else:
        app.state.test.remaining = random.sample(app.speed_test_sentences, k=len(app.speed_test_sentences))

    app.speech.say(
        f"Sentence practice. Topic {sentences_manager.get_practice_topic_display_name(topic)}. Type each sentence exactly as shown, including capitalization and punctuation. Remember to use capital letters and punctuation. Control Space repeats. Escape, press 3 times to finish.",
        priority=True,
        protect_seconds=3.0,
    )
    load_next_practice_sentence(app)


def load_next_practice_sentence(app) -> None:
    """Load next sentence for practice mode."""
    if not app.state.test.remaining:
        if app.practice_sentences:
            app.state.test.remaining = random.sample(
                app.practice_sentences,
                k=min(len(app.practice_sentences), 500),
            )
        else:
            app.state.test.remaining = random.sample(app.speed_test_sentences, k=len(app.speed_test_sentences))

    app.state.test.current = app.state.test.remaining.pop(0)
    app.state.test.typed = ""
    app.state.test.sentences_started += 1
    app.speech.say(app.state.test.current, priority=True, protect_seconds=2.0)


def finish_practice(app) -> None:
    """Finish sentence practice and show results."""
    app.state.test.running = False
    t = app.state.test
    prev_highest_wpm = app.state.settings.highest_wpm

    acc = 0.0
    if t.total_chars:
        acc = (t.correct_chars / t.total_chars) * 100.0

    if t.start_time > 0.0:
        elapsed = max(1e-3, time.time() - t.start_time)
    else:
        elapsed = 1.0

    words_typed = t.correct_chars / 5.0
    minutes = elapsed / 60.0
    wpm = words_typed / minutes if minutes > 0 else 0.0
    gross_words_typed = t.total_chars / 5.0
    gross_wpm = gross_words_typed / minutes if minutes > 0 else 0.0
    time_minutes = elapsed / 60.0

    app.audio.play_victory()

    errors = t.total_chars - t.correct_chars
    partial_sentences = t.sentences_started - t.sentences_completed
    challenge_summary = ""
    coins_earned = currency_manager.award_coins(app.state.settings, "sentence_practice_session")
    earned_parts = []
    if coins_earned:
        earned_parts.append(f"Coins +{coins_earned}")

    challenge = challenge_manager.get_today_challenge()
    if not app.state.settings.daily_challenge_completed and challenge["type"] == "sentence_practice":
        progress = challenge_manager.check_challenge_progress(
            "sentence_practice",
            challenge["target"],
            {"sentences_completed": t.sentences_completed},
        )
        if progress["completed"]:
            challenge_result = challenge_manager.complete_daily_challenge(app.state.settings)
            challenge_coins = currency_manager.award_coins(app.state.settings, "daily_challenge_completed")
            challenge_summary = (
                f"Daily challenge complete. Earned {challenge_result['xp_earned']} XP"
                f"{f' and {challenge_coins} coins' if challenge_coins else ''}."
            )

    results_for_dialog = results_formatter.ResultsFormatter.format_sentence_practice_results(
        wpm=wpm,
        gross_wpm=gross_wpm,
        accuracy=acc,
        time_minutes=time_minutes,
        sentences_completed=t.sentences_completed,
        partial_sentences=partial_sentences,
        words_typed=words_typed,
        correct_chars=t.correct_chars,
        errors=errors,
        total_chars=t.total_chars,
    )
    pet_result = None

    try:
        pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, results_for_dialog.encode("utf-8"))
    except Exception as e:
        error_logging.log_exception(e)

    if wpm > app.state.settings.highest_wpm:
        app.state.settings.highest_wpm = wpm

    if hasattr(app, "apply_pet_session_progress"):
        pet_result = app.apply_pet_session_progress(
            recent_performance={
                "new_best_wpm": wpm > prev_highest_wpm,
                "new_best_accuracy": False,
                "accuracy": acc,
                "session_duration": time_minutes,
                "streak_broken": False,
            },
            xp_amount=max(8, int(words_typed) + int(t.sentences_completed * 2)),
        )

    if challenge_summary:
        earned_parts.append(challenge_summary)
    if pet_result and pet_result.get("has_pet"):
        results_for_dialog += f"\n\nPet status: {pet_result.get('summary', '')}"
        earned_parts.append(f"Pet XP +{pet_result.get('xp_awarded', 0)}")
    if coins_earned:
        results_for_dialog += f"\n\n{currency_manager.get_coin_announcement('sentence_practice_session', coins_earned)}"

    dashboard_manager.record_session(
        app.state.settings,
        {
            "type": "sentence_practice",
            "summary": (
                f"Sentence Practice ({sentences_manager.get_practice_topic_display_name(app.state.settings.sentence_language)})"
            ),
            "wpm": wpm,
            "accuracy": acc,
            "duration": elapsed,
            "earned": " ".join(earned_parts).strip(),
        },
    )

    if challenge_summary:
        results_for_dialog += f"\n\n{challenge_summary}"

    app.show_results_dialog(results_for_dialog)

    app.save_progress()

    app.state.mode = "MENU"
    app.speech.say(
        f"Sentence practice complete! Corrected words per minute {wpm:.1f}. Total words per minute {gross_wpm:.1f}. Accuracy {acc:.1f} percent.",
        priority=True,
        protect_seconds=3.0,
    )
    app.say_menu()


def handle_practice_input(app, event, mods: int) -> None:
    """Handle input during sentence practice mode."""
    if event.key == pygame.K_ESCAPE:
        _clear_compose_state(app)
        return
    if event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
        speak_practice_remaining(app)
        return
    if _handle_spanish_compose_shortcut(app, event, mods, practice_mode=True):
        return
    if getattr(app, "pending_compose_mark", None) and event.key == pygame.K_BACKSPACE:
        app.speech.say(f"{COMPOSE_MARK_NAMES[app.pending_compose_mark]} canceled.", priority=True)
        _clear_compose_state(app)
        return

    process_practice_typing(app, event)


def process_practice_typing(app, event) -> None:
    """Process typing for sentence practice - same as speed test."""
    ch = None
    if event.unicode and event.unicode.isprintable():
        ch = _resolve_pending_compose_character(app, event.unicode)
    elif event.key == pygame.K_BACKSPACE:
        _clear_compose_state(app)
        _record_typing_error(app, app.state.test)
        return
    if not ch:
        return

    process_practice_character(app, ch)


def process_practice_character(app, ch: str) -> None:
    """Process a resolved practice-mode character."""
    t = app.state.test
    pos = len(t.typed)
    current = _normalize_for_match(t.current)

    if pos < len(current) and _normalize_for_match(ch) == current[pos]:
        t.typed += ch
        t.correct_chars += 1
        t.total_chars += 1

        if _normalize_for_match(t.typed) == current:
            app.audio.play_success()
            t.sentences_completed += 1
            load_next_practice_sentence(app)
    else:
        _record_typing_error(app, t)


def speak_practice_remaining(app) -> None:
    """Speak remaining text for sentence practice."""
    current = app.state.test.current
    typed = app.state.test.typed
    remaining = current[len(typed) :] if current.startswith(typed) else current
    app.speech.say(
        speech_format.build_remaining_text_feedback(remaining),
        priority=True,
        protect_seconds=2.0,
    )


def _record_typing_error(app, test_state) -> None:
    """Handle a typing error without modifying already typed text."""
    pos = len(test_state.typed)
    remaining = test_state.current[pos:]
    app.audio.beep_bad()
    app.trigger_flash((100, 0, 0), 0.12)
    app.speech.say(
        speech_format.build_remaining_text_feedback(remaining),
        priority=True,
        protect_seconds=1.5,
    )
    test_state.total_chars += 1
