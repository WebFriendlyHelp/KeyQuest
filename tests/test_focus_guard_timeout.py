"""The focus guard says why when its control spawn times out.

On a machine whose default terminal is Windows Terminal, the control's
tasklist (run from a parent with no console) waits on the console handoff and
times out at 5 seconds. Until 1.28.1 that ended in a bare traceback in
tests/logs/focus_guard.txt. It must still exit 2 (cannot verify), and now says
what happened and how to rerun with the classic console host.

What this proves: run() takes the timeout path and writes the explanation.
pygame and the console check are stubbed, and the timeout is raised by hand,
so this says nothing about whether a real Windows Terminal handoff is slow.
What counts as a pass is unchanged and not exercised here.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import run_focus_guard as guard  # noqa: E402


def _fake_pygame():
    display = SimpleNamespace(
        init=lambda: None,
        set_mode=lambda size: None,
        set_caption=lambda title: None,
        get_wm_info=lambda: {"window": 1},
        quit=lambda: None,
    )
    return SimpleNamespace(display=display, event=SimpleNamespace(pump=lambda: None))


def _timeout():
    raise subprocess.TimeoutExpired(["tasklist", "/FI", "IMAGENAME eq Narrator.exe"], 5)


class TestControlTimeout(unittest.TestCase):
    def _run(self, spawn):
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "focus_guard.txt"
            with mock.patch.dict(sys.modules, {"pygame": _fake_pygame()}), mock.patch.object(
                guard, "kernel32", SimpleNamespace(GetConsoleWindow=lambda: 0)
            ), mock.patch.object(guard, "RESULT_FILE", result), mock.patch.object(
                guard, "spawn_unguarded", spawn
            ), mock.patch.object(guard, "spawn_guarded", lambda: None), mock.patch.object(
                guard.time, "sleep", lambda s: None
            ):
                code = guard.run()
            return code, result.read_text(encoding="utf-8")

    def test_timeout_is_cannot_verify_with_the_reason(self):
        code, text = self._run(_timeout)
        self.assertEqual(code, guard.EXIT_CANNOT_VERIFY)
        self.assertIn("CANNOT VERIFY", text)
        self.assertIn("did not finish within 5 seconds", text)
        self.assertIn("Windows Terminal", text)
        self.assertIn("Windows Console Host", text)
        self.assertIn("parent owns a console: False", text)
        self.assertNotIn("Traceback", text)

    def test_no_timeout_still_reports_the_plain_result(self):
        # Twin: a control that runs and makes no window is the old message.
        code, text = self._run(lambda: None)
        self.assertEqual(code, guard.EXIT_CANNOT_VERIFY)
        self.assertIn("the unguarded spawn created no window", text)
        self.assertNotIn("did not finish within", text)


if __name__ == "__main__":
    unittest.main()
