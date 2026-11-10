"""Letter Fall tells a blind player their lives and score.

Fable review 2026-11-10, ui finding 5. "Missed H! 2 lives left." was cancelled
in the same call by "Target B, like bravo", and nothing bound to a key spoke
the lives or score, so a player could not learn they were on their last life.

Uses tests/speech_burst.py; it models cancellation, not what NVDA voices.
"""

import unittest
from unittest import mock

import pygame

from games.letter_fall import FallingLetter, LetterFallGame
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _game(speech):
    game = LetterFallGame(
        screen=None,
        fonts={"title_font": None, "text_font": None, "small_font": None},
        speech=speech,
        play_sound_func=lambda *_a, **_k: None,
        show_info_dialog_func=lambda *_a, **_k: None,
    )
    game.mode = "PLAYING"
    game.running = True
    game.lives = 3
    game.score = 40
    return game


class TestLettersFallLives(unittest.TestCase):
    def test_a_miss_with_a_queued_letter_says_the_lives(self):
        speech = make_speech()
        game = _game(speech)
        missed = FallingLetter("h", 100, 500, is_active=True)
        game.letters = [missed, FallingLetter("b", 150, 180)]
        with mock.patch("games.letter_fall.time.time", return_value=30.0):
            game._handle_target_missed(missed)
        text = heard_text(speech)
        self.assertIn("2 lives left", text, lines_reaching_backend(speech))
        self.assertIn("bravo", text, "the next target is still announced")

    def test_a_miss_with_nothing_queued_still_says_the_lives(self):
        """Negative twin: no next target, the miss line alone."""
        speech = make_speech()
        game = _game(speech)
        missed = FallingLetter("h", 100, 500, is_active=True)
        game.letters = [missed]
        game._handle_target_missed(missed)
        self.assertIn("2 lives left", heard_text(speech))

    def test_tab_reports_lives_and_score(self):
        speech = make_speech()
        game = _game(speech)
        game.letters = [FallingLetter("a", 100, 120, is_active=True)]
        event = mock.Mock(key=pygame.K_TAB, unicode="\t")
        game.handle_game_input(event, 0)
        text = heard_text(speech)
        self.assertIn("Lives: 3", text, lines_reaching_backend(speech))
        self.assertIn("Score: 40", text)


if __name__ == "__main__":
    unittest.main()
