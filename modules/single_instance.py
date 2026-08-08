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

import hashlib
import os
import time


_ERROR_ALREADY_EXISTS = 183


def mutex_name() -> str:
    """Name the lock after the progress file it is actually protecting.

    Two copies only endanger each other when they save to the same place, and
    progress.json lives in the app directory. An installed copy and a portable
    copy have separate progress files and no conflict, so a single shared name
    refused the second one for nothing.

    Global scope is kept on purpose: two Windows accounts running the SAME
    installation do share one progress file, and that is a real conflict worth
    catching across sessions.
    """
    try:
        from modules.app_paths import get_app_dir

        # Casefolded because Windows paths are case-insensitive, so the same
        # folder reached by differently-cased names must produce one name.
        location = os.path.normcase(os.path.abspath(get_app_dir()))
    except Exception:
        location = ""
    digest = hashlib.sha256(location.encode("utf-8", "replace")).hexdigest()[:16]
    return f"Global\\KeyQuest.SingleInstance.v2.{digest}"


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

            # use_last_error so GetLastError is captured by ctypes at the call
            # itself. Reading it via a second foreign call is documented as
            # unreliable: machinery in between can clobber the value.
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE

            name = mutex_name()
            deadline = time.monotonic() + max(0.0, wait_seconds)
            while True:
                handle = kernel32.CreateMutexW(None, True, name)
                last_error = ctypes.get_last_error()

                if handle and last_error != _ERROR_ALREADY_EXISTS:
                    self._handle = handle
                    return True

                # Not asked here: whether the mutex is actually OWNED, as opposed
                # to merely existing. Waiting on it would answer that, but a
                # mutex is re-entrant for the thread that holds it, so the same
                # process would then be handed its own lock a second time and
                # the guard could no longer be proved in a test. The case it
                # would cover needs another program to create this exact name,
                # which is now a hash of the install path. Not worth trading a
                # provable guarantee for.

                if not handle:
                    # The call FAILED; that is not the same as "a duplicate is
                    # running". The realistic cause is another Windows account
                    # holding the mutex under its own default permissions, which
                    # returns ACCESS_DENIED and a NULL handle. That user's
                    # progress is a different file entirely, nothing is at risk,
                    # and refusing would tell them to switch to a copy running in
                    # a session they cannot reach. When we cannot check, we let
                    # them in: failing open costs a rare overwrite, failing
                    # closed costs someone the app entirely, with no way out.
                    return True

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
