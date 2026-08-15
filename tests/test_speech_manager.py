"""Tests for the logic of modules/speech_manager.py.

All tests mock out (or bypass) the real TTS engines (pyttsx3, SAPI, Tolk)
so that no hardware, COM, or screen-reader infrastructure is required.
Tests are fast and deterministic.
"""

import os
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: build a Speech instance that skips all real engine initialisation.
# ---------------------------------------------------------------------------

def _make_speech_no_engine():
    """Return a Speech instance whose TTS/Tolk init is fully mocked out.

    We patch the three private init helpers at the class level so that the
    __init__ body runs to completion without touching COM, pyttsx3, or Tolk.
    """
    with (
        patch("modules.speech_manager.Speech._init_tts_engine", return_value=False),
        patch("modules.speech_manager.TOLK_AVAILABLE", False),
    ):
        from modules.speech_manager import Speech
        speech = Speech.__new__(Speech)
        # Run __init__ with the patches still active inside the with-block.
        Speech.__init__(speech)
    return speech


class TestSpeechInstantiation(unittest.TestCase):
    """Speech can be created without a real TTS engine."""

    def test_instantiation_does_not_raise(self):
        try:
            _make_speech_no_engine()
        except Exception as exc:
            self.fail(f"Speech.__init__() raised unexpectedly: {exc}")

    def test_backend_is_none_without_engine(self):
        speech = _make_speech_no_engine()
        self.assertEqual(speech.backend, "none")

    def test_enabled_defaults_to_true(self):
        speech = _make_speech_no_engine()
        self.assertTrue(speech.enabled)

    def test_last_text_starts_empty(self):
        speech = _make_speech_no_engine()
        self.assertEqual(speech._last_text, "")

    def test_last_speak_time_starts_at_zero(self):
        speech = _make_speech_no_engine()
        self.assertAlmostEqual(speech._last_speak_time, 0.0)


class TestSayDebounce(unittest.TestCase):
    """Calling say() twice with identical text within the debounce window
    results in only one actual speech call."""

    def _make_speech_with_mock_tolk(self):
        """Return a Speech with backend='tolk' and a mock tolk.speak."""
        speech = _make_speech_no_engine()
        speech.backend = "tolk"
        return speech

    def test_identical_text_within_debounce_is_dropped(self):
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            speech.say("hello")
            # Second call immediately (well within 250 ms debounce window).
            speech.say("hello")

        self.assertEqual(mock_output.call_count, 1,
                         "Duplicate text within debounce window should only speak once")

    def test_different_text_bypasses_debounce(self):
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            speech.say("hello")
            speech.say("world")

        self.assertEqual(mock_output.call_count, 2,
                         "Different text should always be spoken regardless of timing")

    def test_same_text_after_debounce_window_is_spoken_again(self):
        from modules import speech_manager as sm

        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            speech.say("hello")
            # Simulate that enough time has passed.
            speech._last_speak_time -= sm._DUPLICATE_SPEECH_DEBOUNCE_SECONDS + 0.01
            speech.say("hello")

        self.assertEqual(mock_output.call_count, 2,
                         "Same text after debounce window should be spoken again")

    def test_disabled_speech_never_speaks(self):
        speech = self._make_speech_with_mock_tolk()
        speech.enabled = False
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output
            speech.say("hello")

        mock_output.assert_not_called()

    def test_empty_text_is_ignored(self):
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output
            speech.say("")
            speech.say(None)  # type: ignore[arg-type]

        mock_output.assert_not_called()


class TestSayPriority(unittest.TestCase):
    """A priority=True call sets a protection window; a subsequent
    non-priority, non-interrupting call within that window is suppressed."""

    def _make_speech_with_mock_tolk(self):
        speech = _make_speech_no_engine()
        speech.backend = "tolk"
        return speech

    def test_priority_call_sets_priority_until(self):
        speech = self._make_speech_with_mock_tolk()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = MagicMock()
            speech.say("important", priority=True, protect_seconds=5.0)

        self.assertGreater(speech._priority_until, time.time(),
                           "_priority_until should be in the future after a priority call")

    def test_non_priority_non_interrupt_suppressed_within_protection_window(self):
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            # Establish a priority window lasting 10 seconds.
            speech.say("important", priority=True, protect_seconds=10.0)

            # Non-priority, non-interrupting call with DIFFERENT text
            # should be suppressed while the priority window is active.
            speech.say("low priority text", priority=False, interrupt=False)

        # Only the priority call should have reached tolk.output.
        self.assertEqual(mock_output.call_count, 1,
                         "Non-priority non-interrupt call should be suppressed during priority window")

    def test_priority_call_always_overrides(self):
        """A second priority=True call is never suppressed by the first."""
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            speech.say("first important", priority=True, protect_seconds=10.0)
            # Different text, so debounce does not block it.
            speech.say("second important", priority=True, protect_seconds=10.0)

        self.assertEqual(mock_output.call_count, 2,
                         "Priority calls should always be spoken")

    def test_interrupt_true_bypasses_priority_protection(self):
        """An interrupting (default) non-priority call with different text
        is NOT blocked by the priority window — only non-interrupting ones are."""
        speech = self._make_speech_with_mock_tolk()
        mock_output = MagicMock()

        with patch("modules.speech_manager.tolk") as mock_tolk:
            mock_tolk.output = mock_output

            speech.say("important", priority=True, protect_seconds=10.0)
            # interrupt=True (the default) should not be blocked.
            speech.say("normal interrupting text", priority=False, interrupt=True)

        self.assertEqual(mock_output.call_count, 2,
                         "Interrupting non-priority calls should not be blocked by priority window")


class TestShutdown(unittest.TestCase):
    """Shutdown behaviour for the explicit cleanup API."""

    def test_shutdown_does_not_raise(self):
        speech = _make_speech_no_engine()
        try:
            speech.shutdown()
        except Exception as exc:
            self.fail(f"Speech.shutdown() raised unexpectedly: {exc}")

    def test_shutdown_called_twice_does_not_raise(self):
        speech = _make_speech_no_engine()
        try:
            speech.shutdown()
            speech.shutdown()
        except Exception as exc:
            self.fail(f"Second Speech.shutdown() call raised unexpectedly: {exc}")

    def test_tts_shutdown_flag_set_after_shutdown(self):
        speech = _make_speech_no_engine()
        speech.shutdown()
        self.assertTrue(speech._tts_shutdown,
                        "_tts_shutdown should be True after shutdown()")

    def test_say_after_shutdown_does_not_raise(self):
        """Calling say() after shutdown() must not crash (e.g., if the app
        calls say() during teardown after the Speech object was cleaned up)."""
        speech = _make_speech_no_engine()
        speech.shutdown()
        try:
            speech.say("something after shutdown")
        except Exception as exc:
            self.fail(f"say() after shutdown() raised unexpectedly: {exc}")


class TestApplyMode(unittest.TestCase):
    """apply_mode() switches the enabled flag and backend correctly."""

    def test_apply_mode_off_disables_speech(self):
        speech = _make_speech_no_engine()
        speech.apply_mode("off")
        self.assertFalse(speech.enabled)

    def test_apply_mode_any_other_value_enables_speech(self):
        speech = _make_speech_no_engine()
        speech.enabled = False
        speech.apply_mode("tts")
        self.assertTrue(speech.enabled)

    def test_apply_mode_auto_with_no_backend_sets_backend_none(self):
        speech = _make_speech_no_engine()
        # No screen reader, no engine — auto should leave backend as "none".
        speech._screen_reader_detected = None
        speech._engine = None
        speech._sapi_voice = None
        with patch.object(speech, "_init_tts_engine", return_value=False):
            speech.apply_mode("auto")
        self.assertEqual(speech.backend, "none")

    def test_apply_mode_unknown_string_leaves_backend_unchanged(self):
        speech = _make_speech_no_engine()
        speech.backend = "none"
        speech.apply_mode("totally_unknown_mode")
        self.assertEqual(speech.backend, "none")


class TestThreadSafety(unittest.TestCase):
    """say() can be called concurrently without raising exceptions."""

    def test_concurrent_say_calls_do_not_raise(self):
        speech = _make_speech_no_engine()
        # backend "none" falls through to print(), which is thread-safe enough.
        errors = []

        def worker(text):
            try:
                for _ in range(20):
                    speech.say(text)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"text-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [],
                         f"Concurrent say() calls raised exceptions: {errors}")


class TestNarratorProbeDoesNotDisturbTheMainLoop(unittest.TestCase):
    """The Narrator process probe used to freeze the app and steal the keyboard.

    ``refresh_backend`` runs once per second from the pygame loop and reaches
    the Narrator check only when no screen reader was found, which is exactly
    the TTS fallback users reported as sluggish. The probe spawns ``tasklist``,
    and KeyQuest ships windowed, so a console child got its own console window,
    took the foreground, and closed again. Keystrokes made in that gap never
    reached the pygame window.
    """

    def test_probe_hides_the_console_window_it_would_otherwise_create(self):
        speech = _make_speech_no_engine()
        with patch("modules.speech_manager.subprocess.run") as run:
            run.return_value = MagicMock(stdout="")
            speech._detect_narrator_process()

        self.assertTrue(run.called, "the probe did not run tasklist at all")
        kwargs = run.call_args.kwargs
        if os.name == "nt":
            self.assertEqual(
                kwargs.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW,
                subprocess.CREATE_NO_WINDOW,
                "tasklist was spawned without CREATE_NO_WINDOW, so it will "
                "flash a console window and take the keyboard focus",
            )
            startupinfo = kwargs.get("startupinfo")
            self.assertIsNotNone(startupinfo, "no startupinfo passed to tasklist")
            self.assertTrue(startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW)
            self.assertEqual(startupinfo.wShowWindow, 0)  # SW_HIDE

    def test_every_subprocess_call_in_the_module_hides_its_window(self):
        """Invariant, so a probe added later cannot skip the guard."""
        import inspect

        import modules.speech_manager as speech_manager

        source = inspect.getsource(speech_manager)
        spawns = source.count("subprocess.run(")
        guarded = source.count("**hidden_process_kwargs()")
        self.assertEqual(
            spawns,
            guarded,
            f"{spawns} subprocess.run call(s) but only {guarded} carry "
            "hidden_process_kwargs(); an unguarded console spawn will steal "
            "keyboard focus from the pygame window",
        )

    def test_repeated_polling_does_not_spawn_a_process_each_time(self):
        """The main loop asks once a second; it must be answered from cache."""
        speech = _make_speech_no_engine()
        with patch.object(
            speech, "_detect_narrator_process", return_value=False
        ) as probe:
            for _ in range(20):
                speech.narrator_process_running()
            for thread in [speech._narrator_probe_thread]:
                if thread is not None:
                    thread.join(timeout=5)

        self.assertLessEqual(
            probe.call_count,
            1,
            f"20 polls triggered {probe.call_count} process spawns; the cache "
            "is not holding",
        )

    def test_polling_never_blocks_the_calling_thread(self):
        """A slow probe must not stall the caller, whatever tasklist costs."""
        speech = _make_speech_no_engine()
        speech._narrator_checked_at = 0.0  # force a refresh

        def slow_probe():
            time.sleep(1.0)
            return False

        with patch.object(speech, "_detect_narrator_process", side_effect=slow_probe):
            started = time.time()
            speech.narrator_process_running()
            elapsed = time.time() - started
            if speech._narrator_probe_thread is not None:
                speech._narrator_probe_thread.join(timeout=5)

        self.assertLess(
            elapsed,
            0.5,
            f"narrator_process_running blocked for {elapsed:.2f}s; the pygame "
            "loop calls this every second",
        )

    def test_refresh_backend_does_not_probe_synchronously(self):
        """The whole point: the per-second path must not spawn a process."""
        speech = _make_speech_no_engine()
        speech._narrator_checked_at = time.time()  # cache is warm
        speech._narrator_running = False

        with patch.object(speech, "_detect_narrator_process") as probe:
            for _ in range(10):
                speech.refresh_backend("auto")

        self.assertEqual(
            probe.call_count,
            0,
            "refresh_backend spawned tasklist on the main thread",
        )


class TestNativeSapiCountsAsHavingTts(unittest.TestCase):
    """With no screen reader and working SAPI, the app must not decide it is mute.

    Found by running the real app with NVDA stopped: the transcript reported
    `backend=none` while `sapi_voice` was populated and healthy. The cause is
    that `_init_sapi_voice` succeeding means pyttsx3 is never created, so every
    availability check written as `if self._engine` concluded there was no TTS
    at all, on exactly the machines where SAPI was working.
    """

    def _speech_with_sapi_only(self):
        """No Tolk, no pyttsx3, a working native SAPI voice."""
        with (
            patch("modules.speech_manager.TOLK_AVAILABLE", False),
            patch("modules.speech_manager.Speech._init_sapi_voice", autospec=True) as init,
        ):
            from modules.speech_manager import Speech

            def fake_init(self):
                self._sapi_voice = MagicMock()
                return True

            init.side_effect = fake_init
            speech = Speech.__new__(Speech)
            Speech.__init__(speech)
        return speech

    def test_backend_is_tts_at_construction(self):
        speech = self._speech_with_sapi_only()
        self.assertIsNotNone(speech._sapi_voice, "the fixture should provide SAPI")
        self.assertIsNone(speech._engine, "pyttsx3 should not be created when SAPI works")
        self.assertEqual(
            speech.backend, "tts",
            "SAPI is available, so the app must not start with no backend",
        )

    def test_has_tts_accepts_either_engine(self):
        speech = _make_speech_no_engine()
        self.assertFalse(speech._has_tts())
        speech._sapi_voice = MagicMock()
        self.assertTrue(speech._has_tts(), "native SAPI alone counts as TTS")
        speech._sapi_voice = None
        speech._engine = MagicMock()
        self.assertTrue(speech._has_tts(), "pyttsx3 alone counts as TTS")

    def test_auto_mode_selects_tts_with_sapi_only(self):
        speech = self._speech_with_sapi_only()
        speech.backend = "none"
        speech._screen_reader_detected = None
        speech.apply_mode("auto")
        self.assertEqual(speech.backend, "tts")

    def test_forced_screen_reader_mode_falls_back_to_sapi(self):
        speech = self._speech_with_sapi_only()
        speech._tolk_available = False
        speech._screen_reader_detected = None
        speech.apply_mode("screen_reader")
        self.assertEqual(
            speech.backend, "tts",
            "with no Tolk, forced screen reader mode should fall back to SAPI, not silence",
        )


class TestSapiNeverParsesSpeechAsMarkup(unittest.TestCase):
    """A practice sentence starting with "<" was spoken as nothing at all.

    SAPI's default is to parse the text as XML when, and only when, the first
    character is a left angle bracket. Sentence files are user-editable, and
    `test_modes` speaks a sentence as the whole utterance with no prefix, so
    this was reachable content rather than a theory. Proven by rendering to
    WAV: plain text gave 140,898 bytes, the same text with a leading "<" gave
    0 bytes and an "XML parser error", and SVSFIsNotXML restored it exactly.
    """

    def _speak_and_capture_flags(self, text, interrupt=True):
        speech = _make_speech_no_engine()
        speech.backend = "tts"
        speech._sapi_voice = MagicMock()
        speech._sapi_voice.Speak.return_value = 1
        speech.say(text, interrupt=interrupt)
        self.assertTrue(speech._sapi_voice.Speak.called, "SAPI was never asked to speak")
        return speech._sapi_voice.Speak.call_args.args[1]

    def test_is_not_xml_flag_value(self):
        from modules.speech_manager import _SAPI_NOT_XML_FLAG

        self.assertEqual(_SAPI_NOT_XML_FLAG, 16, "SVSFIsNotXML is 16")

    def test_every_utterance_is_marked_not_xml(self):
        from modules.speech_manager import _SAPI_NOT_XML_FLAG

        for text in [
            "<a sentence that starts with a bracket",
            "an ordinary sentence",
            "a sentence with < in the middle",
            "<",
        ]:
            for interrupt in (True, False):
                with self.subTest(text=text, interrupt=interrupt):
                    flags = self._speak_and_capture_flags(text, interrupt)
                    self.assertTrue(
                        flags & _SAPI_NOT_XML_FLAG,
                        f"{text!r} was sent to SAPI without SVSFIsNotXML, so SAPI "
                        "may parse it as markup and speak nothing",
                    )

    def test_async_and_purge_still_behave(self):
        from modules.speech_manager import (
            _SAPI_ASYNC_FLAG,
            _SAPI_PURGE_FLAG,
        )

        interrupting = self._speak_and_capture_flags("hello", interrupt=True)
        queueing = self._speak_and_capture_flags("goodbye", interrupt=False)
        self.assertTrue(interrupting & _SAPI_ASYNC_FLAG)
        self.assertTrue(interrupting & _SAPI_PURGE_FLAG)
        self.assertTrue(queueing & _SAPI_ASYNC_FLAG)
        self.assertFalse(queueing & _SAPI_PURGE_FLAG, "queued speech must not purge")


@unittest.skipUnless(os.name == "nt", "SAPI is Windows only")
class TestSapiActuallyRendersBracketText(unittest.TestCase):
    """The end-to-end proof, so the unit tests above cannot pass on a technicality.

    Renders through real SAPI to a WAV file and compares byte counts. Skips
    rather than fails when SAPI is unavailable, because absence of a voice is
    not a regression in KeyQuest.
    """

    LEADING = "<hello there this is a plain practice sentence"
    PLAIN = "hello there this is a plain practice sentence"

    def _render(self, text, flags):
        import win32com.client

        path = os.path.join(tempfile.gettempdir(), "kq_sapi_flag_test.wav")
        if os.path.exists(path):
            os.unlink(path)
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(path, 3)  # SSFMCreateForWrite
        voice.AudioOutputStream = stream
        try:
            voice.Speak(text, flags)
        finally:
            stream.Close()
        size = os.path.getsize(path)
        os.unlink(path)
        return size

    def test_leading_bracket_survives_with_the_shipped_flags(self):
        from modules.speech_manager import _SAPI_NOT_XML_FLAG

        try:
            import win32com.client  # noqa: F401
        except Exception:
            self.skipTest("pywin32 not available")

        try:
            baseline = self._render(self.PLAIN, 0)
        except Exception as exc:
            self.skipTest(f"SAPI unavailable: {exc}")

        if baseline == 0:
            self.skipTest("SAPI produced no audio even for plain text")

        rendered = self._render(self.LEADING, _SAPI_NOT_XML_FLAG)
        self.assertGreater(
            rendered, baseline * 0.9,
            "a sentence starting with '<' lost audio even with SVSFIsNotXML",
        )


if __name__ == "__main__":
    unittest.main()
