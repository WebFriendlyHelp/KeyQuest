"""The end of a Hangman round is heard, not cancelled by the next line.

Fable review 2026-11-10, ui finding 4 (and 11.1, 11.3). Every line at the end
of a round used the default interrupt=True, so each cancelled the one before:
"Word solved", "YOU WIN", the definition and the coin reward were all cut by
the first results-menu item. On a loss "No guesses left" and "GAME OVER" went
the same way, so win and loss were told apart only by the sound.

Uses tests/speech_burst.py (the real Speech.say drop logic, muted) and the
real KeyQuestApp.handle_game_session_complete for the reward line. What it
would still pass on: the model treats a line as heard unless an interrupting
line follows it in the same action. It cannot tell what NVDA voices.
"""

import unittest
from unittest import mock

from games.hangman import HangmanGame
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings
from tests.speech_burst import heard_text, make_speech, lines_reaching_backend


def _game(speech):
    game = HangmanGame(
        screen=None,
        fonts={"title_font": None, "text_font": None, "small_font": None},
        speech=speech,
        play_sound_func=lambda *_a, **_k: None,
        show_info_dialog_func=lambda *_a, **_k: None,
    )
    app = mock.MagicMock()
    app.state.settings = Settings()
    app.speech = speech
    app.apply_pet_session_progress.return_value = {}
    game.on_session_complete = lambda g, stats: KeyQuestApp.handle_game_session_complete(app, g, stats)
    game.mode = "PLAYING"
    game.running = True
    game.word = "abcde"
    game.word_definition = "a test word"
    game.guessed_letters = set("abcd")
    game.max_wrong = 10
    game.remaining_guesses = 10
    game.wrong_guesses = 0
    game.correct_guesses = 4
    game.guess_attempts = 4
    game.repeated_guesses = 0
    game.game_start_time = 0.0
    return game


class TestRoundEndIsHeard(unittest.TestCase):
    def test_a_win_is_heard_whole(self):
        speech = make_speech()
        game = _game(speech)
        game.process_guess("e")
        text = heard_text(speech)
        self.assertIn("YOU WIN", text, lines_reaching_backend(speech))
        self.assertIn("a test word", text)
        self.assertIn("coin", text.lower(), "the reward line must survive")
        self.assertIn("Word: ABCDE", text, "the results menu is still announced")

    def test_a_loss_is_heard_whole(self):
        speech = make_speech()
        game = _game(speech)
        game.guessed_letters = set("ab")
        game.remaining_guesses = 1
        game.wrong_guesses = 9
        game.process_guess("z")
        text = heard_text(speech)
        self.assertIn("No guesses left", text, lines_reaching_backend(speech))
        self.assertIn("GAME OVER", text)
        self.assertIn("abcde", text.lower())

    def test_an_ordinary_correct_letter_still_speaks_progress(self):
        """Negative twin: mid-round feedback keeps working."""
        speech = make_speech()
        game = _game(speech)
        game.guessed_letters = set("ab")
        game.process_guess("c")
        self.assertTrue(lines_reaching_backend(speech))
        self.assertNotIn("YOU WIN", heard_text(speech))

    def test_hangman_start_is_heard(self):
        """ui finding 11.1: "Guess a letter" was cut by the letter count."""
        speech = make_speech()
        game = _game(speech)
        with mock.patch("games.hangman.pygame.time.wait"), \
                mock.patch.object(game, "_choose_word", return_value=("abcde", "a test word")), \
                mock.patch.object(game, "play_sound"):
            game.start_playing()
        text = heard_text(speech)
        self.assertIn("Guess a letter", text, lines_reaching_backend(speech))
        self.assertIn("5 letters", text)


if __name__ == "__main__":
    unittest.main()
