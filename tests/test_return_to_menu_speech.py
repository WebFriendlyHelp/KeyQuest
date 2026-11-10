"""Returning to the main menu queues the menu line behind the summary.

Fable review 2026-11-10, modules finding 5 (test_modes and keyquest_app
sites). The spoken speed-test and sentence-practice summaries, and "Exiting to
main menu.", were each followed in the same call by say_menu(), whose menu
line used interrupt=True and cancelled them.

Uses tests/speech_burst.py and the real Menu, KeyQuestApp.say_menu and
escape handling; it models cancellation, not what NVDA says.
"""

import types
import unittest
from unittest import mock

from modules import challenge_manager, menu_handler, test_modes
from modules.escape_guard import EscapePressGuard
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _app_with_real_menu(speech):
    app = mock.MagicMock()
    app.speech = speech
    app.main_menu = menu_handler.Menu("Main", ["Lessons", "Games"], speech, lambda *_a: None)
    app.say_menu = lambda **kw: KeyQuestApp.say_menu(app, **kw)
    return app


class TestSummaryThenMenu(unittest.TestCase):
    def test_speed_test_summary_survives_the_menu(self):
        speech = make_speech()
        app = _app_with_real_menu(speech)
        app.state.settings = Settings()
        app.state.settings.daily_challenge_completed = True
        app.state.test = types.SimpleNamespace(
            running=True, start_time=0.0, duration_seconds=60.0, total_chars=100,
            correct_chars=100, sentences_started=5, sentences_completed=5,
        )
        app.apply_pet_session_progress.return_value = {}
        with mock.patch.object(challenge_manager, "get_today_challenge",
                               return_value={"type": "lesson_count", "target": {}}), \
                mock.patch.object(test_modes.dashboard_manager, "record_session"):
            test_modes.finish_test(app)
        text = heard_text(speech)
        self.assertIn("Speed test complete", text, lines_reaching_backend(speech))
        self.assertIn("Main menu", text)

    def test_exiting_a_game_by_escape_is_heard(self):
        speech = make_speech()
        app = object.__new__(KeyQuestApp)
        app.state = types.SimpleNamespace(mode="GAME")
        app.current_game = types.SimpleNamespace(mode="PLAYING", NAME="Letter Fall")
        app.escape_guard = EscapePressGuard()
        app._escape_remaining = 0
        app._escape_noun = ""
        app.speech = speech
        app.main_menu = menu_handler.Menu("Main", ["Lessons", "Games"], speech, lambda *_a: None)
        for _ in range(3):
            KeyQuestApp._handle_escape_shortcut(app)
        entries = lines_reaching_backend(speech)
        last_two = entries[-2:]
        survivors = [e["text"] for i, e in enumerate(last_two)
                     if not (i + 1 < len(last_two) and last_two[i + 1]["interrupt"])]
        self.assertIn("Exiting to main menu.", survivors, entries)
        self.assertTrue(any("Main menu" in t for t in survivors), entries)

    def test_opening_the_menu_from_elsewhere_still_interrupts(self):
        """Negative twin: a plain say_menu() keeps interrupting."""
        speech = make_speech()
        app = _app_with_real_menu(speech)
        app.say_menu()
        self.assertTrue(lines_reaching_backend(speech)[-1]["interrupt"])


if __name__ == "__main__":
    unittest.main()
