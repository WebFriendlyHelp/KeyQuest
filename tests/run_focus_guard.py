"""Real-window guard: KeyQuest must not conjure a window while probing for Narrator.

Why this exists. v1.26.0 fixed a bug where the app went deaf to keypresses
whenever no screen reader was running. `Speech._detect_narrator_process` spawned
`tasklist` once per second from the main loop, and KeyQuest ships windowed, so a
console child got a console window OF ITS OWN. It appeared, took the foreground,
and closed again. SDL only delivers keyboard input to the focused window, so
keys pressed in that gap were not slow, they were gone.

The lesson playthrough harness cannot see this class of bug at all: it runs on
SDL's dummy driver, so there is no real window and no real focus.

What is measured. Foreground theft is the harm, but foreground is a poor thing
to assert on: Windows refuses SetForegroundWindow to a process that does not
already own it, so on a CI runner or from a background shell the test window
never gets focus and a focus-based assertion silently measures nothing. The
mechanism underneath is what actually matters and is environment independent:
does the spawn create a new visible top-level window? That is exactly what
CREATE_NO_WINDOW prevents, and it is the thing that steals focus when the app
is the foreground window, which it is whenever a learner is typing.

THE TRAP THIS SCRIPT EXISTS TO AVOID. The bug only reproduces from a parent with
no console of its own, because a parent that already owns a console lends it to
console children and they never create a window. So:

  1. If started with a console, this script re-launches itself under pythonw.
  2. It first runs the OLD, unguarded pattern and REQUIRES it to create a
     window. If the environment cannot demonstrate the bug, the guard result
     is meaningless and this reports CANNOT-VERIFY rather than success.

Heads up: this briefly flashes console windows and may take the foreground.
That is the measurement, not a side effect.

    py -3.11 tests/run_focus_guard.py
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULT_FILE = ROOT / "tests" / "logs" / "focus_guard.txt"

EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_CANNOT_VERIFY = 2

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def visible_windows() -> set[int]:
    """Every visible top-level window handle, right now."""
    found: set[int] = set()

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            found.add(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


class Watcher:
    """Samples for windows that appear while a spawn is in flight."""

    def __init__(self, known: set[int], own_hwnd: int) -> None:
        self.known = set(known)
        self.own_hwnd = own_hwnd
        self._stop = threading.Event()
        self.new_windows: set[int] = set()
        self.foreign_foreground: set[int] = set()
        self._thread: threading.Thread | None = None

    def _run(self):
        while not self._stop.is_set():
            for hwnd in visible_windows() - self.known:
                if hwnd != self.own_hwnd:
                    self.new_windows.add(hwnd)
            foreground = int(user32.GetForegroundWindow() or 0)
            if foreground and foreground != self.own_hwnd:
                self.foreign_foreground.add(foreground)
            time.sleep(0.004)

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return False


def spawn_unguarded():
    """Exactly what speech_manager did before v1.26.0."""
    subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Narrator.exe"],
        capture_output=True, text=True, timeout=5, check=False,
    )


def spawn_guarded():
    """Exactly what speech_manager does now, through the real module."""
    from modules.speech_manager import Speech

    Speech._detect_narrator_process(Speech.__new__(Speech))


def measure(spawn, rounds, own_hwnd, pygame_module, label, lines):
    baseline = visible_windows()
    with Watcher(baseline, own_hwnd) as watcher:
        for _ in range(rounds):
            spawn()
            pygame_module.event.pump()
            time.sleep(0.08)
    created = len(watcher.new_windows)
    stole = len(watcher.foreign_foreground)
    lines.append(
        f"{label}: {created} new visible window(s) created across {rounds} "
        f"spawn(s); {stole} foreign foreground window(s) observed"
    )
    return created > 0


def run() -> int:
    lines: list[str] = []

    # A real window is the entire point, so make sure nothing left the dummy
    # video driver set in the environment.
    os.environ.pop("SDL_VIDEODRIVER", None)
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

    import pygame

    pygame.display.init()
    pygame.display.set_mode((640, 480))
    pygame.display.set_caption("KeyQuest focus guard")
    own_hwnd = int(pygame.display.get_wm_info().get("window") or 0)
    if not own_hwnd:
        lines.append("CANNOT VERIFY: could not obtain the pygame window handle.")
        return finish(lines, EXIT_CANNOT_VERIFY)

    user32.SetForegroundWindow(own_hwnd)
    for _ in range(25):
        pygame.event.pump()
        time.sleep(0.02)
        if int(user32.GetForegroundWindow() or 0) == own_hwnd:
            break

    has_console = bool(kernel32.GetConsoleWindow())
    lines.append(f"parent owns a console: {has_console} "
                 "(must be False for the bug to be reproducible)")
    lines.append(f"real pygame window created: hwnd {own_hwnd}")
    lines.append(f"window reached the foreground: "
                 f"{int(user32.GetForegroundWindow() or 0) == own_hwnd} "
                 "(not required; window creation is the signal)")
    lines.append("")

    if has_console:
        lines.append("CANNOT VERIFY: running with a console attached, so console "
                     "children inherit it and never create a window.")
        return finish(lines, EXIT_CANNOT_VERIFY)

    # Control first. If the old pattern creates no window here, this environment
    # cannot demonstrate the bug and the guard result would be a false pass.
    control_created = measure(spawn_unguarded, 4, own_hwnd, pygame,
                              "CONTROL  (pre-1.26.0 unguarded spawn)", lines)
    guard_created = measure(spawn_guarded, 6, own_hwnd, pygame,
                            "GUARDED  (current speech_manager probe)", lines)

    lines.append("")
    pygame.display.quit()

    if not control_created:
        lines.append(
            "CANNOT VERIFY: the unguarded spawn created no window in this "
            "environment, so this run proves nothing about the guard. Not "
            "reporting success."
        )
        return finish(lines, EXIT_CANNOT_VERIFY)

    if guard_created:
        lines.append(
            "REGRESSED: the current probe creates a window. When KeyQuest is "
            "the foreground window, which it is whenever someone is typing, "
            "that window takes the keyboard and the keystroke is lost."
        )
        return finish(lines, EXIT_REGRESSED)

    lines.append(
        "PASS: the unguarded spawn creates a window here, so this test can "
        "detect the bug, and the current probe creates none."
    )
    return finish(lines, EXIT_OK)


def finish(lines, code) -> int:
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


def relaunch_without_console() -> int:
    """Re-run under pythonw so console children get windows of their own."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        print("CANNOT VERIFY: no pythonw.exe beside this interpreter, so the "
              "test cannot run without a console and would measure nothing.")
        return EXIT_CANNOT_VERIFY

    completed = subprocess.run([str(pythonw), str(Path(__file__).resolve())],
                               check=False)
    if RESULT_FILE.exists():
        print(RESULT_FILE.read_text(encoding="utf-8"), end="")
    else:
        print("CANNOT VERIFY: the windowed run produced no result file.")
        return EXIT_CANNOT_VERIFY
    return completed.returncode


if __name__ == "__main__":
    if os.name != "nt":
        print("Windows only; KeyQuest is a Windows app.")
        sys.exit(EXIT_CANNOT_VERIFY)
    if kernel32.GetConsoleWindow():
        sys.exit(relaunch_without_console())
    sys.exit(run())
