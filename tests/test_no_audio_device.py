"""KeyQuest must start on a machine with no sound device.

On a Windows machine with no audio endpoint, pygame.mixer.init() raises
"WASAPI can't find requested audio endpoint: Element not found." and KeyQuest
died at startup with "Unexpected KeyQuest Error", never reaching the menu.
Found 2026-10-18 on a fresh Hyper-V guest, which has no sound card.

The child process below builds the real KeyQuestApp with SDL pointed at an audio
driver that does not exist, so the real mixer.init() fails inside real pygame.
That proves KeyQuest's own handling of the failure; it does not prove what a
missing WASAPI endpoint does, which was checked on the VM.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = textwrap.dedent(
    """
    import os, sys
    sys.path.insert(0, sys.argv[1])
    from modules import error_logging
    error_logging.get_log_file_path = lambda: sys.argv[2]
    import pygame
    from modules import keyquest_app
    app = keyquest_app.KeyQuestApp()
    print("MIXER", pygame.mixer.get_init())
    print("MODE", app.state.mode)
    app.speech.shutdown()
    pygame.quit()
    """
)


def _start_app(audio_driver: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = audio_driver
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "keyquest_error.log")
        return subprocess.run(
            [sys.executable, "-c", CHILD, str(ROOT), log],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )


def test_starts_at_menu_when_no_audio_device_exists():
    result = _start_app("keyquest_no_such_audio_driver")
    assert result.returncode == 0, result.stderr[-2000:]
    assert "MIXER None" in result.stdout, result.stdout
    assert "MODE MENU" in result.stdout, result.stdout


def test_control_mixer_does_start_with_a_working_driver():
    # The negative twin: with an audio driver that exists, the mixer is up.
    # Without this, "MIXER None" above could be true for some other reason.
    result = _start_app("dummy")
    assert result.returncode == 0, result.stderr[-2000:]
    assert "MIXER (" in result.stdout, result.stdout
    assert "MODE MENU" in result.stdout, result.stdout
