"""In-memory record of what KeyQuest speaks, so an agent or a test can hear it.

Why this exists. KeyQuest is self-voicing, and the only way to know what it said
used to be a person listening. ``Speech.say`` records every utterance it hands
to a backend into a bounded ring here, with a monotonic index, so a caller can
ask "what was said since index N" and never miss or repeat a line. The optional
dev server (``modules/dev_server.py``) exposes the ring over loopback HTTP.

The ring records what passed the drop checks in ``Speech.say`` (debounce,
priority window, speech off). Dropped lines are not here; they are in the
opt-in transcript, ``modules/speech_log.py``, with their reasons.

Mute. Setting KEYQUEST_NO_SPEECH=1 before launch records speech exactly as
usual but never voices it, so automated runs do not talk over the owner's
screen reader. Pattern from Tanglebeep's ``TANGLEBEEP_NO_SPEECH``.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

MUTE_ENV = "KEYQUEST_NO_SPEECH"
DEFAULT_CAPACITY = 1000


def mute_requested() -> bool:
    """True when the environment asks for recorded-but-silent speech."""
    return os.environ.get(MUTE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


class SpeechRing:
    """Bounded, thread-safe ring of utterances with monotonic indices.

    Index 0 is the first line ever recorded; indices never reset or repeat, so
    when the ring has overflowed, the first entry returned for ``since(n)``
    having an index above ``n`` is how a caller knows lines were lost.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._entries: deque = deque(maxlen=capacity)
        self._next_index = 0
        self._cond = threading.Condition()

    @property
    def next_index(self) -> int:
        with self._cond:
            return self._next_index

    def record(self, text: str, interrupt: bool = True, priority: bool = False) -> int:
        """Store one utterance and wake any waiter. Returns its index."""
        with self._cond:
            index = self._next_index
            self._entries.append({
                "i": index,
                "t": round(time.time(), 3),
                "text": text,
                "interrupt": bool(interrupt),
                "priority": bool(priority),
            })
            self._next_index = index + 1
            self._cond.notify_all()
            return index

    def since(self, index: int) -> list[dict]:
        """Every retained entry whose index is ``index`` or later."""
        with self._cond:
            return [dict(e) for e in self._entries if e["i"] >= index]

    def wait_since(self, index: int, timeout: float) -> list[dict]:
        """Like ``since``, but wait up to ``timeout`` seconds for something new."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._cond:
            while self._next_index <= index:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return [dict(e) for e in self._entries if e["i"] >= index]
