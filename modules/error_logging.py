import traceback
import os
import time
from modules.app_paths import get_app_dir

LOG_FILE = "keyquest_error.log"
_MAX_LOG_BYTES = 512 * 1024  # 512 KB


def get_log_file_path() -> str:
    """Return the full path to the local KeyQuest error log."""
    return os.path.join(get_app_dir(), LOG_FILE)


def touch_log_file() -> str:
    """Ensure the local error log file exists and return its path."""
    path = get_log_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "a", encoding="utf-8"):
                pass
    except OSError:
        pass
    return path


def _rotate_if_needed() -> None:
    """Truncate the log file if it exceeds the size limit."""
    try:
        log_path = touch_log_file()
        if os.path.getsize(log_path) > _MAX_LOG_BYTES:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=== Log rotated (exceeded 512 KB) ===\n")
    except OSError:
        pass


def log_exception(e: BaseException) -> None:
    """Append an exception traceback to the log file."""
    try:
        _rotate_if_needed()
        with open(touch_log_file(), "a", encoding="utf-8") as f:
            f.write("=== Unhandled exception ===\n")
            traceback.print_exc(file=f)
            f.write("\n")
    except Exception:
        pass


def log_message(label: str, message: str, tb_str: str = "") -> None:
    """Append a labelled message to the log file (used by subsystems like dialogs)."""
    try:
        _rotate_if_needed()
        with open(touch_log_file(), "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"{label}\n")
            f.write(f"{message}\n")
            if tb_str:
                f.write(f"Traceback:\n{tb_str}\n")
            f.write(f"{'=' * 60}\n")
    except Exception:
        pass


def read_log_tail(max_chars: int = 2000) -> str:
    """Return the tail of the local log for previews or support sharing."""
    try:
        with open(touch_log_file(), "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""

    if len(text) <= max_chars:
        return text.strip()
    return text[-max_chars:].strip()


def read_full_log() -> str:
    """Return the full local error log contents."""
    try:
        with open(touch_log_file(), "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_HWND_MESSAGE = -3


def copy_text_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard, without building a window to do it.

    This used to create a ``tkinter`` root window: ``Tk()``, ``withdraw()``,
    ``clipboard_append``, ``destroy``. That starts a third GUI toolkit and
    creates a real top-level window inside a process already running SDL and
    wx, in an app that keeps a whole test harness (`tests/run_focus_guard.py`)
    devoted to nothing spawning stray windows, because a spawned window is what
    stole the keyboard in v1.26.0. It was also the last Python code known to be
    running before the v1.27.1 crash recorded in HANDOFF; that is a suspicion
    and not a proven cause, and the crash item stays open regardless.

    The clipboard is owned by a **message-only** window, which is invisible,
    never activated, and absent from alt-tab and from window enumeration.
    ``EmptyClipboard`` on a clipboard opened with a NULL handle is documented to
    set the owner to NULL and make ``SetClipboardData`` fail; it happens to
    work on Windows 11 here, but a real owner is what the API asks for, so the
    NULL form is only a fallback.

    Opening the clipboard is retried briefly: any other application can hold it
    for a moment, and that is a wait, not a failure.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.restype = wintypes.BOOL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        payload = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)

        owner = _message_only_window(user32, ctypes, wintypes)
        try:
            opened = False
            for _ in range(10):
                if user32.OpenClipboard(owner):
                    opened = True
                    break
                time.sleep(0.02)
            if not opened:
                kernel32.GlobalFree(handle)
                return False

            try:
                user32.EmptyClipboard()
                if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                    # Ownership did not transfer, so the memory is still ours.
                    kernel32.GlobalFree(handle)
                    return False
            finally:
                user32.CloseClipboard()
        finally:
            if owner:
                user32.DestroyWindow(owner)
        return True
    except Exception:
        return False


def _message_only_window(user32, ctypes, wintypes):
    """A window that exists only to own the clipboard. None if it cannot be made."""
    try:
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        return user32.CreateWindowExW(
            0, "STATIC", None, 0, 0, 0, 0, 0,
            ctypes.cast(_HWND_MESSAGE, wintypes.HWND), None, None, None,
        ) or None
    except Exception:
        return None


def copy_log_to_clipboard() -> bool:
    """Copy the full local error log to the clipboard."""
    text = read_full_log()
    if not text:
        return False
    return copy_text_to_clipboard(text)
