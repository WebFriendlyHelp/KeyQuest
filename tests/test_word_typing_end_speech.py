"""Word Typing's closing summary and reward are not cancelled by the menu line.

Fable review 2026-11-10, ui finding 11.2. After the results dialog closed,
"Game over! Corrected words per minute..." and the coin reward were each cut
by the next interrupting line, ending with the game menu announcement.

Uses tests/speech_burst.py and the real KeyQuestApp reward line; it models
cancellation, not what NVDA voices.
"""

import unittest
from unittest import mock

from games import base_game
from games.word_typing import WordTypingGame
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


class TestWordTypingEnd(unittest.TestCase):
    def test_summary_reward_and_menu_are_all_heard(self):
        speech = make_speech()
        game = WordTypingGame(
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
        game.game_start_time = 0.0
        game.correct_chars = 50
        game.total_chars_typed = 50
        with mock.patch.object(base_game.dialog_manager, "show_results_dialog"), \
                mock.patch("games.word_typing.time.time", return_value=30.0), \
                mock.patch.object(game, "play_sound", create=True):
            game.end_game()
        text = heard_text(speech)
        self.assertIn("Game over", text, lines_reaching_backend(speech))
        self.assertIn("coin", text.lower())
        self.assertIn("Word Typing menu", text)


if __name__ == "__main__":
    unittest.main()
