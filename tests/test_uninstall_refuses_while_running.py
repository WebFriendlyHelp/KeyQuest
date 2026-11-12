"""The uninstaller refuses while KeyQuest is running.

1.28.1 review, finding 2. Uninstalling with KeyQuest open could not delete the
locked exe, removed progress.json, and then the running app saved it again: a
half-removed folder with a progress file, after an uninstall that promised to
remove everything.

KeyQuest now holds a fixed-name mutex while it runs, and KeyQuest.iss's
InitializeUninstall checks for it with CheckForMutexes and asks the learner to
close KeyQuest first. AppMutex is deliberately NOT used: Inno's documentation
says Setup checks it too, and the in-app updater runs Setup silently while
KeyQuest is handing over to the new copy.

What these prove: the app creates the mutex Inno looks for, under the exact
name the script uses, and lets it go. They do not run Inno; whether the
uninstaller really waits is a VM check.
"""

import ctypes
import os
import re
import sys
import unittest
import uuid
from ctypes import wintypes
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import single_instance  # noqa: E402

ISS = ROOT / "tools" / "build" / "installer" / "KeyQuest.iss"
SYNCHRONIZE = 0x00100000


def _mutex_exists(name: str) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, name)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


@unittest.skipUnless(os.name == "nt", "Windows mutexes")
class TestRunningMutex(unittest.TestCase):
    def setUp(self):
        # Unique names, so a KeyQuest open on this machine cannot interfere.
        suffix = uuid.uuid4().hex
        patches = [
            mock.patch.object(single_instance, "mutex_name", return_value=f"KeyQuestTest.Single.{suffix}"),
            mock.patch.object(single_instance, "RUNNING_MUTEX_NAME", f"KeyQuestTest.Running.{suffix}"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.name = single_instance.RUNNING_MUTEX_NAME

    def test_running_mutex_exists_while_the_lock_is_held(self):
        self.assertFalse(_mutex_exists(self.name), "negative twin: nothing holds it before start")
        lock = single_instance.InstanceLock()
        self.assertTrue(lock.acquire(wait_seconds=0))
        self.assertTrue(_mutex_exists(self.name))
        lock.release()
        self.assertFalse(_mutex_exists(self.name), "released with the lock")

    def test_a_refused_second_copy_does_not_keep_it(self):
        first = single_instance.InstanceLock()
        self.assertTrue(first.acquire(wait_seconds=0))
        second = single_instance.InstanceLock()
        self.assertFalse(second.acquire(wait_seconds=0))
        first.release()
        second.release()
        self.assertFalse(_mutex_exists(self.name))


class TestScriptChecksTheSameName(unittest.TestCase):
    def setUp(self):
        self.text = ISS.read_text(encoding="utf-8")

    def test_initialize_uninstall_checks_the_app_mutex(self):
        match = re.search(r"function InitializeUninstall\(\): Boolean;(.*?)\nend;", self.text, re.S)
        self.assertIsNotNone(match, "KeyQuest.iss has no InitializeUninstall")
        self.assertIn(f"'{single_instance.RUNNING_MUTEX_NAME}'", self.text)
        self.assertIn("CheckForMutexes", match.group(1))

    def test_setup_does_not_use_app_mutex(self):
        # AppMutex is also checked by Setup, which the silent updater runs.
        setup = self.text.split("[Setup]", 1)[1].split("\n[", 1)[0]
        self.assertNotRegex(setup, r"(?im)^\s*AppMutex\s*=")


if __name__ == "__main__":
    unittest.main()
