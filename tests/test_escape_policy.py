import unittest

from modules.escape_guard import EscapePressGuard
from modules.keyquest_app import KeyQuestApp


class _Speech:
    def __init__(self):
        self.spoken = []

    def say(self, text, **kwargs):
        self.spoken.append((text, kwargs))


class _State:
    mode = "MENU"


class TestEscapePolicy(unittest.TestCase):
    def _build_app_stub(self):
        app = object.__new__(KeyQuestApp)
        app.state = _State()
        app.current_game = None
        app.escape_guard = EscapePressGuard()
        app._escape_remaining = 0
        app._escape_noun = ""
        app.speech = _Speech()
        app.quit_calls = []
        app._quit_app = lambda: app.quit_calls.append(True)
        return app

    def test_main_menu_escape_policy_requires_three_presses_to_quit(self):
        app = self._build_app_stub()

        policy = KeyQuestApp._escape_policy(app)

        self.assertEqual(policy["context"], "MENU")
        self.assertEqual(policy["required_presses"], 3)
        self.assertEqual(policy["action"], "quit")
        self.assertEqual(policy["noun"], "quit")

    def test_main_menu_escape_warns_before_quitting(self):
        app = self._build_app_stub()

        self.assertTrue(KeyQuestApp._handle_escape_shortcut(app))
        self.assertEqual(app._escape_remaining, 2)
        self.assertEqual(app._escape_noun, "quit")
        self.assertEqual(app.quit_calls, [])
        self.assertIn("Press 2 more times to quit", app.speech.spoken[-1][0])

        self.assertTrue(KeyQuestApp._handle_escape_shortcut(app))
        self.assertEqual(app._escape_remaining, 1)
        self.assertEqual(app.quit_calls, [])
        self.assertIn("Press 1 more time to quit", app.speech.spoken[-1][0])

        self.assertTrue(KeyQuestApp._handle_escape_shortcut(app))
        self.assertEqual(app._escape_remaining, 0)
        self.assertEqual(app.quit_calls, [True])


if __name__ == "__main__":
    unittest.main()
