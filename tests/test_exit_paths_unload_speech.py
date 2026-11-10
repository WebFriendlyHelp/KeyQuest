"""Every exit path unloads speech before pygame quits.

Fable review 2026-11-10, modules finding 10. CLAUDE.md requires
speech.shutdown() before pygame.quit() (Tolk is never left to __del__). Both
update handoffs called pygame.quit(); sys.exit(0) without it, and the
unhandled-exception path in main() exited without unloading Tolk.

The first test is structural (it reads the source); it proves the call is
there, not that NVDA keeps speaking the farewell line after unload. The
second drives main() with an app whose run() raises.
"""

import ast
import inspect
import unittest
from unittest import mock

from modules import keyquest_app, update_controller


def _quit_calls_without_shutdown(module):
    tree = ast.parse(inspect.getsource(module))
    offenders = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for i, stmt in enumerate(body):
            src = ast.unparse(stmt) if isinstance(stmt, ast.Expr) else ""
            if src == "pygame.quit()":
                before = " ".join(ast.unparse(s) for s in body[max(0, i - 3):i])
                if "speech.shutdown()" not in before:
                    offenders.append(stmt.lineno)
    return offenders


class TestExitPathsUnloadSpeech(unittest.TestCase):
    def test_every_pygame_quit_follows_speech_shutdown(self):
        for module in (update_controller, keyquest_app):
            source = inspect.getsource(module)
            self.assertIn("pygame.quit()", source, "pin that the scan has something to check")
            self.assertEqual(_quit_calls_without_shutdown(module), [], module.__name__)

    def test_the_scan_catches_a_bare_quit(self):
        """Negative twin: the checker must be able to fail."""
        fake = type("M", (), {})()
        src = "def f():\n    x = 1\n    pygame.quit()\n"
        with mock.patch.object(inspect, "getsource", return_value=src):
            self.assertEqual(_quit_calls_without_shutdown(fake), [3])

    def test_a_crash_in_run_unloads_speech(self):
        app = mock.MagicMock()
        app.run.side_effect = RuntimeError("boom")
        with mock.patch.object(keyquest_app, "KeyQuestApp", return_value=app), \
                mock.patch.object(keyquest_app, "_offer_general_error_log_copy"), \
                mock.patch.object(keyquest_app.error_logging, "log_exception"), \
                mock.patch.object(keyquest_app.error_logging, "log_message"):
            keyquest_app.main()
        app.speech.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
