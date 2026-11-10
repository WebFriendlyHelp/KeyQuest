"""What the triple-Escape exit does inside a game (Casey's decision, 2026-11-10).

Fable review ui finding 3. While a game is being played the app's guard eats
every Escape, so the games' own Escape code never ran:

1. Word Typing dropped straight to the main menu on the third press and the
   session (coins, pet XP, practice log entry) was never recorded.
2. Letter Fall kept dropping letters during the first two presses, so a
   learner who pressed Escape once to stop lost lives while hearing
   "Press 2 more times to exit".

These drive the real KeyQuestApp._handle_escape_shortcut and the frame
update step with stub speech. They prove the call order and the recorded
stats, not what a screen reader voices.
"""

import unittest
from unittest import mock

from games.hangman import HangmanGame
from games.letter_fall import LetterFallGame
from games.word_typing import WordTypingGame
from modules.escape_guard import EscapePressGuard
from modules.keyquest_app import KeyQuestApp


class _Speech:
    def __init__(self):
        self.spoken = []

    def say(self, text, **kwargs):
        self.spoken.append((text, kwargs))


class _State:
    mode = "GAME"


def _make_game(cls, speech):
    return cls(
        screen=None,
        fonts={"title_font": None, "text_font": None, "small_font": None},
        speech=speech,
        play_sound_func=lambda *_a, **_k: None,
        show_info_dialog_func=lambda *_a, **_k: None,
    )


def _make_app(game, speech):
    app = object.__new__(KeyQuestApp)
    app.state = _State()
    app.current_game = game
    app.escape_guard = EscapePressGuard()
    app._escape_remaining = 0
    app._escape_noun = ""
    app.speech = speech
    app.say_menu = lambda *a, **k: speech.say("Main menu.", **k)
    return app


class TestWordTypingTripleEscape(unittest.TestCase):
    def test_third_escape_records_the_session(self):
        speech = _Speech()
        game = _make_game(WordTypingGame, speech)
        recorded = []
        game.on_session_complete = lambda g, stats: recorded.append(stats)
        game.mode = "PLAYING"
        game.running = True
        game.game_start_time = 0.0
        game.words_completed = 6
        game.correct_chars = 40
        game.total_chars_typed = 50
        app = _make_app(game, speech)

        with mock.patch("games.word_typing.time.time", return_value=15.0):
            for _ in range(3):
                self.assertTrue(KeyQuestApp._handle_escape_shortcut(app))

        self.assertEqual(len(recorded), 1, "the session must be recorded exactly once")
        stats = recorded[0]
        self.assertEqual(stats["words_completed"], 6)
        self.assertEqual(stats["accuracy"], 80.0)
        self.assertAlmostEqual(stats["session_duration_minutes"], 0.25)
        self.assertTrue(stats["ended_early"])
        self.assertIsNone(app.current_game)
        self.assertEqual(app.state.mode, "MENU")
        self.assertFalse(game.running)

    def test_two_escapes_record_nothing(self):
        # Negative twin: the session is only recorded when the exit completes.
        speech = _Speech()
        game = _make_game(WordTypingGame, speech)
        recorded = []
        game.on_session_complete = lambda g, stats: recorded.append(stats)
        game.mode = "PLAYING"
        game.running = True
        app = _make_app(game, speech)

        for _ in range(2):
            KeyQuestApp._handle_escape_shortcut(app)

        self.assertEqual(recorded, [])
        self.assertIs(app.current_game, game)


class TestLetterFallPausesOnEscape(unittest.TestCase):
    def _playing_letter_fall(self, speech):
        game = _make_game(LetterFallGame, speech)
        game.mode = "PLAYING"
        game.running = True
        return game

    def test_first_escape_pauses_the_falling_letters(self):
        speech = _Speech()
        game = self._playing_letter_fall(speech)
        app = _make_app(game, speech)

        KeyQuestApp._handle_escape_shortcut(app)
        with mock.patch.object(game, "update") as update:
            KeyQuestApp._update_current_game(app, 0.1)
        update.assert_not_called()
        self.assertIn("paused", speech.spoken[-1][0].lower())

    def test_another_key_resumes(self):
        speech = _Speech()
        game = self._playing_letter_fall(speech)
        app = _make_app(game, speech)

        KeyQuestApp._handle_escape_shortcut(app)
        # Any key other than Escape resets the guard in handle_event.
        app.escape_guard.reset()
        app._escape_remaining = 0
        with mock.patch.object(game, "update") as update:
            KeyQuestApp._update_current_game(app, 0.1)
        update.assert_called_once_with(0.1)

    def test_third_escape_records_the_session_with_the_score(self):
        speech = _Speech()
        game = self._playing_letter_fall(speech)
        game.score = 120
        recorded = []
        game.on_session_complete = lambda g, stats: recorded.append(stats)
        app = _make_app(game, speech)

        for _ in range(3):
            KeyQuestApp._handle_escape_shortcut(app)

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["score"], 120)
        self.assertTrue(recorded[0]["ended_early"])
        spoken = " ".join(text for text, _ in speech.spoken)
        self.assertIn("120", spoken)
        self.assertIn("Exiting to main menu", spoken)

    def test_hangman_keeps_running_after_one_escape(self):
        # Negative twin: only a game that asks to pause is paused.
        speech = _Speech()
        game = _make_game(HangmanGame, speech)
        game.mode = "PLAYING"
        app = _make_app(game, speech)

        KeyQuestApp._handle_escape_shortcut(app)
        with mock.patch.object(game, "update") as update:
            KeyQuestApp._update_current_game(app, 0.1)
        update.assert_called_once_with(0.1)


class TestEscapeHelpMatches(unittest.TestCase):
    def test_letter_fall_help_says_one_escape_pauses(self):
        for text in (LetterFallGame.HOTKEYS, LetterFallGame.INSTRUCTIONS):
            self.assertIn("pause", text.lower(), text)

    def test_word_typing_help_says_the_session_is_recorded(self):
        self.assertIn("still count", WordTypingGame.INSTRUCTIONS.lower())


if __name__ == "__main__":
    unittest.main()
