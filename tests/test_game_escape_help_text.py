"""Game help text describes the Escape behaviour the app really has.

Fable review 2026-11-10, ui findings 3 and 12. While a game is being played,
the app's triple-Escape guard consumes every Escape, so one press says "Press 2
more times to exit" and the third goes straight to the main menu. Letter Fall
said one Escape pauses and returns to the game menu, Word Typing said it ends
the session and shows results. Hangman's footer named Tab (unhandled) and
called Ctrl+Space a guessed count (it reads word progress).

These check the text only. The Escape behaviour itself is pinned by
tests/test_escape_policy.py.
"""

import inspect
import unittest

from games import hangman, letter_fall, word_typing
from modules.keyquest_app import KeyQuestApp


class TestGameEscapeHelp(unittest.TestCase):
    def _assert_says_three_presses(self, game_cls):
        for text in (game_cls.HOTKEYS, game_cls.INSTRUCTIONS):
            lowered = text.lower()
            self.assertNotIn("escape during play to pause", lowered)
            self.assertNotIn("escape during play to end", lowered)
            self.assertNotIn("escape: pause", lowered)
            self.assertNotIn("escape: end session", lowered)
            self.assertTrue("three times" in lowered or "x3" in lowered, text)

    def test_letter_fall(self):
        self._assert_says_three_presses(letter_fall.LetterFallGame)

    def test_word_typing(self):
        self._assert_says_three_presses(word_typing.WordTypingGame)

    def test_the_guard_really_needs_three_presses_in_play(self):
        """Pins the behaviour the text now describes."""
        source = inspect.getsource(KeyQuestApp._escape_policy)
        self.assertIn('game_mode not in ("MENU", "RESULTS")', source)

    def test_hangman_footer_names_real_keys(self):
        source = inspect.getsource(hangman)
        self.assertNotIn("Tab word progress", source)
        self.assertNotIn("Ctrl+Space guessed count", source)


if __name__ == "__main__":
    unittest.main()
