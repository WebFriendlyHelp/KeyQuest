"""Letter Fall's game-over reward line is heard, not cut off by the menu.

Codex release review 2026-11-11, finding 2. After the results dialog, the app
queues the coins, pet status and any streak milestone behind the game's lines
(priority, interrupt=False). Letter Fall then called say_game_menu() with the
default interrupt=True, which cancelled that reward line in the same call, so
the coins were paid but never announced. Word Typing already queues its menu.

Uses tests/speech_burst.py (the real Speech.say drop logic, muted). It models
cancellation, not what NVDA voices.
"""

import unittest
from unittest import mock

from games.letter_fall import FallingLetter, LetterFallGame
from modules import keyquest_app
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _game_on_last_life(speech, pet_result):
    game = LetterFallGame(
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
    game.lives = 1
    game.score = 400
    game.max_combo = 5
    game.game_start_time = 0.0
    patches = (
        mock.patch.object(keyquest_app.pet_manager, "apply_session_pet_progress", return_value=pet_result),
        mock.patch.object(keyquest_app.pet_manager, "get_pet_status", return_value={"pet_name": "Rex"}),
    )
    return game, patches


class TestLetterFallRewardLine(unittest.TestCase):
    def _game_over(self, pet_result):
        speech = make_speech()
        game, patches = _game_on_last_life(speech, pet_result)
        missed = FallingLetter("h", 100, 500, is_active=True)
        game.letters = [missed]
        with patches[0], patches[1]:
            game._handle_target_missed(missed)
        return speech, game

    def test_pet_status_reward_line_is_heard_after_game_over(self):
        speech, game = self._game_over({"has_pet": True, "summary": "Rex is happy."})
        self.assertEqual(game.mode, "MENU")
        text = heard_text(speech)
        self.assertIn("Pet status", text, lines_reaching_backend(speech))
        self.assertIn("Letter Fall menu", text, "the menu is still announced after it")

    def test_menu_still_announced_with_no_reward_line(self):
        """Twin: no pet, the menu line is still heard."""
        speech, _game = self._game_over({"has_pet": False})
        self.assertIn("Letter Fall menu", heard_text(speech), lines_reaching_backend(speech))


if __name__ == "__main__":
    unittest.main()
