"""End-to-end lesson playthrough: type exactly what KeyQuest says to type.

Why this exists. A tester reported that lesson 0 announced "type a a" for a
target that actually needed A, space, A. Every unit test passed, because they
checked the formatter and the lesson generator separately and neither is wrong
on its own. What was wrong was the agreement between them, and only playing the
lesson can see that.

So this boots the real KeyQuestApp headless, plays each lesson as a perfect
typist, and asserts one thing: a learner who types precisely what the program
announced is never told they are wrong. That single property catches any drift
between a prompt and the keystrokes it stands for.

It also catches a subtler failure. The decoder below turns a spoken prompt back
into keystrokes, so it knows both readings of a word like "dash": the letters
d-a-s-h, and this app's spoken name for the hyphen key. A prompt that decodes
two ways is genuinely ambiguous to a listener, and gets reported. That is how
lesson 8's "gag dash" was found.

Not a pytest module. It boots a real app with a real display surface (SDL's
dummy driver) and takes about ninety seconds, so it runs like the updater
harness does: on demand, and in CI when lesson or speech code changes.

    py -3.11 tests/run_lesson_playthrough.py
    py -3.11 tests/run_lesson_playthrough.py --lessons 0-8 --attempts 5
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# SDL needs these before pygame is imported anywhere, including transitively.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from modules import lesson_manager, speech_format  # noqa: E402

# Spoken key name back to the character it stands for.
NAME_TO_CHAR = {name: ch for ch, name in speech_format.SPECIAL_CHAR_NAMES.items()}


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str = "") -> None:
        self.lines.append(str(message))
        print(message, flush=True)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


class RecordingSpeech:
    """Stands in for Speech and captures everything the app would say.

    Deliberately not a mock of the audio: what matters is the text handed to
    the speech layer, which is what a screen reader or SAPI would voice.
    """

    def __init__(self) -> None:
        self.said: list[str] = []
        self.enabled = True
        self.backend = "tts"
        self._screen_reader_detected = None

    def say(self, text, priority=False, protect_seconds=0.0, interrupt=True):
        if text:
            self.said.append(str(text))

    def apply_mode(self, *_args, **_kwargs):
        pass

    def refresh_backend(self, *_args, **_kwargs):
        return False

    def apply_tts_settings(self, *_args, **_kwargs):
        pass

    def get_available_voices(self):
        return []

    def shutdown(self):
        pass

    def last(self) -> str:
        return self.said[-1] if self.said else ""


def decode_prompt(spoken: str) -> list[str]:
    """Turn a spoken prompt back into the keystrokes it asks for."""
    text = spoken.strip()

    # The first announcement of a lesson prefixes the prompt with the mode
    # intro ("Lesson practice. Control Space repeats. ... Type h, g, e"), so
    # take what follows the LAST "Type ", not the first.
    marker = "Type "
    position = text.rfind(marker)
    if position == -1:
        position = text.rfind("type ")
    if position != -1:
        text = text[position + len(marker):]
    text = text.rstrip(".")

    parts = text.split(" ")
    if len(parts) == 2 and parts[1] == "twice":
        return decode_token(parts[0]) * 2
    if len(parts) == 3 and parts[2] == "times" and parts[1].isdigit():
        return decode_token(parts[0]) * int(parts[1])

    keys: list[str] = []
    for token in text.split(", "):
        keys.extend(decode_token(token))
    return keys


def decode_token(token: str) -> list[str]:
    token = token.strip()
    if not token:
        return []
    if token in NAME_TO_CHAR:
        return [NAME_TO_CHAR[token]]
    if len(token) == 1:
        return [token]
    if token.startswith("capital ") and len(token) == len("capital x"):
        return [token[-1].upper()]
    return list(token)  # a naturally spoken word: type its letters


def key_event(ch: str) -> pygame.event.Event:
    """A real pygame KEYDOWN for a printable character."""
    if ch == " ":
        key = pygame.K_SPACE
    else:
        key = getattr(pygame, "K_" + ch, None)
        if key is None:
            key = ord(ch) if ord(ch) < 128 else 0
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=ch, mod=0)


def special_key_event(name: str) -> pygame.event.Event | None:
    """A KEYDOWN for a named non-printable key, e.g. "tab" or "pageup"."""
    for key_code, key_name in lesson_manager.SPECIAL_KEY_NAMES.items():
        if key_name == name:
            return pygame.event.Event(pygame.KEYDOWN, key=key_code, unicode="", mod=0)
    return None


def build_app():
    from modules import keyquest_app

    app = keyquest_app.KeyQuestApp()
    app.speech = RecordingSpeech()

    # Never touch the player's real save file, and never open a wx dialog.
    handle, temp_progress = tempfile.mkstemp(suffix="-playthrough-progress.json")
    os.close(handle)
    app.progress_manager.filename = temp_progress
    app.save_progress = lambda *a, **k: True
    app.show_guided_results_dialog = lambda *a, **k: None
    app.show_badge_notifications = lambda *a, **k: None
    app.show_level_up_notification = lambda *a, **k: None
    app.show_quest_notifications = lambda *a, **k: None
    app.apply_pet_session_progress = lambda *a, **k: {"has_pet": False}
    return app, temp_progress


def clear_intro_screen(app, lesson_num: int, problems: list[str]) -> bool:
    """Lessons with key-location intros only start once the new keys are pressed.

    Without this the playthrough silently skips lessons 0 to 10, which are the
    ones the original bug was reported in. A harness that quietly tests nothing
    is worse than no harness, so a failure to advance is reported.
    """
    if app.state.mode != "LESSON_INTRO":
        return True

    for key in sorted(app.state.lesson_intro.required_keys):
        app.handle_event(key_event(key))

    if app.state.mode != "LESSON":
        problems.append(
            f"lesson {lesson_num}: could not get past the intro screen; "
            f"still in mode {app.state.mode!r}"
        )
        return False
    return True


def play_special_key_lesson(app, lesson_num: int, problems: list[str]) -> int:
    """Drill lessons whose targets are named keys rather than characters."""
    lesson = app.state.lesson
    done = 0
    for _ in range(len(lesson.batch_words)):
        if app.state.mode != "LESSON" or lesson.index >= len(lesson.batch_words):
            break
        target = lesson.batch_words[lesson.index]
        event = special_key_event(target)
        if event is None:
            problems.append(
                f"lesson {lesson_num}: no key event maps to the target {target!r}"
            )
            break
        before = lesson.index
        app.handle_event(event)
        if lesson.index == before:
            problems.append(
                f"lesson {lesson_num}: pressing {target!r} did not advance the drill"
            )
            break
        done += 1
    return done


def play_lesson(app, lesson_num: int, max_items: int = 40) -> tuple[int, list[str]]:
    """Play one lesson as a perfect typist."""
    problems: list[str] = []
    app.speech.said.clear()
    app.start_lesson(lesson_num)

    if not clear_intro_screen(app, lesson_num, problems):
        return 0, problems

    lesson = app.state.lesson
    if lesson.batch_instructions:
        return play_special_key_lesson(app, lesson_num, problems), problems

    done = 0
    guard = 0
    while done < max_items and guard < max_items * 12:
        guard += 1
        if app.state.mode != "LESSON" or lesson.index >= len(lesson.batch_words):
            break

        target = lesson.batch_words[lesson.index]
        typed_before = lesson.typed
        remaining = target[len(typed_before):]

        spoken = app.speech.last()
        asked = decode_prompt(spoken)

        if "".join(asked) != remaining:
            problems.append(
                f"lesson {lesson_num} item {target!r} (typed {typed_before!r}): "
                f"announced {spoken!r} decodes to {''.join(asked)!r}, but the "
                f"required keys are {remaining!r}"
            )
            asked = list(remaining)  # recover so the run continues

        errors_before = lesson.tracker.total_attempts - lesson.tracker.total_correct
        start_index = lesson.index

        for ch in asked:
            app.handle_event(key_event(ch))
            if app.state.mode != "LESSON":
                break

        errors_after = lesson.tracker.total_attempts - lesson.tracker.total_correct
        if errors_after > errors_before:
            problems.append(
                f"lesson {lesson_num} item {target!r}: typing exactly what was "
                f"announced produced {errors_after - errors_before} error(s)"
            )

        if app.state.mode != "LESSON":
            break
        if lesson.index == start_index and lesson.typed == typed_before:
            problems.append(
                f"lesson {lesson_num} item {target!r}: stuck, no progress after "
                f"typing {''.join(asked)!r}"
            )
            break
        if lesson.index != start_index:
            done += 1

    return done, problems


def parse_lessons(spec: str) -> list[int]:
    total = len(lesson_manager.STAGE_LETTERS)
    if not spec or spec == "all":
        return list(range(total))
    if "-" in spec:
        first, last = spec.split("-", 1)
        return [n for n in range(int(first), int(last) + 1) if 0 <= n < total]
    return [int(n) for n in spec.split(",") if 0 <= int(n) < total]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lessons", default="all", help='"all", "0-8", or "0,3,7"')
    parser.add_argument("--attempts", type=int, default=3,
                        help="batches are random; how many to sample per lesson")
    parser.add_argument("--report", default=str(ROOT / "tests" / "logs" /
                                                "lesson_playthrough.txt"))
    args = parser.parse_args()

    report = Report()
    report.log("Booting KeyQuestApp headless (SDL dummy video and audio).")
    app, temp_progress = build_app()
    report.log(f"Booted. Mode {app.state.mode}.")
    report.log("")

    total_items = 0
    all_problems: list[str] = []

    for lesson_num in parse_lessons(args.lessons):
        app.state.settings.unlocked_lessons.add(lesson_num)
        items = 0
        found: list[str] = []
        for _ in range(args.attempts):
            done, problems = play_lesson(app, lesson_num)
            items += done
            found.extend(problems)
        total_items += items
        all_problems.extend(found)
        name = lesson_manager.LESSON_NAMES[lesson_num][:36]
        report.log(f"lesson {lesson_num:2d} ({name:<36}) items {items:3d}  "
                   f"problems {len(found)}")

    report.log("")
    report.log("=" * 70)
    report.log(f"Items typed exactly as announced: {total_items}")
    report.log(f"Prompts that disagreed with the required keys: {len(all_problems)}")
    for problem in all_problems[:40]:
        report.log("  " + problem)
    if len(all_problems) > 40:
        report.log(f"  ... and {len(all_problems) - 40} more")
    report.log("=" * 70)

    app.speech.shutdown()
    try:
        os.unlink(temp_progress)
    except OSError:
        pass

    report.write(Path(args.report))
    report.log(f"Report written to {args.report}")
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main())
