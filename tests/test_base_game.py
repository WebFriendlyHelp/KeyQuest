import unittest

from games.base_game import BaseGame
from modules import dialog_manager


class _DummyGame(BaseGame):
    NAME = "Dummy"
    DESCRIPTION = "Dummy"
    INSTRUCTIONS = "Dummy"
    HOTKEYS = "Dummy"

    def start_playing(self):
        return None

    def handle_game_input(self, event, mods):
        return None

    def draw_game(self):
        return None


class TestBaseGameSessionCallback(unittest.TestCase):
    def test_show_game_results_triggers_session_callback(self):
        captured = {}

        def _on_complete(game, stats):
            captured["game_name"] = game.NAME
            captured["stats"] = stats

        original_show = dialog_manager.show_results_dialog
        dialog_manager.show_results_dialog = lambda *args, **kwargs: None
        try:
            game = _DummyGame(
                screen=None,
                fonts={"title_font": None, "text_font": None, "small_font": None},
                speech=None,
                play_sound_func=lambda wave: None,
                show_info_dialog_func=lambda title, content: None,
                session_complete_callback=_on_complete,
            )
            game.show_game_results("done", session_stats={"pet_xp": 15, "accuracy": 90})
        finally:
            dialog_manager.show_results_dialog = original_show

        self.assertEqual(captured["game_name"], "Dummy")
        self.assertEqual(captured["stats"]["pet_xp"], 15)

    def test_show_game_results_uses_escape_only_close_behavior(self):
        captured = {}

        def _fake_show_results_dialog(*args, **kwargs):
            captured["kwargs"] = kwargs

        original_show = dialog_manager.show_results_dialog
        dialog_manager.show_results_dialog = _fake_show_results_dialog
        try:
            game = _DummyGame(
                screen=None,
                fonts={"title_font": None, "text_font": None, "small_font": None},
                speech=None,
                play_sound_func=lambda wave: None,
                show_info_dialog_func=lambda title, content: None,
            )
            game.show_game_results("done")
        finally:
            dialog_manager.show_results_dialog = original_show

        self.assertFalse(captured["kwargs"]["close_on_enter"])
        self.assertTrue(captured["kwargs"]["close_on_escape"])
        self.assertFalse(captured["kwargs"]["close_on_space"])


if __name__ == "__main__":
    unittest.main()
