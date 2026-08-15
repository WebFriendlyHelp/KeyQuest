"""Tests for the logic of modules/speech_manager.py.

All tests mock out (or bypass) the real TTS engines (pyttsx3, SAPI, Tolk)
so that no hardware, COM, or screen-reader infrastructure is required.
Tests are fast and deterministic.
"""

import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
