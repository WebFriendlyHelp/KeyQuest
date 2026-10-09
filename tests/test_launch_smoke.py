"""Launch smoke test: start the real app and hear its first words.

Starts keyquest.pyw as a separate process the way tools/kq_drive.py does:
SDL dummy video and audio (no window, no sound), KEYQUEST_NO_SPEECH=1 (nothing
voiced), a temp KEYQUEST_PROGRESS_PATH (the real progress.json is never read or
written), and the loopback dev server on a free port. It then waits for the
first utterance and requires it to be the main menu's startup line, so a
startup that crashes, hangs, or reaches the menu without announcing it fails.

What it does not prove: anything about a real window, focus, or a screen
reader actually voicing the line.
"""

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT_SECONDS = 30.0
# The startup announcement: the first main-menu item, spoken without interrupt.
EXPECTED_FIRST_LINE = "Tutorial: T"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _instance_running() -> bool:
    # A second copy from this folder shows a native "already open" message
    # box, which is a real window that takes focus.
    from modules.single_instance import mutex_name

    handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, mutex_name())  # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


@unittest.skipUnless(os.name == "nt", "KeyQuest runs on Windows only")
class TestLaunchSmoke(unittest.TestCase):
    def test_first_utterance_is_the_main_menu_line(self):
        if _instance_running():
            self.skipTest("a KeyQuest from this folder is already running")
        port = _free_port()
        progress_dir = tempfile.mkdtemp(prefix="kq_smoke_")
        self.addCleanup(shutil.rmtree, progress_dir, True)
        env = dict(os.environ)
        env.update({
            "KEYQUEST_NO_SPEECH": "1",
            "KEYQUEST_PROGRESS_PATH": os.path.join(progress_dir, "progress.json"),
            "KEYQUEST_DEV_SERVER": str(port),
            "SDL_VIDEODRIVER": "dummy",
            "SDL_AUDIODRIVER": "dummy",
            "PYGAME_HIDE_SUPPORT_PROMPT": "1",
        })
        env.pop("KEYQUEST_SPEECH_LOG", None)
        proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "keyquest.pyw")],
            cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            entries = self._wait_for_first_utterance(proc, port)
        finally:
            proc.kill()
            proc.wait(timeout=10)
        self.assertIsNotNone(proc.returncode, "KeyQuest is still running after kill")
        with socket.socket() as s:
            s.settimeout(0.5)
            self.assertNotEqual(s.connect_ex(("127.0.0.1", port)), 0, "dev server port still open")

        first = entries[0]
        self.assertEqual(first["i"], 0)
        self.assertEqual(first["text"], EXPECTED_FIRST_LINE)
        self.assertFalse(first["interrupt"])

    def _wait_for_first_utterance(self, proc, port) -> list:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        url = f"http://127.0.0.1:{port}/speech?since=0&wait=2"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                self.fail(f"KeyQuest exited during startup with code {proc.returncode}")
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    lines = resp.read().decode("utf-8").splitlines()
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)  # server not up yet
                continue
            if lines:
                return [json.loads(line) for line in lines]
        self.fail(f"no speech within {STARTUP_TIMEOUT_SECONDS:.0f} s of launch")


if __name__ == "__main__":
    unittest.main()
