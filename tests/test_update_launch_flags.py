"""Regression test for how the in-app updater spawns its ``.bat`` helper.

The update launcher's wait-loop uses ``tasklist | find " <pid> "``. Windows
``find.exe`` requires a console; if the helper is spawned with
``DETACHED_PROCESS`` it has NO console, so ``find`` hangs forever and the update
never proceeds (Windows even pops a stray console window for the orphaned
``find`` — the "stuck cmd window" users reported). The fix is to launch with a
hidden-but-real console (``CREATE_NO_WINDOW``) and never ``DETACHED_PROCESS``.

These tests lock that in so the regression cannot silently come back.
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import update_controller

_SOURCE = Path(__file__).parent.parent / "modules" / "update_controller.py"


class TestBatLauncherCreationFlags(unittest.TestCase):
    def test_flags_do_not_include_detached_process(self):
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        flags = update_controller.bat_launcher_creationflags()
        if detached:
            self.assertEqual(
                flags & detached,
                0,
                "Update .bat must NOT be launched DETACHED: a detached process has "
                "no console and the wait-loop's find.exe hangs forever.",
            )

    def test_flags_include_create_no_window(self):
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags = update_controller.bat_launcher_creationflags()
        if no_window:
            self.assertEqual(
                flags & no_window,
                no_window,
                "Update .bat needs a hidden-but-real console (CREATE_NO_WINDOW).",
            )

    def test_source_never_reintroduces_detached_process(self):
        # Catch DETACHED_PROCESS creeping back into any launch site, even one that
        # bypasses the helper. Matches the two code-access forms, not prose/docstrings.
        src = _SOURCE.read_text(encoding="utf-8")
        self.assertNotIn(
            '"DETACHED_PROCESS"',
            src,
            "getattr(subprocess, \"DETACHED_PROCESS\", ...) reintroduced — it hangs the updater.",
        )
        self.assertNotIn(
            "subprocess.DETACHED_PROCESS",
            src,
            "subprocess.DETACHED_PROCESS reintroduced — it hangs the updater wait-loop.",
        )


if __name__ == "__main__":
    unittest.main()
