"""Tests for the opt-in speech transcript.

The transcript exists to answer "why did it go quiet", so the tests that matter
most are the ones about DROPPED events. Every early return in Speech.say is a
silent drop by design, and a user cannot tell one from an announcement that was
never requested.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from modules import speech_log as speech_log_module
from modules.speech_log import SpeechLog


def _make_speech_no_engine():
    """A Speech instance with no real TTS, Tolk, or COM behind it."""
    with (
        patch("modules.speech_manager.Speech._init_tts_engine", return_value=False),
        patch("modules.speech_manager.TOLK_AVAILABLE", False),
    ):
        from modules.speech_manager import Speech

        speech = Speech.__new__(Speech)
        Speech.__init__(speech)
    return speech


class TempLog:
    """A SpeechLog writing to a throwaway file, installed over the singleton."""

    def __enter__(self):
        handle, self.path = tempfile.mkstemp(suffix="-speech.log")
        os.close(handle)
        os.unlink(self.path)
        self.log = SpeechLog()
        self.log.enable(self.path)
        self._patches = [
            patch("modules.speech_manager.speech_log", self.log),
            patch("modules.speech_log.speech_log", self.log),
        ]
        for item in self._patches:
            item.start()
        return self

    def __exit__(self, *_exc):
        for item in self._patches:
            item.stop()
        self.log.disable()
        try:
            os.unlink(self.path)
        except OSError:
            pass
        return False

    def text(self) -> str:
        with open(self.path, encoding="utf-8") as handle:
            return handle.read()

    def events(self, name: str) -> list[str]:
        return [line for line in self.text().splitlines() if f" {name} " in f" {line} "]

    def drops(self, reason: str) -> list[str]:
        """Drops for one specific reason.

        Filtered rather than counted, because a backend of "none" also records
        a no-backend drop for every call, and conflating the two would make
        these assertions depend on which backend the fixture happened to pick.
        """
        return [line for line in self.events("DROPPED") if f"reason={reason} " in line + " "]


class TestDisabledByDefault(unittest.TestCase):
    def test_a_fresh_log_writes_nothing(self):
        log = SpeechLog()
        self.assertFalse(log.enabled)
        log.record("SPOKE", "hello")  # must not raise, must not create a file
        log.session_header(backend="none")

    def test_speech_works_with_logging_off(self):
        speech = _make_speech_no_engine()
        speech.say("hello")  # backend "none" prints; no transcript involved

    def test_env_flag_parsing(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {speech_log_module.ENV_FLAG: value}):
                    self.assertTrue(speech_log_module.env_requested())
        for value in ("", "0", "false", "no", "off"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {speech_log_module.ENV_FLAG: value}):
                    self.assertFalse(speech_log_module.env_requested())


class TestSilentDropsAreRecorded(unittest.TestCase):
    """The reason the transcript exists."""

    def test_duplicate_within_debounce(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            speech.say("Lessons")
            speech.say("Lessons")
            drops = temp.drops("duplicate-within-debounce")
            body = temp.text()
        self.assertEqual(len(drops), 1, body)
        self.assertIn('text="Lessons"', drops[0])
        self.assertIn("since_ms=", drops[0])

    def test_priority_window_swallowing_a_non_interrupting_line(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            speech.say("Loading", priority=True, protect_seconds=5.0)
            speech.say("25 percent.", interrupt=False)
            drops = temp.drops("priority-window-protecting")
            body = temp.text()
        self.assertEqual(len(drops), 1, body)
        self.assertIn('text="25 percent."', drops[0])
        self.assertIn("window_ms_left=", drops[0])

    def test_speech_disabled(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            speech.enabled = False
            speech.say("nobody hears this")
            drops = temp.drops("speech-disabled")
            body = temp.text()
        self.assertEqual(len(drops), 1, body)

    def test_text_that_is_only_emoji(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            speech.say("\U0001F600")
            drops = temp.drops("empty-after-emoji-strip")
            body = temp.text()
        self.assertEqual(len(drops), 1, body)


class TestTranscriptShape(unittest.TestCase):
    def test_every_record_is_exactly_one_line(self):
        """A multi-line announcement must not become multiple log entries."""
        with TempLog() as temp:
            temp.log.record("SPOKE", "line one\nline two\r\nline three\ttabbed")
            body = temp.text()
        payload = [line for line in body.splitlines() if "SPOKE" in line]
        self.assertEqual(len(payload), 1, body)
        self.assertIn("\\n", payload[0])
        self.assertIn("\\t", payload[0])

    def test_quotes_and_backslashes_survive(self):
        with TempLog() as temp:
            temp.log.record("SPOKE", 'she said "hi" \\ then left')
            line = temp.events("SPOKE")[0]
        self.assertIn('\\"hi\\"', line)
        self.assertIn("\\\\", line)

    def test_session_header_names_the_backend(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            temp.log.session_header(**speech.describe_for_log())
            body = temp.text()
        self.assertIn("SESSION-INFO", body)
        self.assertIn("backend=", body)
        self.assertIn("screen_reader=", body)


class TestLoggingNeverBreaksSpeech(unittest.TestCase):
    """A diagnostic that can take the app down is worse than no diagnostic."""

    def test_a_failing_write_does_not_raise_and_disables_itself(self):
        log = SpeechLog()
        handle, path = tempfile.mkstemp(suffix="-speech.log")
        os.close(handle)
        log.enable(path)

        class Exploding:
            def write(self, *_a):
                raise OSError("disk full")

            def flush(self):
                pass

            def close(self):
                pass

        log._handle = Exploding()
        log.record("SPOKE", "this write fails")  # must not raise
        self.assertFalse(log.enabled, "a failing log should switch itself off")
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_say_still_speaks_when_the_log_is_broken(self):
        with TempLog() as temp:
            speech = _make_speech_no_engine()
            spoken = []
            speech.backend = "tolk"
            with patch("modules.speech_manager.tolk") as tolk:
                tolk.output.side_effect = lambda text, interrupt=True: spoken.append(text)
                temp.log._handle = None  # log goes away mid-session
                speech.say("still speaks")
        self.assertEqual(spoken, ["still speaks"])

    def test_enable_on_an_unwritable_path_reports_failure(self):
        log = SpeechLog()
        self.assertFalse(log.enable(os.path.join("Z:\\", "nope", "speech.log")))
        self.assertFalse(log.enabled)


if __name__ == "__main__":
    unittest.main()
