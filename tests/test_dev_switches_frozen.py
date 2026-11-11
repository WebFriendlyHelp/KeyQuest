"""Developer switches are refused in a shipped (frozen) build.

Fable release review, 2026-11-11 (medium): --dev-server, KEYQUEST_DEV_SERVER,
KEYQUEST_NO_SPEECH and KEYQUEST_PROGRESS_PATH all worked in an installed
KeyQuest.exe. A stray KEYQUEST_NO_SPEECH=1 gives a blind learner a silent
KeyQuest with no message saying why, and the dev server answers any local
program. Nothing legitimate uses them in a frozen build: release.yml's smoke
step runs only --selftest, and tests/test_launch_smoke.py and tools/kq_drive.py
start keyquest.pyw from source.

These set sys.frozen the way PyInstaller does and call the real readers. They
prove the readers' decisions, not a real bundle; the VM checklist starts the
installed exe with the variables set.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import dev_server, speech_capture, state_manager  # noqa: E402


class FrozenRefusesDevSwitches(unittest.TestCase):
    def frozen(self):
        return mock.patch.object(sys, "frozen", True, create=True)

    def test_dev_server_flag_and_env_refused_when_frozen(self):
        with self.frozen():
            self.assertIsNone(dev_server.requested_port(["--dev-server"], {}))
            self.assertIsNone(dev_server.requested_port(["--dev-server=50002"], {}))
            self.assertIsNone(dev_server.requested_port([], {dev_server.ENV_FLAG: "1"}))

    def test_dev_server_still_works_from_source(self):
        # Negative twin: a source run keeps the switch.
        self.assertFalse(getattr(sys, "frozen", False))
        self.assertEqual(dev_server.requested_port(["--dev-server"], {}), dev_server.DEFAULT_PORT)
        self.assertEqual(dev_server.requested_port([], {dev_server.ENV_FLAG: "1"}), dev_server.DEFAULT_PORT)

    def test_no_speech_refused_when_frozen(self):
        with mock.patch.dict(os.environ, {speech_capture.MUTE_ENV: "1"}):
            with self.frozen():
                self.assertFalse(speech_capture.mute_requested())
            self.assertTrue(speech_capture.mute_requested())   # twin: source run

    def test_progress_path_refused_when_frozen(self):
        with tempfile.TemporaryDirectory() as d:
            override = os.path.join(d, "elsewhere.json")
            with mock.patch.dict(os.environ, {state_manager.PROGRESS_PATH_ENV: override}):
                with self.frozen():
                    self.assertNotEqual(state_manager.ProgressManager().filename, override)
                    self.assertTrue(state_manager.ProgressManager().filename.endswith("progress.json"))
                self.assertEqual(state_manager.ProgressManager().filename, override)   # twin


if __name__ == "__main__":
    unittest.main()
