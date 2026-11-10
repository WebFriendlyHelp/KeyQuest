""""Left unchanged" is said once per update, not on every launch.

Fable review 2026-11-10, modules finding 3. The merge runs on every startup
with the shipped defaults as its source when no update was staged, so a user
with one edited file heard "Sentence content checked. 1 of your own sentence
files was left unchanged." and got a log entry at every launch, against the
docstring's "only once per update".

Uses the real merge against a scratch app folder. What it still passes on:
what is queued for speech, not what the screen reader says.
"""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from modules import sentence_merge, update_controller
from modules.update_controller import AppUpdateController


class _Speech:
    def __init__(self):
        self.calls = []

    def say(self, text, **kwargs):
        self.calls.append(text)


class _App:
    def __init__(self):
        self.state = SimpleNamespace(mode="MENU")
        self.speech = _Speech()
        self.events = []

    def _record_update_event(self, message):
        self.events.append(message)


def _scratch_install(tmpdir, staged):
    root = Path(tmpdir)
    (root / "Sentences").mkdir()
    (root / "Sentences" / "English.txt").write_text("My own edited sentence.\n", encoding="utf-8")
    source = root / (sentence_merge.INCOMING_DIR_NAME if staged else os.path.join(*sentence_merge.DEFAULTS_DIR_PARTS))
    source.mkdir(parents=True)
    (source / "English.txt").write_text("Shipped sentence.\n", encoding="utf-8")
    return root


class TestLeftUnchangedIsSaidOncePerUpdate(unittest.TestCase):
    def _run(self, staged):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _scratch_install(tmpdir, staged)
            app = _App()
            controller = AppUpdateController.__new__(AppUpdateController)
            controller.app = app
            with mock.patch.object(update_controller, "get_app_dir", return_value=str(root)):
                controller._merge_shipped_sentences()
            kept = (root / "Sentences" / "English.txt").read_text(encoding="utf-8")
        self.assertEqual(kept, "My own edited sentence.\n", "the user's file is never touched")
        return app

    def test_an_ordinary_launch_says_nothing(self):
        app = self._run(staged=False)
        self.assertEqual(app.speech.calls, [])
        self.assertEqual(app.events, [])

    def test_a_staged_update_still_says_it(self):
        """Negative twin: the real update case must keep its announcement."""
        app = self._run(staged=True)
        self.assertTrue(any("left unchanged" in c for c in app.speech.calls), app.speech.calls)


if __name__ == "__main__":
    unittest.main()
