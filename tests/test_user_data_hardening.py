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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import dashboard_manager, single_instance, state_manager
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

    def test_unknown_fields_survive_more_than_one_launch(self) -> None:
        """The first save rewrites schema_version down to this build's number.

        A capture gated on the file looking newer therefore protected only the
        very first run after a rollback, and the second run stripped the fields
        anyway. One load-save cycle passes either way, so it has to be two.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            Path(path).write_text(json.dumps({
                "schema_version": state_manager.PROGRESS_SCHEMA_VERSION + 5,
                "a_field_from_the_future": 42,
            }), encoding="utf-8")

            for _ in range(3):
                state = AppState()
                manager = ProgressManager(path)
                manager.load(state, stage_letters_count=50)
                self.assertTrue(manager.save(state))

            after = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(after["a_field_from_the_future"], 42)

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
        # Force the failure. The previous version used a malformed date, which
        # check_and_update_streak handles internally without raising, so the
        # guard this test names was never exercised and it passed with the
        # try/except deleted.
        settings = state_manager.Settings()
        with mock.patch(
            "modules.streak_manager.check_and_update_streak",
            side_effect=RuntimeError("streak bookkeeping exploded"),
        ):
            dashboard_manager.record_session(settings, {"wpm": 40})

        self.assertEqual(
            len(settings.session_history), 1,
            "a streak problem must never cost the user their session record",
        )


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

    def test_separate_installations_do_not_block_each_other(self) -> None:
        """An installed copy and a portable copy save to different files.

        Sharing one lock name refused the second launch for no reason, and the
        user was told a copy was already open when none was.
        """
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            with mock.patch("modules.app_paths.get_app_dir", return_value=one):
                first_name = single_instance.mutex_name()
                again = single_instance.mutex_name()
            with mock.patch("modules.app_paths.get_app_dir", return_value=two):
                second_name = single_instance.mutex_name()

        self.assertEqual(first_name, again, "the same folder must give a stable name")
        self.assertNotEqual(first_name, second_name)
        self.assertTrue(first_name.startswith("Global\\"), "one install, two Windows users, one file")

    def test_the_name_ignores_path_casing(self) -> None:
        """Windows reaches one folder by many casings; all are the same install."""
        with mock.patch("modules.app_paths.get_app_dir", return_value=r"C:\KeyQuest"):
            lower = single_instance.mutex_name()
        with mock.patch("modules.app_paths.get_app_dir", return_value=r"c:\keyquest"):
            upper = single_instance.mutex_name()
        self.assertEqual(lower, upper)


class TestALockedProgressFileIsNeverOverwritten(unittest.TestCase):
    """The sequence that quietly destroyed a good file.

    Something holds progress.json at startup, so it cannot be read and cannot be
    renamed out of the way either. The app starts on default state, the lock
    clears, and the next routine save writes those defaults over a file that was
    perfectly intact. Nothing tells the user, and there is no copy left.
    """

    @staticmethod
    def _lock(path: str):
        """Rename behaviour of a file held open without delete sharing.

        A lock stops the original being renamed away AND being replaced. Keying
        this on the target alone let the quarantine rename succeed, which is not
        what a locked file does, and the test then measured the wrong path.
        """
        real_replace = Path.replace

        def replace(self_path, target):
            if path in (str(self_path), str(target)):
                raise PermissionError("locked")
            return real_replace(self_path, target)

        return replace

    def _locked_manager(self, tmp: str) -> tuple[ProgressManager, str]:
        path = os.path.join(tmp, "progress.json")
        Path(path).write_text(json.dumps({"current_lesson": 7, "coins": 500}), encoding="utf-8")
        manager = ProgressManager(path)
        state = AppState()
        # Reading and renaming both fail, exactly as a sharing violation does.
        with mock.patch("builtins.open", side_effect=PermissionError("locked")), \
                mock.patch.object(Path, "replace", self._lock(path)):
            self.assertFalse(manager.load(state, stage_letters_count=50))
        return manager, path

    def test_the_original_is_left_alone_while_it_stays_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, path = self._locked_manager(tmp)
            state = AppState()
            state.settings.coins = 0

            with mock.patch.object(Path, "replace", self._lock(path)):
                saved = manager.save(state)

            self.assertFalse(saved, "the user must be told this did not really work")
            self.assertEqual(
                json.loads(Path(path).read_text(encoding="utf-8"))["coins"], 500,
                "defaults were written over an intact progress file",
            )
            # Without this the test passes even with the protection removed,
            # because writing over a locked file fails of its own accord. It has
            # to show the save was ROUTED AWAY, not merely that it bounced.
            self.assertTrue(
                Path(path).with_suffix(".recovered.json").exists(),
                "the save should never have been aimed at the locked file",
            )

    def test_the_session_is_written_beside_the_locked_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, path = self._locked_manager(tmp)
            state = AppState()
            state.settings.coins = 3

            with mock.patch.object(Path, "replace", self._lock(path)):
                manager.save(state)

            beside = Path(path).with_suffix(".recovered.json")
            self.assertTrue(beside.exists(), "the session must not just be dropped")
            self.assertEqual(json.loads(beside.read_text(encoding="utf-8"))["coins"], 3)

    def test_saving_returns_to_normal_once_the_lock_clears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, path = self._locked_manager(tmp)
            state = AppState()
            state.settings.coins = 3

            # No patch this time: the lock is gone, so the rename now works.
            self.assertTrue(manager.save(state), "saving must heal, not stay degraded")
            self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["coins"], 3)
            preserved = list(Path(tmp).glob("progress.json.unreadable-*"))
            self.assertEqual(len(preserved), 1, "the original is kept, not deleted")
            self.assertEqual(json.loads(preserved[0].read_text(encoding="utf-8"))["coins"], 500)


class TestPersistedKeysMatchTheSavePayload(unittest.TestCase):
    """The key list decides what counts as an "unknown" field.

    If a key is left in the tuple after leaving the payload, every newer file's
    copy of it is treated as ours and silently dropped. Nothing pinned the two
    together, so this compares them directly.
    """

    def test_every_saved_key_is_listed_and_vice_versa(self) -> None:
        state = AppState()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "progress.json")
            ProgressManager(path).save(state)
            written = set(json.loads(Path(path).read_text(encoding="utf-8")))

        self.assertEqual(
            written, set(state_manager._PERSISTED_KEYS),
            "_PERSISTED_KEYS has drifted from what save() actually writes",
        )



if __name__ == "__main__":
    unittest.main()
