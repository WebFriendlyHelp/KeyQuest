"""Tests that a failed update *check* only interrupts the user when they asked.

A background check fires every few hours regardless of what the user is doing.
Before this was fixed, any background check error forced ``state.mode`` to
``MENU``, spoke over whatever was happening, and ran the full recovery flow
(which copies the error log to the clipboard and opens a modal dialog).  A user
playing offline was pulled out of their game every four hours.
"""

import unittest
from types import SimpleNamespace

from modules.update_controller import AppUpdateController


class _Speech:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def say(self, text: str, **kwargs) -> None:
        self.calls.append((text, kwargs))


class _App:
    def __init__(self, mode: str) -> None:
        self.state = SimpleNamespace(mode=mode)
        self.speech = _Speech()
        self.events: list[str] = []
        self.recovery_calls: list[tuple[str, str]] = []

    def _record_update_event(self, message: str) -> None:
        self.events.append(message)

    def _offer_update_failure_recovery(self, message: str, tb_str: str = "") -> None:
        self.recovery_calls.append((message, tb_str))


def _make_controller(mode: str) -> AppUpdateController:
    controller = AppUpdateController.__new__(AppUpdateController)
    controller.app = _App(mode)
    controller._update_error_message = ""
    controller._update_status = ""
    return controller


_ERROR_RESULT = {
    "status": "error",
    "message": "Network unreachable.",
    "traceback": "Traceback (most recent call last): ...",
}


class TestBackgroundCheckError(unittest.TestCase):
    def test_does_not_pull_the_user_out_of_a_game(self) -> None:
        controller = _make_controller("PLAYING")
        controller._handle_update_check_result({**_ERROR_RESULT, "manual": False})

        self.assertEqual(controller.app.state.mode, "PLAYING")
        self.assertEqual(controller.app.speech.calls, [])
        self.assertEqual(controller.app.recovery_calls, [])

    def test_still_records_the_failure_for_diagnostics(self) -> None:
        controller = _make_controller("PLAYING")
        controller._handle_update_check_result({**_ERROR_RESULT, "manual": False})

        self.assertTrue(
            any("Network unreachable." in event for event in controller.app.events),
            "a silent background failure must still be logged",
        )
        self.assertEqual(controller._update_error_message, "Network unreachable.")
        self.assertEqual(controller._update_status, "Update check failed.")

    def test_missing_manual_key_is_treated_as_background(self) -> None:
        controller = _make_controller("PLAYING")
        controller._handle_update_check_result(dict(_ERROR_RESULT))

        self.assertEqual(controller.app.recovery_calls, [])
        self.assertEqual(controller.app.speech.calls, [])


class TestManualCheckError(unittest.TestCase):
    def test_reports_the_failure_and_offers_recovery(self) -> None:
        controller = _make_controller("MENU")
        controller._handle_update_check_result({**_ERROR_RESULT, "manual": True})

        self.assertEqual(controller.app.state.mode, "MENU")
        self.assertEqual(len(controller.app.speech.calls), 1)
        spoken = controller.app.speech.calls[0][0]
        self.assertIn("Update check failed", spoken)
        self.assertIn("Network unreachable.", spoken)
        self.assertEqual(
            controller.app.recovery_calls,
            [("Network unreachable.", "Traceback (most recent call last): ...")],
        )


if __name__ == "__main__":
    unittest.main()
