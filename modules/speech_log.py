"""Opt-in transcript of everything KeyQuest tries to say, and everything it does not.

Why this exists. When a blind user reports "it went quiet" or "it felt sluggish",
there is nothing to look at afterwards. Speech is the product, and it was the one
subsystem leaving no trace. Two shipped bugs were found only because a tester
described symptoms well enough to reconstruct them by hand.

The most valuable thing here is not the list of what was spoken. It is the list
of what was DROPPED and why: ``Speech.say`` has several paths that return without
speaking (duplicate debounce, the priority protection window, speech disabled,
no backend), and each one is silent by design. A user cannot tell a dropped
announcement from one that was never requested.

Cost, measured rather than assumed: one line is about 5 microseconds with the
handle held open, against 102 microseconds if the file is opened and closed each
time. So the handle stays open and every line is flushed, which is both faster
and crash-safe. For scale, the per-second work that caused the v1.26.0 focus bug
cost about 68,000 microseconds.

Off unless asked for. Turn it on with the Speech Log setting, or by setting the
environment variable KEYQUEST_SPEECH_LOG to 1 before launching.
"""

from __future__ import annotations

import os
import threading
import time

from modules.app_paths import get_app_dir

LOG_FILENAME = "keyquest_speech.log"
ENV_FLAG = "KEYQUEST_SPEECH_LOG"

_MAX_BYTES = 2 * 1024 * 1024
_ROTATE_CHECK_EVERY = 500  # stat() per line would cost more than the write


def get_log_path() -> str:
    """Full path to the speech transcript, beside the error log."""
    return os.path.join(get_app_dir(), LOG_FILENAME)


def env_requested() -> bool:
    """True when the environment asks for logging at startup."""
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def quote(text: str) -> str:
    """One line, always, however odd the text is."""
    cleaned = str(text).replace("\\", "\\\\").replace('"', '\\"')
    cleaned = cleaned.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    return f'"{cleaned}"'


class SpeechLog:
    """Append-only transcript. Never raises; a broken log must not break speech."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handle = None
        self._started = 0.0
        self._records = 0
        self._path = ""

    @property
    def enabled(self) -> bool:
        return self._handle is not None

    @property
    def path(self) -> str:
        return self._path

    def enable(self, path: str | None = None) -> bool:
        """Open the transcript. Returns whether logging is now on."""
        with self._lock:
            if self._handle is not None:
                return True
            target = path or get_log_path()
            try:
                self._rotate_if_needed(target)
                self._handle = open(target, "a", encoding="utf-8")
                self._path = target
                self._started = time.perf_counter()
                self._records = 0
            except OSError:
                self._handle = None
                return False
        return True

    def disable(self) -> None:
        with self._lock:
            if self._handle is not None:
                try:
                    self._write_line("SESSION-END", {})
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None

    @staticmethod
    def _rotate_if_needed(target: str) -> None:
        try:
            if os.path.exists(target) and os.path.getsize(target) > _MAX_BYTES:
                os.replace(target, target + ".1")
        except OSError:
            pass

    def _write_line(self, event: str, fields: dict) -> None:
        """Caller holds the lock."""
        parts = [f"+{time.perf_counter() - self._started:8.3f}s", event]
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        self._handle.write(" ".join(parts) + "\n")
        self._handle.flush()

    def record(self, event: str, text: str | None = None, **fields) -> None:
        """Record one speech event. Safe to call when logging is off."""
        if self._handle is None:
            return
        with self._lock:
            if self._handle is None:
                return
            try:
                if text is not None:
                    fields["text"] = quote(text)
                self._write_line(event, fields)
                self._records += 1
                if self._records % _ROTATE_CHECK_EVERY == 0:
                    self._check_size_locked()
            except Exception:
                # A failing log must never take speech down with it.
                try:
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None

    def _check_size_locked(self) -> None:
        try:
            if self._handle.tell() > _MAX_BYTES:
                self._handle.close()
                self._handle = None
                self._rotate_if_needed(self._path)
                self._handle = open(self._path, "a", encoding="utf-8")
                self._started = self._started  # keep the same time origin
        except Exception:
            self._handle = None

    def session_header(self, **fields) -> None:
        """Record what the speech system decided at startup.

        Without this a transcript cannot be interpreted: "nothing was spoken"
        means something very different on the Tolk path than on the SAPI one.
        """
        if self._handle is None:
            return
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            if self._handle is None:
                return
            try:
                self._handle.write("\n")
                self._write_line("SESSION-START", {"local_time": stamp})
                self._write_line("SESSION-INFO", fields)
            except Exception:
                self._handle = None


# One transcript per process.
speech_log = SpeechLog()
