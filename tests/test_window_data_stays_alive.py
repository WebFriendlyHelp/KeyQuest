"""The SDL window's "pg_window" pointer must point at a live Python object.

The 1.28.1 release crash (release.yml run 43309104393, 2026-11-12): KeyQuest
died at startup with 0xC0000005 inside pygame.event.get. Under full page heap
on the GitHub runner it crashed every time, for 1.28.0's code too, at
`Py_INCREF(pgWindow)` in pygame 2.6.1's dict_from_event (src_c/event.c), with
pgWindow pointing at freed memory.

The cause is in KeyQuestApp._maximize_window. pygame's
`Window.from_display_module()` stores a pointer to the new Window object in
the SDL window's data under "pg_window" without taking a reference
(src_c/cython/pygame/_sdl2/video.pyx). The method kept the Window in a local
variable, so it was freed on return, and every later window event (shown,
maximized, focus, resize) made pygame increment and hand out the freed
object. Whether that crashes depends on what reused the memory, which is
why it came and went with unrelated changes.

What this proves: after _maximize_window returns and garbage is collected,
the pointer SDL holds is the address of an object KeyQuest still references.
It runs on SDL's dummy video driver; it does not show a real window event
being delivered, which the page-heap run on the runner does.
"""

import ctypes
import gc
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from modules.keyquest_app import KeyQuestApp  # noqa: E402


def _sdl():
    lib = ctypes.CDLL(os.path.join(os.path.dirname(pygame.__file__), "SDL2.dll"))
    lib.SDL_GetWindowFromID.argtypes = [ctypes.c_uint32]
    lib.SDL_GetWindowFromID.restype = ctypes.c_void_p
    lib.SDL_GetWindowData.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.SDL_GetWindowData.restype = ctypes.c_void_p
    return lib


def _pg_window_pointer() -> int:
    lib = _sdl()
    for window_id in range(1, 64):
        window = lib.SDL_GetWindowFromID(window_id)
        if window:
            return lib.SDL_GetWindowData(window, b"pg_window") or 0
    raise AssertionError("no SDL window found")


@unittest.skipUnless(os.name == "nt", "SDL2.dll is loaded by name on Windows")
class TestWindowDataStaysAlive(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((200, 150))
        self.addCleanup(pygame.display.quit)

    def test_pg_window_points_at_an_object_the_app_keeps(self):
        app = object.__new__(KeyQuestApp)
        KeyQuestApp._maximize_window(app)
        gc.collect()
        pointer = _pg_window_pointer()
        if not pointer:
            self.skipTest("pygame stored no pg_window pointer on this build")
        kept = getattr(app, "_sdl_window", None)
        self.assertIsNotNone(kept, "the Window object was not kept, so SDL holds a freed pointer")
        self.assertEqual(pointer, id(kept))

    def test_a_dropped_window_object_leaves_a_dangling_pointer(self):
        # Negative twin: the pygame behaviour this guards against. A Window made
        # and dropped leaves SDL pointing at an address no live object has.
        from pygame._sdl2.video import Window

        window = Window.from_display_module()
        self.assertEqual(_pg_window_pointer(), id(window))
        # Only this local and getrefcount's own argument: SDL's pointer holds no
        # reference, so dropping the local frees the object it points at.
        self.assertEqual(sys.getrefcount(window), 2)


if __name__ == "__main__":
    unittest.main()
