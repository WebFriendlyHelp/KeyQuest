import os
import re
import subprocess
import threading
import time
import traceback

from modules import speech_log as speech_log_module
from modules.speech_log import quote as _quote_for_log, speech_log

# Matches emoji and other non-BMP Unicode that screen readers may mispronounce.
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # geometric
    "\U0001F800-\U0001F8FF"  # supplemental arrows
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess / other
    "\U0001FA70-\U0001FAFF"  # other symbols
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


LOG_FILE = "keyquest_error.log"
_DUPLICATE_SPEECH_DEBOUNCE_SECONDS = 0.25
_SAPI_ASYNC_FLAG = 1
_SAPI_PURGE_FLAG = 2
# SVSFIsNotXML. Without it SAPI uses SVSFDefault, which parses the text as XML
# when, and only when, the FIRST character is a left angle bracket. A practice
# sentence beginning with "<" therefore went to the XML parser, failed to parse,
# and raised, so the user was told to type a sentence they never heard. Measured
# by rendering to WAV: plain text produced 140,898 bytes, the same text with a
# leading "<" produced 0 bytes and an "XML parser error", and with this flag it
# produced 140,898 bytes again. A "<" anywhere other than the first character
# was never affected, which is exactly what made this rare enough to survive.
# Sentence files are user-editable, so this is reachable content, not a theory.
_SAPI_NOT_XML_FLAG = 16

# How stale a Narrator-process answer may be before it is refreshed. Narrator
# starting mid-session is noticed within this window rather than within a second.
_NARRATOR_POLL_SECONDS = 5.0


def hidden_process_kwargs() -> dict:
    """Subprocess keyword arguments that keep a console child from showing a window.

    KeyQuest ships windowed (``console=False`` in the PyInstaller spec, and
    ``keyquest.pyw`` runs under pythonw), so the app owns no console. A console
    program launched from a parent with no console gets a brand new console
    window of its own: it appears, TAKES THE FOREGROUND, and closes again.
    Measured on Windows 11, four bare ``tasklist`` spawns from a pythonw parent
    produced four different foreground windows plus a moment with no foreground
    window at all, while the same spawns with these flags never moved the
    foreground once. Keystrokes made during those moments never reach the pygame
    window, because SDL only delivers keyboard input to the focused window.

    ``update_manager._run_powershell`` and ``update_controller`` already do this;
    this is the same guard for the speech module's own process probe.
    """
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def log_exception(e: BaseException):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write("=== Unhandled exception ===\n")
            traceback.print_exc(file=file)
            file.write("\n")
    except Exception:
        pass


try:
    from cytolk import tolk

    TOLK_AVAILABLE = True
except Exception:
    tolk = None
    TOLK_AVAILABLE = False

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import win32com.client
except Exception:
    win32com = None


class Speech:
    """Speech system with intelligent screen reader detection and TTS fallback."""

    def __init__(self):
        print("Speech.__init__() starting...")
        self.enabled = True
        self._lock = threading.Lock()
        self._engine = None
        self._sapi_voice = None
        self._tts_backend = "none"
        self._voice_query_failed = False
        self._tts_pending_text = None
        self._tts_pending_interrupt = True
        self._tts_event = threading.Event()
        self._tts_shutdown = False
        self._tts_thread = None
        self._tts_queue_lock = threading.Lock()
        self._tolk_loaded = False
        self._tolk_available = False
        self._screen_reader_detected = None
        self._narrator_running = False
        self._narrator_checked_at = 0.0
        self._narrator_probe_thread = None
        self._narrator_lock = threading.Lock()
        self.backend = "none"
        self._priority_until = 0.0
        self._last_text = ""
        self._last_speak_time = 0.0
        self.tts_rate = 200
        self.tts_volume = 1.0
        self.tts_voice_id = ""
        print("Speech basic init complete")

        # Initialize TTS before Tolk to avoid COM apartment conflicts on Windows.
        self._init_tts_engine()

        if TOLK_AVAILABLE:
            print("Trying Tolk...")
            try:
                tolk.load()
                self._tolk_available = True
                self._screen_reader_detected = tolk.detect_screen_reader()
                print(
                    f"Tolk loaded - Screen reader detected: {self._screen_reader_detected or 'None'}"
                )

                # Startup can afford the blocking probe once; the per-second
                # check in refresh_backend cannot, so it reads the cache.
                if not self._screen_reader_detected and self._refresh_narrator_flag():
                    self._screen_reader_detected = "Narrator"

                if self._screen_reader_detected and self._screen_reader_detected != "Narrator":
                    self._tolk_loaded = True
                    self.backend = "tolk"
                    print(f"Using screen reader: {self._screen_reader_detected}")
                    try:
                        _has_speech = tolk.has_speech()
                        _has_braille = tolk.has_braille()
                        try:
                            with open(LOG_FILE, "a", encoding="utf-8") as _f:
                                _f.write(
                                    f"Tolk capabilities - speech: {_has_speech}, braille: {_has_braille}\n"
                                )
                        except Exception:
                            pass
                    except Exception:
                        pass
                elif self._engine is not None:
                    self.backend = "tts"
                    print("No screen reader detected, will use TTS")
                else:
                    print("No screen reader detected, and TTS unavailable")
            except Exception as e:
                print(f"Tolk failed: {e}")
                traceback.print_exc()
                if self._engine is not None and self.backend == "none":
                    self.backend = "tts"

        if self.backend == "none" and self._engine is not None:
            self.backend = "tts"

        print(f"Speech initialized with backend: {self.backend}")

        # The environment switch is read here so a transcript covers startup
        # too. The settings toggle can only turn it on once settings are loaded,
        # which is already several announcements in.
        if speech_log_module.env_requested():
            self.set_logging(True)

    def set_logging(self, on: bool) -> bool:
        """Turn the speech transcript on or off. Returns whether it is now on."""
        if on:
            if not speech_log.enable():
                return False
            speech_log.session_header(**self.describe_for_log())
            return True
        speech_log.disable()
        return False

    @property
    def logging_enabled(self) -> bool:
        return speech_log.enabled

    @property
    def log_path(self) -> str:
        return speech_log.path or speech_log_module.get_log_path()

    def _detect_narrator_process(self) -> bool:
        """Return True when the Windows Narrator process appears to be running.

        Blocking: it spawns a process. Only call this from startup or from the
        background probe, never from the main loop.
        """
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Narrator.exe"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
                **hidden_process_kwargs(),
            )
            return "Narrator.exe" in result.stdout
        except Exception:
            return False

    def _refresh_narrator_flag(self) -> bool:
        """Run the blocking probe and store the result. Returns what it found."""
        running = self._detect_narrator_process()
        with self._narrator_lock:
            self._narrator_running = running
            self._narrator_checked_at = time.time()
        return running

    def narrator_process_running(self) -> bool:
        """Return the cached Narrator answer, refreshing it off the main thread.

        ``refresh_backend`` runs once per second from the pygame loop, and only
        reaches the Narrator check when no screen reader was detected -- exactly
        the TTS fallback case users reported as sluggish and intermittently
        deaf to keypresses. Spawning ``tasklist`` there stalled the loop for as
        long as the spawn took and stole the keyboard focus with it. Answering
        from cache keeps the loop free; a worker refreshes the cache.
        """
        now = time.time()
        with self._narrator_lock:
            probe_in_flight = (
                self._narrator_probe_thread is not None
                and self._narrator_probe_thread.is_alive()
            )
            if probe_in_flight or (now - self._narrator_checked_at) < _NARRATOR_POLL_SECONDS:
                return self._narrator_running
            thread = threading.Thread(target=self._refresh_narrator_flag, daemon=True)
            self._narrator_probe_thread = thread
            cached = self._narrator_running

        thread.start()
        return cached

    def _init_tts_engine(self) -> bool:
        """Initialize TTS backend (prefer native SAPI on Windows)."""
        if self._init_sapi_voice():
            self._tts_backend = "sapi"
            return True
        self._tts_backend = "pyttsx3"
        return self._init_pyttsx3_engine()

    def _init_sapi_voice(self) -> bool:
        """Initialize native SAPI voice if available."""
        if self._sapi_voice is not None:
            return True
        if win32com is None:
            return False

        print("Initializing SAPI voice...")
        try:
            self._sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
            print("SAPI voice initialized successfully")
            return True
        except Exception as e:
            print(f"SAPI init failed: {e}")
            traceback.print_exc()
            self._sapi_voice = None
            return False

    def _init_pyttsx3_engine(self) -> bool:
        """Initialize pyttsx3 engine if available."""
        if pyttsx3 is None:
            return False
        if self._engine is not None:
            return True

        print("Initializing pyttsx3...")
        try:
            self._engine = pyttsx3.init()
            self._voice_query_failed = False
            self._start_tts_worker()
            print("pyttsx3 initialized successfully")
            return True
        except Exception as e:
            print(f"pyttsx3 failed: {e}")
            traceback.print_exc()
            self._engine = None
            return False

    def _start_tts_worker(self) -> None:
        """Start background TTS worker thread if needed."""
        if self._tts_thread and self._tts_thread.is_alive():
            return

        self._tts_shutdown = False
        self._tts_thread = threading.Thread(target=self._tts_worker_loop, daemon=True)
        self._tts_thread.start()

    def _tts_worker_loop(self) -> None:
        """Process queued TTS speech requests without blocking the main loop."""
        while not self._tts_shutdown:
            self._tts_event.wait(timeout=0.1)
            if self._tts_shutdown:
                break
            if not self._tts_event.is_set():
                continue
            self._tts_event.clear()

            while True:
                with self._tts_queue_lock:
                    text = self._tts_pending_text
                    interrupt = self._tts_pending_interrupt
                    self._tts_pending_text = None
                if not text:
                    break
                if self._engine is None and not self._init_tts_engine():
                    break
                try:
                    if interrupt:
                        self._engine.stop()
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e:
                    log_exception(e)
                    self._engine = None
                    if not self._init_tts_engine():
                        break

    def say(
        self,
        text: str,
        priority: bool = False,
        protect_seconds: float = 0.0,
        interrupt: bool = True,
    ):
        # Every early return below is a silent drop by design. A user cannot
        # tell one from an announcement that was never requested, so each is
        # recorded with its reason when the transcript is on.
        flags_for_log = {"pri": int(priority), "int": int(interrupt)}

        if not self.enabled:
            speech_log.record("DROPPED", text, reason="speech-disabled", **flags_for_log)
            return
        if not text:
            return
        text = _EMOJI_RE.sub("", text).strip()
        if not text:
            speech_log.record("DROPPED", "", reason="empty-after-emoji-strip")
            return
        with self._lock:
            now = time.time()
            # Drop rapid duplicate text to reduce screen reader stutter.
            if (
                text == self._last_text
                and (now - self._last_speak_time) < _DUPLICATE_SPEECH_DEBOUNCE_SECONDS
            ):
                speech_log.record(
                    "DROPPED", text, reason="duplicate-within-debounce",
                    since_ms=round((now - self._last_speak_time) * 1000, 1),
                    **flags_for_log,
                )
                return

            self._last_text = text
            self._last_speak_time = now
            if priority:
                self._priority_until = now + protect_seconds
            else:
                # Keep protection for non-interrupting speech only, so user navigation
                # can always interrupt and hear the next focused item.
                if now < self._priority_until and not interrupt:
                    speech_log.record(
                        "DROPPED", text, reason="priority-window-protecting",
                        window_ms_left=round((self._priority_until - now) * 1000, 1),
                        **flags_for_log,
                    )
                    return
            started = time.perf_counter()
            try:
                if self.backend == "tolk":
                    tolk.output(text, interrupt=interrupt)
                    self._log_spoken("tolk", text, started, flags_for_log)
                elif self.backend == "tts":
                    if self._sapi_voice is None and self._engine is None and not self._init_tts_engine():
                        speech_log.record(
                            "DROPPED", text, reason="no-tts-engine", **flags_for_log
                        )
                        return
                    if self._sapi_voice is not None:
                        flags = (
                            _SAPI_ASYNC_FLAG
                            | _SAPI_NOT_XML_FLAG
                            | (_SAPI_PURGE_FLAG if interrupt else 0)
                        )
                        # Async, so this should return in microseconds. If it
                        # ever does not, the elapsed time in the log says so.
                        stream = self._sapi_voice.Speak(text, flags)
                        self._log_spoken(
                            "sapi", text, started, flags_for_log,
                            sapi_flags=flags, stream=stream,
                        )
                    else:
                        with self._tts_queue_lock:
                            self._tts_pending_text = text
                            self._tts_pending_interrupt = interrupt
                        # Best-effort immediate cut-off for currently playing utterance.
                        if interrupt:
                            try:
                                self._engine.stop()
                            except Exception:
                                pass
                        self._tts_event.set()
                        self._log_spoken("pyttsx3", text, started, flags_for_log)
                else:
                    print(text)
                    speech_log.record(
                        "DROPPED", text, reason="no-backend", **flags_for_log
                    )
            except Exception as e:
                speech_log.record(
                    "ERROR", text, backend=self.backend,
                    error=type(e).__name__, detail=_quote_for_log(e),
                    sapi_hresult=self._sapi_last_hresult(), **flags_for_log,
                )
                log_exception(e)

    def _sapi_last_hresult(self):
        """SAPI's own last error code, where a silent failure reports itself.

        Worth capturing because the interesting SAPI failures are device-level
        and do not necessarily raise: SPERR_DEVICE_BUSY 0x80045006,
        SPERR_DEVICE_NOT_SUPPORTED 0x80045007, SPERR_DEVICE_NOT_ENABLED
        0x80045008, SPERR_NO_DRIVER 0x80045009.
        """
        if self._sapi_voice is None:
            return None
        try:
            value = self._sapi_voice.Status.LastHResult
        except Exception:
            return None
        return value if value == 0 else hex(value & 0xFFFFFFFF)

    @staticmethod
    def _log_spoken(backend: str, text: str, started: float, flags: dict, **extra) -> None:
        """Record a delivered utterance and how long handing it over took."""
        speech_log.record(
            "SPOKE", text, backend=backend,
            ms=round((time.perf_counter() - started) * 1000, 2),
            **flags, **extra,
        )

    def describe_for_log(self) -> dict:
        """Backend state worth knowing before reading a transcript.

        "Nothing was spoken" means something completely different on the Tolk
        path than on the SAPI one, so a transcript without this is guesswork.
        """
        info = {
            "backend": self.backend,
            "screen_reader": self._screen_reader_detected or "none",
            "tolk_available": int(self._tolk_available),
            "tts_backend": self._tts_backend,
            "enabled": int(self.enabled),
        }
        if self._screen_reader_detected == "Narrator":
            # Stated outright, because it is the one case where a reader of the
            # transcript would otherwise expect screen reader output and find
            # only SAPI lines. Tolk does not expose Narrator, so KeyQuest never
            # speaks through it and there is nothing Narrator-side to record.
            info["note"] = _quote_for_log(
                "Narrator is running but Tolk does not expose it, so KeyQuest "
                "speaks through SAPI instead. Every line below is KeyQuest's "
                "own speech, not Narrator's."
            )
        if self._sapi_voice is not None:
            try:
                info["sapi_voice"] = _quote_for_log(
                    self._sapi_voice.Voice.GetDescription()
                )
                info["sapi_rate"] = self._sapi_voice.Rate
                info["sapi_volume"] = self._sapi_voice.Volume
            except Exception as e:
                info["sapi_query_error"] = type(e).__name__
        return info

    def apply_mode(self, mode: str):
        """Apply a speech mode and switch backends accordingly.

        Modes: off | auto | screen_reader | tts
        """
        mode = (mode or "").strip().lower()

        if mode == "off":
            self.enabled = False
            return

        self.enabled = True

        if mode == "auto":
            if self._screen_reader_detected and self._screen_reader_detected != "Narrator":
                self.backend = "tolk"
                self._tolk_loaded = True
                print(f"Auto mode: Using screen reader ({self._screen_reader_detected})")
            elif self._engine:
                self.backend = "tts"
                print("Auto mode: Using TTS (no screen reader detected)")
            else:
                self.backend = "none"
                print("Auto mode: No speech backend available")
            return

        if mode == "screen_reader":
            if self._screen_reader_detected == "Narrator" and (self._sapi_voice or self._engine or self._init_tts_engine()):
                self.backend = "tts"
                self.say("Narrator detected. Using built-in speech because Narrator is not exposed through Tolk.")
            elif self._tolk_available:
                self.backend = "tolk"
                self._tolk_loaded = True
                if not self._screen_reader_detected:
                    self.say(
                        "Screen reader mode selected, but no screen reader detected. Speech may not work."
                    )
                print("Forced screen reader mode")
            else:
                if self._engine:
                    self.backend = "tts"
                else:
                    self.backend = "none"
                self.say("Screen reader mode selected, but Tolk library not available. Using TTS.")
            return

        if mode == "tts":
            if self._sapi_voice or self._engine or self._init_tts_engine():
                self.backend = "tts"
                print("Forced TTS mode")
            else:
                if self._tolk_available:
                    self.backend = "tolk"
                    self._tolk_loaded = True
                else:
                    self.backend = "none"
                self.say("TTS mode selected, but TTS engine not available.")
            return

        print(f"Unknown speech mode '{mode}', leaving backend unchanged ({self.backend})")

    def refresh_backend(self, mode: str) -> bool:
        """Refresh backend selection at runtime.

        Returns:
            True if backend changed, False otherwise.
        """
        mode = (mode or "").strip().lower()
        if mode == "off":
            self.enabled = False
            return False

        self.enabled = True
        if mode != "auto":
            return False

        previous_backend = self.backend
        detected_reader = None

        if self._tolk_available:
            try:
                detected_reader = tolk.detect_screen_reader()
            except Exception as e:
                log_exception(e)
                detected_reader = None

        # Cached, and refreshed on a worker: this runs every second from the
        # main loop whenever no screen reader is present.
        if not detected_reader and self.narrator_process_running():
            detected_reader = "Narrator"

        self._screen_reader_detected = detected_reader

        if detected_reader and detected_reader != "Narrator":
            self.backend = "tolk"
            self._tolk_loaded = True
        elif self._sapi_voice or self._engine or self._init_tts_engine():
            self.backend = "tts"
        else:
            self.backend = "none"

        return self.backend != previous_backend

    def get_available_voices(self):
        """Get list of available TTS voices.

        Returns:
            List of tuples: (voice_id, voice_name) or empty list if TTS unavailable
        """
        if self._sapi_voice is not None:
            try:
                token_collection = self._sapi_voice.GetVoices()
                return [(token.Id, token.GetDescription()) for token in token_collection]
            except Exception as e:
                log_exception(e)
                return []
        if not self._engine:
            return []
        if self._voice_query_failed:
            return []
        try:
            voices = self._engine.getProperty("voices")
            return [(voice.id, voice.name) for voice in voices]
        except Exception as e:
            self._voice_query_failed = True
            log_exception(e)
            return []

    def apply_tts_settings(self, rate: int = 200, volume: float = 1.0, voice_id: str = ""):
        """Apply TTS settings to pyttsx3 engine.

        Args:
            rate: Words per minute (50-400, default 200)
            volume: Volume level (0.0-1.0, default 1.0)
            voice_id: Voice ID to use (empty string = default)
        """
        if self._sapi_voice is None and self._engine is None:
            if not self._init_tts_engine():
                print("TTS engine not available")
                return

        try:
            rate = max(50, min(400, rate))
            volume = max(0.0, min(1.0, volume))
            self.tts_rate = rate
            self.tts_volume = volume
            self.tts_voice_id = voice_id

            if self._sapi_voice is not None:
                sapi_rate = int((rate - 200) / 20)
                sapi_rate = max(-10, min(10, sapi_rate))
                self._sapi_voice.Rate = sapi_rate
                self._sapi_voice.Volume = int(volume * 100)
                print(f"SAPI rate set to {sapi_rate} (from {rate} WPM)")
                print(f"SAPI volume set to {int(volume * 100)}%")
                if voice_id:
                    voices = self._sapi_voice.GetVoices()
                    matched = False
                    for token in voices:
                        if token.Id == voice_id:
                            self._sapi_voice.Voice = token
                            matched = True
                            print(f"SAPI voice set to {voice_id}")
                            break
                    if not matched:
                        print(f"Voice ID {voice_id} not found, using default")
            else:
                self._engine.setProperty("rate", rate)
                print(f"TTS rate set to {rate} WPM")
                self._engine.setProperty("volume", volume)
                print(f"TTS volume set to {volume}")

                if voice_id:
                    if self._voice_query_failed:
                        self._engine.setProperty("voice", voice_id)
                        print(f"TTS voice set to {voice_id}")
                    else:
                        voices = self._engine.getProperty("voices")
                        valid_ids = [v.id for v in voices]
                        if voice_id in valid_ids:
                            self._engine.setProperty("voice", voice_id)
                            print(f"TTS voice set to {voice_id}")
                        else:
                            print(f"Voice ID {voice_id} not found, using default")
        except Exception as e:
            if "voice" in str(e).lower():
                self._voice_query_failed = True
            print(f"Error applying TTS settings: {e}")
            log_exception(e)

    def shutdown(self):
        """Clean up speech resources. Call explicitly on app exit."""
        self._tts_shutdown = True
        self._tts_event.set()
        if self._tolk_available:
            try:
                tolk.unload()
            except Exception:
                pass
