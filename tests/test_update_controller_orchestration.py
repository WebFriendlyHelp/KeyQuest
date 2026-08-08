"""Tests for the controller logic that switches between updater layers.

Both "hands" of the updater were well covered and the brain was not: nothing
anywhere drove ``_launch_downloaded_update``, ``_fallback_apply``, the
early-death poll, or the marker ordering.  Three fixes from the 2026-08 review
rounds live in exactly that code:

- a launcher-generation failure escaping instead of falling through to the
  fallback chain,
- the last-resort helper being spawned with no early-failure poll, so a bat that
  died instantly left the user with nothing running,
- the marker being written after the poll, which let the installer fallback's
  ``/FORCECLOSEAPPLICATIONS`` close the app first and lose it.

These tests drive the real controller against a stub app.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from modules import update_controller, update_manager
from modules.update_controller import AppUpdateController


class _Speech:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def say(self, text: str, **kwargs) -> None:
        self.calls.append(text)


class _App:
    def __init__(self) -> None:
        self.state = SimpleNamespace(mode="UPDATING")
        self.speech = _Speech()
        self.events: list[str] = []
        self.errors: list[str] = []
        self.recovery_calls: list[str] = []
        self.saved = 0
        self.main_menu = SimpleNamespace(announce_current=lambda: None)

    def _record_update_event(self, message: str) -> None:
        self.events.append(message)

    def _record_update_error(self, message: str, tb_str=None) -> None:
        self.errors.append(message)

    def _offer_update_failure_recovery(self, message: str, tb_str: str = "") -> None:
        self.recovery_calls.append(message)

    def save_progress(self) -> None:
        self.saved += 1


class _Proc:
    """Stand-in for the spawned helper: ``rc`` None means still running."""

    def __init__(self, rc):
        self._rc = rc
        self.returncode = rc

    def poll(self):
        return self._rc


def _controller(app_dir: Path, *, portable: bool = False) -> AppUpdateController:
    controller = AppUpdateController.__new__(AppUpdateController)
    controller.app = _App()
    controller._portable_update_mode = portable
    controller._update_status = ""
    controller._update_error_message = ""
    controller._rollback_backup_zip = None
    return controller


class TestLauncherGenerationFailureFallsThrough(unittest.TestCase):
    def test_bat_write_failure_reaches_the_fallback_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            with mock.patch.object(update_controller, "get_app_dir", return_value=tmp), \
                 mock.patch.object(
                     update_manager, "create_update_launcher",
                     side_effect=update_manager.UpdateError("staging dir unwritable")), \
                 mock.patch.object(controller, "_fallback_run_update_direct") as fallback:
                controller._launch_downloaded_update(str(Path(tmp) / "Setup.exe"), "9.9.9")

            fallback.assert_called_once()
            self.assertTrue(
                any("Could not prepare the update launcher" in e for e in controller.app.errors),
                "the failure should be recorded, not swallowed",
            )


class TestFallbackEarlyDeathPoll(unittest.TestCase):
    """The last-resort helper must be watched before the app commits to exiting."""

    def _run_fallback(self, tmp: str, rc):
        controller = _controller(Path(tmp))
        bat = Path(tmp) / "fallback.bat"
        bat.write_text("@echo off\r\n", encoding="ascii", newline="")
        with mock.patch.object(update_controller, "get_app_dir", return_value=tmp), \
             mock.patch.object(update_manager, "create_installer_fallback_bat", return_value=bat), \
             mock.patch.object(update_controller.subprocess, "Popen", return_value=_Proc(rc)), \
             mock.patch.object(update_controller.pygame.time, "wait"), \
             mock.patch.object(update_controller.pygame, "quit"), \
             mock.patch.object(update_controller.time, "monotonic", side_effect=[0.0, 0.1, 10.0] * 40), \
             mock.patch.object(update_controller.time, "sleep"):
            raised = None
            try:
                controller._fallback_apply(Path(tmp) / "Setup.exe", "9.9.9")
            except SystemExit as exc:
                raised = exc
        return controller, raised

    def test_helper_dying_nonzero_is_treated_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller, raised = self._run_fallback(tmp, rc=1)

            self.assertIsNone(raised, "the app must NOT exit when the helper died")
            self.assertEqual(controller.app.state.mode, "MENU")
            self.assertTrue(
                any("manually" in c for c in controller.app.speech.calls),
                "the user must be told to update manually",
            )
            self.assertFalse(
                (Path(tmp) / "pending_update.json").exists(),
                "a stale marker would make the next launch announce a failure that "
                "never happened, since the app is still running",
            )

    def test_helper_finishing_cleanly_is_not_treated_as_failure(self) -> None:
        # The installer fallback waits ~3s then runs Inno, so it can legitimately
        # complete inside the 4s poll. Treating that as failure deleted the
        # marker for an update that had actually applied.
        with tempfile.TemporaryDirectory() as tmp:
            controller, raised = self._run_fallback(tmp, rc=0)

            self.assertIsInstance(raised, SystemExit)
            self.assertNotEqual(controller.app.state.mode, "MENU")
            self.assertTrue(
                (Path(tmp) / "pending_update.json").exists(),
                "the marker must survive: the update may well have applied",
            )

    def test_marker_and_progress_are_saved_before_the_helper_starts(self) -> None:
        # Ordering matters because the installer fallback can close the app.
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            bat = Path(tmp) / "fallback.bat"
            bat.write_text("@echo off\r\n", encoding="ascii", newline="")
            order: list[str] = []

            def record_popen(*args, **kwargs):
                order.append("spawn")
                return _Proc(None)

            original_write = update_manager.write_pending_update_marker

            def record_marker(app_dir, version):
                order.append("marker")
                return original_write(app_dir, version)

            with mock.patch.object(update_controller, "get_app_dir", return_value=tmp), \
                 mock.patch.object(update_manager, "create_installer_fallback_bat", return_value=bat), \
                 mock.patch.object(update_manager, "write_pending_update_marker", side_effect=record_marker), \
                 mock.patch.object(update_controller.subprocess, "Popen", side_effect=record_popen), \
                 mock.patch.object(update_controller.pygame.time, "wait"), \
                 mock.patch.object(update_controller.pygame, "quit"), \
                 mock.patch.object(update_controller.time, "monotonic", side_effect=[0.0, 10.0] * 40), \
                 mock.patch.object(update_controller.time, "sleep"):
                try:
                    controller._fallback_apply(Path(tmp) / "Setup.exe", "9.9.9")
                except SystemExit:
                    pass

            self.assertEqual(
                order[:2], ["marker", "spawn"],
                "the marker must be written before the helper can close the app",
            )
            self.assertGreaterEqual(controller.app.saved, 1, "progress must be saved too")


class TestMarkerWriteFailureIsSpoken(unittest.TestCase):
    def test_user_is_told_when_the_marker_cannot_be_written(self) -> None:
        # A local log entry is no use to a blind user; if the update then fails
        # silently, nothing else will tell them.
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            with mock.patch.object(update_controller, "get_app_dir", return_value=tmp), \
                 mock.patch.object(update_manager, "write_pending_update_marker", return_value=False):
                ok = controller._write_marker_or_warn("9.9.9")

            self.assertFalse(ok)
            self.assertTrue(controller.app.errors, "the failure must be recorded")
            self.assertTrue(
                any("update check file" in c for c in controller.app.speech.calls),
                "the failure must be spoken, not only logged",
            )


class TestProductionSpawnFlags(unittest.TestCase):
    """The historic freeze came from the wrong creation flags."""

    def test_fallback_spawn_uses_the_hidden_console_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            bat = Path(tmp) / "fallback.bat"
            bat.write_text("@echo off\r\n", encoding="ascii", newline="")
            captured: dict = {}

            def capture(*args, **kwargs):
                captured.update(kwargs)
                captured["command"] = args[0] if args else None
                return _Proc(None)

            with mock.patch.object(update_controller, "get_app_dir", return_value=tmp), \
                 mock.patch.object(update_manager, "create_installer_fallback_bat", return_value=bat), \
                 mock.patch.object(update_controller.subprocess, "Popen", side_effect=capture), \
                 mock.patch.object(update_controller.pygame.time, "wait"), \
                 mock.patch.object(update_controller.pygame, "quit"), \
                 mock.patch.object(update_controller.time, "monotonic", side_effect=[0.0, 10.0] * 40), \
                 mock.patch.object(update_controller.time, "sleep"):
                try:
                    controller._fallback_apply(Path(tmp) / "Setup.exe", "9.9.9")
                except SystemExit:
                    pass

            flags = captured.get("creationflags")
            self.assertEqual(flags, update_controller.bat_launcher_creationflags())
            self.assertFalse(
                flags & getattr(subprocess, "DETACHED_PROCESS", 0),
                "DETACHED_PROCESS gives the helper no console, which is what made "
                "the wait loop's find.exe hang forever",
            )
            self.assertIn("/s /c", str(captured.get("command")))


if __name__ == "__main__":
    unittest.main()
