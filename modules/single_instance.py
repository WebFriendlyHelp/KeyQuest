"""Stop two copies of KeyQuest fighting over one progress file.

Why this matters: progress is saved as a whole document, last writer wins. Two
running copies each hold their own snapshot, so the one closed last silently
reverts everything earned in the other: lessons, XP, coins, pets, achievements.
A double-clicked shortcut is enough to lose an evening's work, and the user is
given no clue it happened.

A named Windows mutex is used rather than a lock file because the kernel
releases it when the process ends, however it ends. A lock file left behind by a
crash or a force-kill would block every future launch, which is a worse failure
than the one being prevented.

The retry window is the load-bearing detail. The updater relaunches KeyQuest as
the old copy exits, and those two can briefly overlap. Refusing to start in that
window would leave someone with no running app immediately after an update,
which is precisely the stranding this project has spent a long time eliminating.
So a second instance waits a few seconds for the first to finish leaving before
concluding it is genuinely a duplicate.
"""

from __future__ import annotations

import os
import time


# Global scope so it applies across the whole session, not just this desktop.
_MUTEX_NAME = "Global\\KeyQuest.SingleInstance.v1"
_ERROR_ALREADY_EXISTS = 183


class InstanceLock:
    """Holds the single-instance mutex for the lifetime of the process."""

    def __init__(self) -> None:
        self._handle = None

    def acquire(self, wait_seconds: float = 6.0) -> bool:
        """Try to become the only running instance.

        Returns True when this process owns the lock, or when the platform
        cannot support the check. Never raises: failing to test for a second
        instance must not stop the first one starting.
        """
        if os.name != "nt":
            return True
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE

            deadline = time.monotonic() + max(0.0, wait_seconds)
            while True:
                handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
                last_error = kernel32.GetLastError()

                if handle and last_error != _ERROR_ALREADY_EXISTS:
                    self._handle = handle
                    return True

                if handle:
                    kernel32.CloseHandle(handle)

                if time.monotonic() >= deadline:
                    return False
                # The other copy may be an outgoing instance mid-update.
                time.sleep(0.4)
        except Exception:
            return True

    def release(self) -> None:
        """Release the lock. Safe to call more than once, or never."""
        if self._handle is None:
            return
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
        except Exception:
            pass
        finally:
            self._handle = None


ALREADY_RUNNING_MESSAGE = (
    "KeyQuest is already running. Only one copy can be open at a time, because "
    "two copies would overwrite each other's saved progress. Please switch to "
    "the copy that is already open."
)


def show_already_running_message() -> None:
    """Tell the user why KeyQuest did not open, in a way they will actually get.

    A native Windows message box rather than the app's own dialog helper: that
    helper needs an already-initialised ``wx.App``, which does not exist this
    early, so it printed to a console nobody sees and the app simply vanished.
    Someone double-clicking the shortcut would get no explanation at all, which
    is the worst outcome for a user who cannot see that nothing happened.

    ``MessageBoxW`` is a standard Windows dialog, so screen readers announce it
    normally, and it needs nothing initialised first.
    """
    try:
        import ctypes

        MB_OK = 0x0
        MB_ICONINFORMATION = 0x40
        MB_SETFOREGROUND = 0x10000
        ctypes.windll.user32.MessageBoxW(
            None,
            ALREADY_RUNNING_MESSAGE,
            "KeyQuest Is Already Open",
            MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND,
        )
    except Exception:
        print(ALREADY_RUNNING_MESSAGE)
