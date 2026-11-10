"""A pet mood or evolution line queues behind the session's own lines.

Pre-merge review finding 4. apply_pet_session_progress spoke "pet evolved" and
"pet is feeling X" with the default interrupt=True, so when a session changed
the pet's mood that line cancelled the Hangman round headline ("YOU WIN ...")
or "Words completed: N. Exiting to main menu."

Uses tests/speech_burst.py (the real Speech.say drop logic, muted). It models
cancellation, not what NVDA voices.
"""

import unittest
from unittest import mock

from games.hangman import HangmanGame
from modules import keyquest_app
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _hangman_with_pet(speech, pet_result):
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
    app.apply_pet_session_progress = (
        lambda **kw: KeyQuestApp.apply_pet_session_progress(app, **kw)
    )
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
    patches = (
        mock.patch.object(keyquest_app.pet_manager, "apply_session_pet_progress", return_value=pet_result),
        mock.patch.object(keyquest_app.pet_manager, "get_pet_status", return_value={"pet_name": "Rex"}),
    )
    return game, patches


class TestPetLineQueues(unittest.TestCase):
    def _win(self, pet_result):
        speech = make_speech()
        game, patches = _hangman_with_pet(speech, pet_result)
        with patches[0], patches[1]:
            game.process_guess("e")
        return speech

    def test_mood_change_does_not_cut_the_win_headline(self):
        speech = self._win({"has_pet": True, "mood_changed": True, "mood": "happy",
                            "mood_message": "Rex wags.", "summary": "Happy."})
        text = heard_text(speech)
        self.assertIn("YOU WIN", text, lines_reaching_backend(speech))
        self.assertIn("Rex is feeling happy", text)

    def test_evolution_does_not_cut_the_win_headline(self):
        speech = self._win({"has_pet": True, "evolved": True, "new_stage": 2,
                            "stage_name": "teen", "summary": "Grown."})
        text = heard_text(speech)
        self.assertIn("YOU WIN", text, lines_reaching_backend(speech))
        self.assertIn("Rex evolved", text)

    def test_no_pet_change_still_heard(self):
        # Twin: the plain path is unchanged.
        speech = self._win({"has_pet": False})
        self.assertIn("YOU WIN", heard_text(speech))


if __name__ == "__main__":
    unittest.main()
