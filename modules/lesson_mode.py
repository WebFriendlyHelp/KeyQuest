import os
import random
import time

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
except Exception:  # pragma: no cover
    pygame = None

from modules import badge_manager
from modules import challenge_manager
from modules import currency_manager
from modules import dashboard_manager
from modules import input_utils
from modules import key_analytics
from modules import lesson_manager
from modules import quest_manager
from modules import results_formatter
from modules import speech_format
from modules import xp_manager

# Star-rating thresholds
_STARS_3_ACCURACY = 95.0
_STARS_2_ACCURACY = 85.0
_STARS_1_ACCURACY = 70.0
_STARS_3_WPM = 30.0
_STARS_2_WPM = 20.0  # matches lesson_manager.MIN_WPM


def _require_pygame() -> None:
    if pygame is None:  # pragma: no cover
        raise RuntimeError("pygame is required for lesson mode input handling")


def _make_early_sequence(allowed_list) -> str:
    """Build a 3-4 key memory-friendly sequence for early lessons."""
    length = random.randint(3, 4)
    sequence = []
    for i in range(length):
        choices = allowed_list
        if i == 0 or i == length - 1:
            non_space = [ch for ch in allowed_list if ch != " "]
            if non_space:
                choices = non_space
        if sequence and sequence[-1] == " ":
            non_space = [ch for ch in choices if ch != " "]
            if non_space:
                choices = non_space
        sequence.append(random.choice(choices))
    return "".join(sequence)


def _normalize_early_target(candidate: str, allowed_list) -> str:
    """Force early-lesson targets to 3-4 keys for easier memorization."""
    if len(candidate) in (3, 4) and not candidate.startswith(" ") and not candidate.endswith(" ") and "  " not in candidate:
        return candidate
    return _make_early_sequence(allowed_list)


def _early_completion_allowed(stage: int) -> bool:
    """Require full batches for early key-acquisition lessons."""
    return stage >= lesson_manager.WPM_REQUIRED_FROM_LESSON


def _build_front_loaded_early_batch(stage: int, allowed_list, valid_words, valid_phrases) -> list[str]:
    """Front-load early lessons with repeated new-key drills before mixed practice."""
    batch: list[str] = []
    new_keys = [key for key in sorted(lesson_manager.STAGE_LETTERS[stage]) if key != " "]
    prior_keys = [key for key in allowed_list if key not in new_keys and key != " "]

    for key in new_keys:
        batch.extend([key * 3, key * 2, key * 4])
        if prior_keys:
            anchor = prior_keys[0]
            batch.extend(
                [
                    f"{anchor}{key}{anchor}{key}",
                    f"{key}{anchor}{anchor}{key}",
                    f"{key}{anchor}{key}{key}",
                ]
            )

    tail = []
    while len(batch) + len(tail) < lesson_manager.LESSON_BATCH:
        roll = random.random()
        target = None

        if valid_phrases and roll < 0.15:
            target = random.choice(valid_phrases)
        elif valid_words and roll < 0.45:
            target = random.choice(valid_words)
        else:
            target = _make_early_sequence(allowed_list)

        tail.append(_normalize_early_target(target, allowed_list))

    random.shuffle(tail)
    return (batch + tail)[: lesson_manager.LESSON_BATCH]


def build_lesson_batch(app) -> None:
    """Build adaptive lesson batch based on performance with high randomization."""
    stage = app.state.lesson.stage
    lesson_state = app.state.lesson

    if stage in lesson_manager.SPECIAL_KEY_COMMANDS:
        commands = lesson_manager.SPECIAL_KEY_COMMANDS[stage]
        lesson_state.batch_words = [cmd[1] for cmd in commands]
        lesson_state.batch_instructions = [cmd[0] for cmd in commands]
        lesson_state.index = 0
        lesson_state.typed = ""
        lesson_state.start_time = time.time()
        return

    allowed = set().union(*lesson_manager.STAGE_LETTERS[: stage + 1])
    allowed_list = sorted(allowed)
    early_stage = stage < lesson_manager.WPM_REQUIRED_FROM_LESSON
    valid_phrases = lesson_manager.filter_stage_content(
        stage,
        lesson_manager.STAGE_PHRASES.get(stage, []),
    )
    valid_words = lesson_manager.filter_stage_content(
        stage,
        lesson_manager.STAGE_WORDS.get(stage, []),
    )

    struggling = lesson_state.tracker.get_struggling_keys()
    batch = []

    if lesson_state.review_mode and struggling:
        lesson_state.review_keys = struggling[:3]
        for _ in range(lesson_manager.LESSON_BATCH):
            length = random.randint(3, 4) if early_stage else random.randint(1, 3)
            word = "".join(random.choice(lesson_state.review_keys) for _ in range(length))
            batch.append(word)
    elif early_stage:
        batch = _build_front_loaded_early_batch(stage, allowed_list, valid_words, valid_phrases)
    else:
        for _ in range(lesson_manager.LESSON_BATCH):
            roll = random.random()
            target = None

            if lesson_state.use_words and valid_phrases and roll < 0.25:
                target = random.choice(valid_phrases)
            elif lesson_state.use_words and valid_words and roll < 0.60:
                target = random.choice(valid_words)
            else:
                length = random.randint(3, 4) if early_stage else random.randint(1, 3)
                if random.random() < 0.3:
                    subset = random.sample(
                        allowed_list,
                        min(len(allowed_list), random.randint(2, 4)),
                    )
                    target = "".join(random.choice(subset) for _ in range(length))
                else:
                    target = "".join(random.choice(allowed_list) for _ in range(length))

            if early_stage:
                target = _normalize_early_target(target, allowed_list)
            batch.append(target)

        random.shuffle(batch)

    # Always start with a short item so the first prompt isn't overwhelming
    short_idx = next((i for i, w in enumerate(batch) if len(w) <= 4), None)
    if short_idx is not None and short_idx != 0:
        batch.insert(0, batch.pop(short_idx))

    lesson_state.batch_words = batch
    lesson_state.index = 0
    lesson_state.typed = ""
    lesson_state.start_time = time.time()


def lesson_prompt(app) -> None:
    lesson_state = app.state.lesson
    target = lesson_state.batch_words[lesson_state.index]

    if lesson_state.batch_instructions and lesson_state.index < len(lesson_state.batch_instructions):
        instruction = lesson_state.batch_instructions[lesson_state.index]
        app.speech.say(instruction, priority=True, protect_seconds=2.0)
        return

    remaining = target[len(lesson_state.typed) :]
    natural_words = lesson_manager.get_stage_natural_words(lesson_state.stage)
    speakable = speech_format.spell_text_for_typing_instruction(remaining, natural_words=natural_words)
    app.speech.say(f"Type {speakable}", priority=True, protect_seconds=2.0)


def extend_lesson_practice(app) -> None:
    """Extend lesson with additional practice items for struggling students."""
    _require_pygame()
    lesson_state = app.state.lesson
    stage = lesson_state.stage
    allowed = set().union(*lesson_manager.STAGE_LETTERS[: stage + 1])
    allowed_list = sorted(allowed)

    struggling = lesson_state.tracker.get_struggling_keys()
    items_to_add = min(10, lesson_manager.MAX_LESSON_BATCH - len(lesson_state.batch_words))

    new_items = []
    for _ in range(items_to_add):
        if struggling and random.random() < 0.6:
            length = random.randint(2, 3)
            word_chars = []
            for _ in range(length):
                if random.random() < 0.7:
                    word_chars.append(random.choice(struggling))
                else:
                    word_chars.append(random.choice(allowed_list))
            new_items.append("".join(word_chars))
        else:
            length = random.randint(2, 4)
            new_items.append("".join(random.choice(allowed_list) for _ in range(length)))

    lesson_state.batch_words.extend(new_items)
    app.speech.say("Let's practice a bit more.", priority=True, protect_seconds=2.0)
    pygame.time.wait(1500)


def check_and_inject_adaptive_content(app) -> None:
    """Dynamically adjust lesson difficulty mid-batch based on real-time performance."""
    lesson_state = app.state.lesson

    if lesson_state.index % 5 != 0:
        return

    struggling = lesson_state.tracker.get_struggling_keys()
    if not (struggling and lesson_state.tracker.consecutive_wrong >= 2):
        return

    stage = lesson_state.stage
    allowed = set().union(*lesson_manager.STAGE_LETTERS[: stage + 1])

    good_keys = []
    for key in allowed:
        if key in struggling:
            continue
        perf = lesson_state.tracker.key_performance.get(key)
        if perf and perf.recent_accuracy() > 0.75:
            good_keys.append(key)

    if not good_keys:
        return

    easier_words = []
    for _ in range(3):
        length = random.randint(2, 3)
        word = "".join(random.choice(good_keys) for _ in range(length))
        easier_words.append(word)

    for _ in range(2):
        length = random.randint(2, 3)
        word_chars = [random.choice(good_keys) for _ in range(length - 1)]
        word_chars.append(random.choice(struggling))
        random.shuffle(word_chars)
        easier_words.append("".join(word_chars))

    lesson_state.batch_words = (
        lesson_state.batch_words[: lesson_state.index]
        + easier_words
        + lesson_state.batch_words[lesson_state.index :]
    )


def next_lesson_item(app) -> None:
    _require_pygame()
    lesson_state = app.state.lesson
    lesson_state.index += 1
    lesson_state.typed = ""

    check_and_inject_adaptive_content(app)

    if lesson_state.index >= len(lesson_state.batch_words):
        if lesson_state.tracker.should_slow_down() and len(lesson_state.batch_words) < lesson_manager.MAX_LESSON_BATCH:
            extend_lesson_practice(app)
            lesson_prompt(app)
        else:
            if app.state.mode == "FREE_PRACTICE":
                app.end_free_practice()
            else:
                evaluate_lesson_performance(app)
    else:
        lesson_prompt(app)


def calculate_lesson_stars(lesson_num: int, accuracy: float, wpm: float) -> int:
    """Calculate star rating (1-3) based on lesson performance."""
    if lesson_num < lesson_manager.WPM_REQUIRED_FROM_LESSON:
        if accuracy >= _STARS_3_ACCURACY:
            return 3
        if accuracy >= _STARS_2_ACCURACY:
            return 2
        if accuracy >= _STARS_1_ACCURACY:
            return 1
        return 0

    if accuracy >= _STARS_3_ACCURACY and wpm >= _STARS_3_WPM:
        return 3
    if accuracy >= _STARS_2_ACCURACY and wpm >= _STARS_2_WPM:
        return 2
    if accuracy >= _STARS_1_ACCURACY:
        return 1
    return 0


def evaluate_lesson_performance(app) -> None:
    """Evaluate performance and decide next action."""
    _require_pygame()
    lesson_state = app.state.lesson
    lesson_state.end_time = time.time()

    app.audio.play_victory()

    duration = lesson_state.end_time - lesson_state.start_time
    accuracy = lesson_state.tracker.overall_accuracy() * 100
    total_attempts = lesson_state.tracker.total_attempts
    total_correct = lesson_state.tracker.total_correct
    total_errors = total_attempts - total_correct
    wpm = lesson_state.tracker.calculate_wpm(duration)
    minutes = duration / 60.0 if duration > 0 else 0.0
    gross_wpm = ((total_attempts / 5.0) / minutes) if minutes > 0 else 0.0

    stars = calculate_lesson_stars(lesson_state.stage, accuracy, wpm)

    prev_stars = app.state.settings.lesson_stars.get(lesson_state.stage, 0)
    if stars > prev_stars:
        app.state.settings.lesson_stars[lesson_state.stage] = stars

    prev_wpm = app.state.settings.lesson_best_wpm.get(lesson_state.stage, 0.0)
    if wpm > prev_wpm:
        app.state.settings.lesson_best_wpm[lesson_state.stage] = wpm

    prev_accuracy = app.state.settings.lesson_best_accuracy.get(lesson_state.stage, 0.0)
    if accuracy > prev_accuracy:
        app.state.settings.lesson_best_accuracy[lesson_state.stage] = accuracy

    app.state.settings.total_lessons_completed += 1
    app.state.settings.total_practice_time += duration
    if wpm > app.state.settings.highest_wpm:
        app.state.settings.highest_wpm = wpm

    lesson_stats = {"accuracy": accuracy, "wpm": wpm, "duration": duration}
    new_badges = badge_manager.check_badges(app.state.settings, lesson_stats)
    for badge_id in new_badges:
        app.state.settings.earned_badges.add(badge_id)
        app.state.settings.badge_notifications.append(badge_id)

    xp_earned = xp_manager.XP_AWARDS["lesson"]
    xp_earned += total_correct * xp_manager.XP_AWARDS["keystroke"]
    if accuracy >= 100:
        xp_earned += xp_manager.XP_AWARDS["perfect_accuracy"]
    if wpm > prev_wpm and wpm >= 20:
        xp_earned += xp_manager.XP_AWARDS["new_best_wpm"]
    if accuracy > prev_accuracy:
        xp_earned += xp_manager.XP_AWARDS["new_best_accuracy"]

    xp_result = xp_manager.award_xp(app.state.settings, xp_earned, f"Lesson {lesson_state.stage} completed")
    coins_earned = currency_manager.award_coins(app.state.settings, "lesson_completed")
    earned_parts = [f"XP +{xp_earned}"]
    if coins_earned:
        earned_parts.append(f"Coins +{coins_earned}")

    quest_progress_data = {
        "lesson_num": lesson_state.stage,
        "accuracy": accuracy,
        "wpm": wpm,
        "duration": duration,
    }
    newly_completed_quests = quest_manager.check_all_active_quests(app.state.settings, quest_progress_data)
    for quest_id in newly_completed_quests:
        quest = quest_manager.get_quest_info(quest_id)
        if quest:
            xp_manager.award_xp(app.state.settings, quest["xp_reward"], f"Quest: {quest['name']}")

    challenge = challenge_manager.get_today_challenge()
    challenge_summary = ""
    if not app.state.settings.daily_challenge_completed:
        if challenge["type"] == "lesson_accuracy":
            progress = challenge_manager.check_challenge_progress(
                "lesson_accuracy",
                challenge["target"],
                {"accuracy": accuracy},
            )
            if progress["completed"]:
                challenge_result = challenge_manager.complete_daily_challenge(app.state.settings)
                xp_manager.award_xp(app.state.settings, challenge_result["xp_earned"], "Daily Challenge")
                challenge_coins = currency_manager.award_coins(app.state.settings, "daily_challenge_completed")
                challenge_summary = (
                    f"Daily challenge complete. Earned {challenge_result['xp_earned']} XP"
                    f"{f' and {challenge_coins} coins' if challenge_coins else ''}."
                )

    session_data = {
        "type": "lesson",
        "summary": f"Lesson {lesson_state.stage}",
        "lesson_num": lesson_state.stage,
        "wpm": wpm,
        "accuracy": accuracy,
        "duration": duration,
        "stars": stars,
        "xp_earned": xp_earned,
        "earned": ", ".join(earned_parts),
    }
    if challenge_summary:
        session_data["earned"] += f". {challenge_summary}"
    dashboard_manager.record_session(app.state.settings, session_data)

    key_perf_dict = None
    if lesson_state.tracker.key_performance:
        key_perf_dict = {}
        for key, perf in lesson_state.tracker.key_performance.items():
            key_perf_dict[key] = {
                "recent_accuracy": perf.recent_accuracy(),
                "correct": perf.correct,
                "attempts": perf.attempts,
            }

    unlocked_new = False
    unlocked_lesson_info = None
    should_advance = lesson_state.tracker.should_advance(
        lesson_num=lesson_state.stage,
        duration_seconds=duration,
        wpm_required_from_lesson=lesson_manager.WPM_REQUIRED_FROM_LESSON,
        min_wpm=lesson_manager.MIN_WPM,
    )
    should_review = lesson_state.tracker.should_slow_down()
    needs_wpm = (
        lesson_state.stage >= lesson_manager.WPM_REQUIRED_FROM_LESSON
        and wpm < lesson_manager.MIN_WPM
        and accuracy >= 80
    )

    if should_advance:
        next_lesson = min(lesson_state.stage + 1, len(lesson_manager.STAGE_LETTERS) - 1)
        if next_lesson not in app.state.settings.unlocked_lessons:
            app.state.settings.unlocked_lessons.add(next_lesson)
            unlocked_new = True
            next_name = (
                lesson_manager.LESSON_NAMES[next_lesson]
                if next_lesson < len(lesson_manager.LESSON_NAMES)
                else f"Lesson {next_lesson}"
            )
            new_keys = (
                lesson_manager.STAGE_LETTERS[next_lesson]
                if next_lesson < len(lesson_manager.STAGE_LETTERS)
                else set()
            )
            unlocked_lesson_info = {"name": next_name, "keys": new_keys}

        app.state.settings.current_lesson = next_lesson
        lesson_state.stage = next_lesson
        app.save_progress()
    elif should_review:
        lesson_state.review_mode = True

    results_text, action = results_formatter.ResultsFormatter.format_lesson_results(
        accuracy=accuracy,
        wpm=wpm,
        gross_wpm=gross_wpm,
        total_correct=total_correct,
        total_errors=total_errors,
        duration=duration,
        key_performance=key_perf_dict,
        unlocked_lesson=unlocked_lesson_info,
        should_advance=should_advance,
        should_review=should_review,
        needs_wpm=needs_wpm,
        min_wpm=lesson_manager.MIN_WPM,
        stars=stars,
        prev_stars=prev_stars,
    )

    if unlocked_new:
        app.audio.play_unlock()
        pygame.time.wait(500)

    app.show_badge_notifications()
    app.show_level_up_notification(xp_result)
    app.show_quest_notifications()
    pet_result = app.apply_pet_session_progress(
        recent_performance={
            "new_best_wpm": wpm > prev_wpm,
            "new_best_accuracy": accuracy > prev_accuracy,
            "accuracy": accuracy,
            "session_duration": duration / 60.0,
            "streak_broken": False,
        },
        xp_amount=max(10, int(xp_earned * 0.25)),
    )

    if challenge_summary:
        results_text += f"\n\n{challenge_summary}"
    if coins_earned:
        results_text += f"\n\n{currency_manager.get_coin_announcement('lesson_completed', coins_earned)}"
    if pet_result.get("has_pet"):
        results_text += f"\n\nPet status: {pet_result.get('summary', '')}"

    app.show_guided_results_dialog(
        results_text,
        title="Lesson Results",
        enter_target="continue to your choices",
    )

    app.state.mode = "RESULTS"

    completed_lesson = lesson_state.stage - 1 if action == "advance" else lesson_state.stage
    completed_name = (
        lesson_manager.LESSON_NAMES[completed_lesson]
        if completed_lesson < len(lesson_manager.LESSON_NAMES)
        else f"Lesson {completed_lesson}"
    )

    # Always offer the next lesson so the user is never stuck.
    # If they officially advanced, current_lesson is already the new one;
    # otherwise offer the lesson after the one they just completed.
    next_lesson = app.state.settings.current_lesson if action == "advance" else completed_lesson + 1
    next_lesson = min(next_lesson, len(lesson_manager.STAGE_LETTERS) - 1)
    next_name = (
        lesson_manager.LESSON_NAMES[next_lesson]
        if next_lesson < len(lesson_manager.LESSON_NAMES)
        else f"Lesson {next_lesson}"
    )

    if action == "advance" and app.state.settings.auto_start_next_lesson:
        app.state.results_action = ""
        app.state.results_next_lesson = next_lesson
        app.speech.say(f"Starting {next_name}.", priority=True, protect_seconds=2.0)
        pygame.time.wait(500)
        app.start_lesson(next_lesson)
        return

    options = []
    if next_lesson != completed_lesson:
        options.append(f"Start next lesson: {next_name}")
    options.append(f"Try {completed_name} again")
    options.append("Return to main menu")

    app.state.results_action = "advance" if action == "advance" else "retry"
    app.state.results_next_lesson = next_lesson
    app.state.results_retry_lesson = completed_lesson
    app._configure_results_menu(
        title="Lesson Complete",
        body=f"Next lesson ready: {next_name}." if action == "advance" else f"Keep practising {completed_name}.",
        options=options,
    )
    app._announce_results_menu()


def handle_lesson_input(app, event, mods: int) -> None:
    _require_pygame()
    if event.key == pygame.K_ESCAPE:
        app.state.mode = "MENU"
        app.say_menu()
    elif event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
        lesson_prompt(app)
    else:
        process_lesson_typing(app, event)


def process_lesson_typing(app, event) -> None:
    _require_pygame()
    target = app.current_word()
    lesson_state = app.state.lesson

    if lesson_state.batch_instructions:
        if event.key in lesson_manager.SPECIAL_KEY_NAMES:
            pressed_key_name = lesson_manager.SPECIAL_KEY_NAMES[event.key]
            if pressed_key_name == target:
                app.audio.beep_ok()
                app.trigger_flash((0, 80, 0), 0.12)
                lesson_state.tracker.record_keystroke(target, True)
                key_analytics.record_keystroke(app.state.settings, target.lower(), True)
                next_lesson_item(app)
                return
            app.audio.beep_bad()
            app.trigger_flash((100, 0, 0), 0.12)
            lesson_state.tracker.record_keystroke(pressed_key_name, False)
            key_analytics.record_keystroke(app.state.settings, pressed_key_name.lower(), False)
            app.speech.say(f"That was {pressed_key_name}. Try {target}.", priority=True)
        return

    if event.unicode and event.unicode.isprintable():
        ch = event.unicode.lower()
    elif event.key == pygame.K_BACKSPACE:
        lesson_state.typed = lesson_state.typed[:-1]
        return
    else:
        return

    lesson_state.typed += ch
    typed = lesson_state.typed

    if not target.startswith(typed):
        app.audio.beep_bad()
        app.trigger_flash((100, 0, 0), 0.12)
        lesson_state.tracker.record_keystroke(ch, False)
        key_analytics.record_keystroke(app.state.settings, ch.lower(), False)
        lesson_state.typed = typed[:-1]
        lesson_state.errors_in_row += 1
        app.provide_key_guidance(ch, target, lesson_state.typed)
        return

    lesson_state.errors_in_row = 0
    lesson_state.show_guidance = False
    lesson_state.guidance_message = ""
    lesson_state.hint_message = ""
    lesson_state.tracker.record_keystroke(ch, True)
    key_analytics.record_keystroke(app.state.settings, ch.lower(), True)

    if typed == target:
        app.audio.play_success()
        next_lesson_item(app)
    else:
        percentage = len(typed) / len(target)
        app.audio.play_progressive(percentage)
