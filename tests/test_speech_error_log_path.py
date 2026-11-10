"""Speech errors go to the app's error log, not the current directory.

Fable review 2026-11-10, modules finding 13. speech_manager opened the bare
relative name "keyquest_error.log", so when the working directory was not the
app folder, Tolk and SAPI exceptions went somewhere Report a Problem never
looks, or failed silently.
"""

import os
import tempfile
import unittest
from unittest import mock

from modules import error_logging, speech_manager


class TestSpeechErrorLogPath(unittest.TestCase):
    def test_log_exception_writes_to_the_app_folder_log(self):
        with tempfile.TemporaryDirectory() as app_dir, tempfile.TemporaryDirectory() as elsewhere:
            old_cwd = os.getcwd()
            os.chdir(elsewhere)
            try:
                with mock.patch.object(error_logging, "get_app_dir", return_value=app_dir):
                    try:
                        raise RuntimeError("tolk exploded")
                    except RuntimeError as exc:
                        speech_manager.log_exception(exc)
            finally:
                os.chdir(old_cwd)
            stray = os.path.exists(os.path.join(elsewhere, "keyquest_error.log"))
            target = os.path.join(app_dir, error_logging.LOG_FILE)
            written = open(target, encoding="utf-8").read() if os.path.exists(target) else ""
        self.assertFalse(stray, "nothing may be written to the working directory")
        self.assertIn("tolk exploded", written)


if __name__ == "__main__":
    unittest.main()
