"""Nothing in the app may start tkinter (Fable review 2026-11-10, high findings).

CLAUDE.md records the frozen build crashing 5 times out of 5 on a tkinter root
window built to copy text, inside a process already running SDL and wx. Only
``error_logging.copy_text_to_clipboard`` was converted; Hangman's "Copy Word +
Definition" and the Practice Log's "Copy Log" still built their own Tk root.
The old guard test scanned error_logging alone, so neither copy was caught.

These tests prove the SOURCE no longer reaches tkinter and that both copy
actions go through the shared Win32 helper. They do not prove the frozen build
stops crashing; that needs the installed exe.
"""

import os
import re
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_SOURCE_DIRS = ("modules", "games", "ui")
TK_IMPORT = re.compile(r"^\s*(import\s+tkinter|from\s+tkinter\b)", re.MULTILINE)


def _app_source_files():
    yield os.path.join(ROOT, "keyquest.pyw")
    for folder in APP_SOURCE_DIRS:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


class TestNoTkinterAnywhereInTheApp(unittest.TestCase):
    def test_the_scan_sees_the_app(self):
        """Pin the scan's own reach, so an empty walk cannot pass."""
        files = list(_app_source_files())
        names = {os.path.relpath(p, ROOT).replace(os.sep, "/") for p in files}
        self.assertIn("games/hangman.py", names)
        self.assertIn("modules/progress_views.py", names)
        self.assertGreater(len(files), 40)

    def test_no_app_source_imports_tkinter(self):
        offenders = []
        for path in _app_source_files():
            with open(path, "r", encoding="utf-8") as handle:
                if TK_IMPORT.search(handle.read()):
                    offenders.append(os.path.relpath(path, ROOT))
        self.assertEqual(offenders, [], "never start a second GUI toolkit")

    def test_the_pattern_catches_an_indented_import(self):
        """Negative twin: the regex must match the shape the old code used."""
        self.assertTrue(TK_IMPORT.search("    try:\n        import tkinter as tk\n"))

    def test_the_build_excludes_tkinter(self):
        """A future import should fail at build time instead of shipping Tk."""
        spec = os.path.join(ROOT, "tools", "build", "KeyQuest-RootFolders.spec")
        with open(spec, "r", encoding="utf-8") as handle:
            text = handle.read()
        match = re.search(r"excludes\s*=\s*\[([^\]]*)\]", text)
        self.assertIsNotNone(match)
        self.assertIn("tkinter", match.group(1))


class TestCopyActionsUseTheSharedHelper(unittest.TestCase):
    def test_hangman_copy_goes_through_error_logging(self):
        from games import hangman

        game = hangman.HangmanGame.__new__(hangman.HangmanGame)
        game.word = "keyboard"
        game.word_definition = "a set of keys"
        game.speech = mock.Mock()
        with mock.patch("modules.error_logging.copy_text_to_clipboard", return_value=True) as copy:
            game.copy_word_and_definition()
        copy.assert_called_once_with("Word: KEYBOARD\nDefinition: a set of keys")
        game.speech.say.assert_called_once()
        self.assertIn("Copied", game.speech.say.call_args[0][0])

    def test_hangman_copy_failure_is_spoken(self):
        from games import hangman

        game = hangman.HangmanGame.__new__(hangman.HangmanGame)
        game.word = "keyboard"
        game.word_definition = "a set of keys"
        game.speech = mock.Mock()
        with mock.patch("modules.error_logging.copy_text_to_clipboard", return_value=False):
            game.copy_word_and_definition()
        self.assertIn("Unable", game.speech.say.call_args[0][0])

    def test_practice_log_copy_goes_through_error_logging(self):
        from modules import progress_views

        app = mock.Mock()
        with mock.patch.object(progress_views.dashboard_manager, "format_practice_log", return_value="LOG"), \
                mock.patch.object(progress_views.dialog_manager, "show_yes_no_dialog", return_value=True), \
                mock.patch("modules.error_logging.copy_text_to_clipboard", return_value=True) as copy:
            progress_views.show_practice_log(app)
        copy.assert_called_once_with("LOG")


if __name__ == "__main__":
    unittest.main()
