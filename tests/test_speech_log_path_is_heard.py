"""Turning on the speech log says where the file is, after the option text.

Fable review 2026-11-10, modules finding 5 (speech log site). apply_speech_log
spoke "Speech log started. It is being written to <path>" from the option's
change handler, and the Options menu then announced the option's own text
with interrupt=True, cancelling it, so the path its docstring says must be
spoken was not.

Uses tests/speech_burst.py; it models cancellation, not what NVDA says.
"""

import unittest
from unittest import mock

from modules import menu_handler
from modules.keyquest_app import KeyQuestApp
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _options_menu(speech, on_change):
    state = {"value": False}
    return menu_handler.OptionsMenu(
        name="Options",
        options=[
            {
                "name": "speech_log",
                "get_value": lambda: state["value"],
                "set_value": lambda v: state.__setitem__("value", v),
                "get_text": lambda: f"Speech Log: {'On' if state['value'] else 'Off'}",
                "get_explanation": lambda: "Writes what KeyQuest says to a file.",
                "cycle": lambda value, _direction: not value,
            }
        ],
        speech_system=speech,
        on_change_callback=on_change,
    )


class TestSpeechLogPathIsHeard(unittest.TestCase):
    def test_the_real_handler_path_survives_the_option_text(self):
        speech = make_speech()
        app = mock.MagicMock()
        app.speech = speech
        app.state.settings.speech_log = True
        speech.set_logging = mock.Mock(return_value=True)
        app.options_menu.options = [{"name": "speech_log"}]

        def on_change(index, old, new):
            return KeyQuestApp._handle_option_change(app, index, old, new)

        app.apply_speech_log = lambda: KeyQuestApp.apply_speech_log(app)
        with mock.patch.object(type(speech), "log_path", new=property(lambda _s: "C:/KQ/keyquest_speech.log")):
            _options_menu(speech, on_change).cycle_current("right")
        text = heard_text(speech)
        self.assertIn("keyquest_speech.log", text, lines_reaching_backend(speech))
        self.assertIn("Speech Log: On", text)

    def test_options_without_a_follow_up_speak_once(self):
        """Negative twin: an on_change that returns nothing adds nothing."""
        speech = make_speech()
        _options_menu(speech, lambda *_a: None).cycle_current("right")
        self.assertEqual(len(lines_reaching_backend(speech)), 1)


if __name__ == "__main__":
    unittest.main()
