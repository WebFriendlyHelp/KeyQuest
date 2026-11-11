"""The pyttsx3 fallback speaks every queued line, in order.

Codex release review 2026-11-11, finding 1. The pyttsx3 path (used only when
the SAPI COM voice cannot be created) handed text to its worker through ONE
pending slot, so a second interrupt=False line overwrote the first before the
worker took it. The speech-burst fixes queue followers with interrupt=False,
so on this backend the reward or instruction line between a leader and a menu
was lost while the speech ring, and every ring-based test, recorded it.

Drives the real Speech.say and the real worker loop against a fake engine. It
proves what the worker hands to pyttsx3, not what any voice sounds like.
"""

import threading
import time
import unittest
from collections import deque

from modules import speech_manager
from modules.speech_capture import SpeechRing


class _FakeEngine:
    def __init__(self):
        self.spoken = []
        self._current = None

    def stop(self):
        pass

    def say(self, text):
        self._current = text

    def runAndWait(self):
        self.spoken.append(self._current)


def _tts_speech():
    sp = speech_manager.Speech.__new__(speech_manager.Speech)
    sp.enabled = True
    sp._lock = threading.Lock()
    sp._priority_until = 0.0
    sp._last_text = ""
    sp._last_speak_time = 0.0
    sp.ring = SpeechRing()
    sp.muted = False
    sp.backend = "tts"
    sp._sapi_voice = None
    sp._engine = _FakeEngine()
    sp._tts_queue_lock = threading.Lock()
    sp._tts_pending = deque()
    sp._tts_event = threading.Event()
    sp._tts_shutdown = False
    sp._tts_thread = None
    return sp


def _drain(sp, expected_count):
    worker = threading.Thread(target=sp._tts_worker_loop, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3.0
    while len(sp._engine.spoken) < expected_count and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.15)  # let a wrong extra line show up too
    sp._tts_shutdown = True
    sp._tts_event.set()
    worker.join(timeout=2.0)
    return sp._engine.spoken


class TestPyttsx3Queue(unittest.TestCase):
    def test_queued_lines_are_all_spoken_in_order(self):
        sp = _tts_speech()
        sp.say("Leader", priority=True, protect_seconds=3.0)
        sp.say("Reward", priority=True, interrupt=False)
        sp.say("Menu", priority=True, interrupt=False)
        self.assertEqual(_drain(sp, 3), ["Leader", "Reward", "Menu"])

    def test_an_interrupting_line_discards_what_was_queued(self):
        """Twin: interrupt=True still cancels pending lines, as before."""
        sp = _tts_speech()
        sp.say("Old one", priority=True, interrupt=False)
        sp.say("Old two", priority=True, interrupt=False)
        sp.say("Navigation", interrupt=True)
        self.assertEqual(_drain(sp, 1), ["Navigation"])


if __name__ == "__main__":
    unittest.main()
