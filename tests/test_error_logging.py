import inspect
import os
import sys
import unittest
from unittest import mock

from modules import error_logging


class TestErrorLogging(unittest.TestCase):
    def test_copy_log_to_clipboard_uses_full_log_contents(self):
        with mock.patch("modules.error_logging.read_full_log", return_value="sample log text"):
            with mock.patch("modules.error_logging.copy_text_to_clipboard", return_value=True) as copy_mock:
                copied = error_logging.copy_log_to_clipboard()

        self.assertTrue(copied)
        copy_mock.assert_called_once_with("sample log text")

    def test_copy_log_to_clipboard_returns_false_for_empty_log(self):
        with mock.patch("modules.error_logging.read_full_log", return_value=""):
            with mock.patch("modules.error_logging.copy_text_to_clipboard") as copy_mock:
                copied = error_logging.copy_log_to_clipboard()

        self.assertFalse(copied)
        copy_mock.assert_not_called()


class TestTheClipboardBuildsNoWindow(unittest.TestCase):
    """It used to raise a tkinter root window to copy text.

    That is a third GUI toolkit and a real top-level window inside a process
    already running SDL and wx, in an app with a harness devoted to nothing
    spawning stray windows. It was also the last Python running before the
    v1.27.1 crash in HANDOFF, which is unexplained rather than fixed.
    """

    def test_tkinter_is_not_used_and_not_even_imported(self):
        source = inspect.getsource(error_logging)
        self.assertNotIn("import tkinter", source,
                         "copying text must not start a second GUI toolkit")
        self.assertNotIn("tk.Tk(", source)
        self.assertNotIn("tkinter", sys.modules,
                         "importing the module must not drag tkinter in")

    def test_the_owner_window_is_message_only(self):
        """A message-only window cannot be shown, activated, or alt-tabbed to."""
        source = inspect.getsource(error_logging)
        self.assertIn("_HWND_MESSAGE", source)
        self.assertEqual(error_logging._HWND_MESSAGE, -3)

    def test_a_failure_returns_false_rather_than_raising(self):
        """A failed copy is reported to the user; a crash helps nobody."""
        with mock.patch("ctypes.windll") as windll:
            windll.kernel32.GlobalAlloc.side_effect = OSError("no memory")
            self.assertFalse(error_logging.copy_text_to_clipboard("anything"))

    def test_memory_is_released_when_the_clipboard_will_not_open(self):
        """Ownership only transfers on success, so the rest is ours to free."""
        with mock.patch("ctypes.windll") as windll, \
                mock.patch("ctypes.memmove"), \
                mock.patch("time.sleep"):
            windll.kernel32.GlobalAlloc.return_value = 4242
            windll.kernel32.GlobalLock.return_value = 999
            windll.user32.OpenClipboard.return_value = 0  # held by someone else
            self.assertFalse(error_logging.copy_text_to_clipboard("anything"))
            windll.kernel32.GlobalFree.assert_called_with(4242)

    @unittest.skipUnless(os.environ.get("KEYQUEST_CLIPBOARD_TEST") == "1",
                         "overwrites the developer's clipboard; opt in with "
                         "KEYQUEST_CLIPBOARD_TEST=1")
    def test_a_real_round_trip(self):
        payload = "KeyQuest round trip\n" + ("line\n" * 1000)
        self.assertTrue(error_logging.copy_text_to_clipboard(payload))
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True)
        self.assertIn("KeyQuest round trip", result.stdout)


if __name__ == "__main__":
    unittest.main()
