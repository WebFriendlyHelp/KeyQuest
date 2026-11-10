"""Model what survives a burst of Speech.say calls made by one action.

Uses the REAL Speech.say drop logic (debounce, priority window) on a Speech
object built without loading Tolk or SAPI, muted so nothing is voiced. Its
ring then holds exactly what would have reached the backend, with each line's
interrupt flag.

The model: lines handed to the backend within one synchronous action are
microseconds apart, so a line followed by an INTERRUPTING line is cancelled
before it is heard (tolk.output(interrupt=True) and SAPI purge both cancel
what is in progress). What this cannot tell you is what a screen reader
actually voices; a few milliseconds of the cancelled line may be heard, and
NVDA's own queueing is not modelled. Real proof is a VM speech capture.
"""

import threading

from modules import speech_manager
from modules.speech_capture import SpeechRing


def make_speech():
    sp = speech_manager.Speech.__new__(speech_manager.Speech)
    sp.enabled = True
    sp._lock = threading.Lock()
    sp._priority_until = 0.0
    sp._last_text = ""
    sp._last_speak_time = 0.0
    sp.ring = SpeechRing()
    sp.muted = True
    sp.backend = "tolk"
    return sp


def lines_reaching_backend(sp):
    return sp.ring.since(0)


def heard(sp):
    """Texts not cancelled by an interrupting line that follows them."""
    entries = lines_reaching_backend(sp)
    survivors = []
    for i, entry in enumerate(entries):
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        if nxt is not None and nxt["interrupt"]:
            continue
        survivors.append(entry["text"])
    return survivors


def heard_text(sp):
    return " ".join(heard(sp))
