"""Guards for the user-data integrity fixes.

Progress is the one thing in KeyQuest that cannot be regenerated, and the owner
and his users are blind: a file that quietly empties itself is invisible until
it is far too late. Each test here pins a specific way that used to happen.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import dashboard_manager, state_manager
from modules.single_instance import InstanceLock
from modules.state_manager import AppState, ProgressManager


class TestNewerFieldsSurviveAnOlderBuild(unittest.TestCase):
    """schema_version was written but never acted on.

    Running an older KeyQuest once, after a rollback say, silently stripped
    every field it did not recognise from the user's file on its next save.
    """

    def test_unknown_fields_are_written_back_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            Path(path).write_text(json.dumps({
                "schema_version": state_manager.PROGRESS_SCHEMA_VERSION + 5,
                "current_lesson": 3,
                "a_field_from_the_future": 42,
                "another": {"nested": True},
            }), encoding="utf-8")

            state = AppState()
            manager = ProgressManager(path)
            manager.load(state, stage_letters_count=50)
            manager.save(state)

            after = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(after["a_field_from_the_future"], 42)
            self.assertEqual(after["another"], {"nested": True})
            self.assertEqual(after["current_lesson"], 3, "our own fields still round-trip")

    def test_our_own_fields_are_not_shadowed_by_stale_unknowns(self) -> None:
        state = AppState()
        state.settings.unknown_progress_fields = {"current_lesson": 999}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            state.settings.current_lesson = 4
            ProgressManager(path).save(state)
            after = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(after["current_lesson"], 4, "a real field must win over a carried one")


class TestUnlockedLessonsAreValidated(unittest.TestCase):
    """A bad value used to break every future save, silently and permanently.

    Load did `set(unlocked)` with no checking, and save does `sorted()`. A file
    containing a string therefore loaded fine and then raised TypeError on every
    save for the rest of time, while the user kept playing.
    """

    def test_junk_entries_are_dropped_and_saving_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            Path(path).write_text(json.dumps({
                "schema_version": 1,
                "unlocked_lessons": [0, 1, "two", None, 3],
            }), encoding="utf-8")

            state = AppState()
            manager = ProgressManager(path)
            manager.load(state, stage_letters_count=50)

            self.assertEqual(sorted(state.settings.unlocked_lessons), [0, 1, 3])
            self.assertTrue(manager.save(state), "a cleaned set must save without raising")

    def test_out_of_range_lessons_are_dropped(self) -> None:
        # Rolling back to a build with fewer lessons would otherwise leave an
        # index that crashes the lesson menu.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            Path(path).write_text(json.dumps({
                "schema_version": 1, "unlocked_lessons": [0, 5, 9999],
            }), encoding="utf-8")
            state = AppState()
            ProgressManager(path).load(state, stage_letters_count=10)
            self.assertEqual(sorted(state.settings.unlocked_lessons), [0, 5])

    def test_an_empty_result_still_leaves_lesson_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            Path(path).write_text(json.dumps({
                "schema_version": 1, "unlocked_lessons": ["nonsense"],
            }), encoding="utf-8")
            state = AppState()
            ProgressManager(path).load(state, stage_letters_count=50)
            self.assertEqual(state.settings.unlocked_lessons, {0})


class TestStreakCountsEverySession(unittest.TestCase):
    """The streak only rolled over at launch.

    Someone who leaves KeyQuest open and practises daily never refreshed
    last_practice_date, so relaunching later looked like days of inactivity and
    reset a streak they had genuinely earned.
    """

    def test_recording_a_session_updates_the_practice_date(self) -> None:
        settings = state_manager.Settings()
        settings.last_practice_date = ""
        dashboard_manager.record_session(settings, {"wpm": 40})

        self.assertTrue(settings.last_practice_date, "the session should count towards the streak")
        self.assertGreaterEqual(settings.current_streak, 1)

    def test_a_streak_problem_never_stops_the_session_being_recorded(self) -> None:
        settings = state_manager.Settings()
        settings.last_practice_date = "not a date at all"
        dashboard_manager.record_session(settings, {"wpm": 40})
        self.assertEqual(len(settings.session_history), 1)


class TestSingleInstance(unittest.TestCase):
    def test_the_lock_is_reentrantly_safe_to_release(self) -> None:
        lock = InstanceLock()
        self.assertTrue(lock.acquire(wait_seconds=0.1))
        lock.release()
        lock.release()  # must not raise

    def test_a_second_lock_is_refused_while_the_first_is_held(self) -> None:
        if os.name != "nt":
            self.skipTest("named mutex is Windows-only")
        first = InstanceLock()
        self.assertTrue(first.acquire(wait_seconds=0.1))
        try:
            second = InstanceLock()
            self.assertFalse(
                second.acquire(wait_seconds=0.1),
                "two copies would overwrite each other's whole progress file",
            )
        finally:
            first.release()


if __name__ == "__main__":
    unittest.main()
