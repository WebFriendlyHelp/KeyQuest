"""Tests for unobtrusive spoken updater download milestones."""

import unittest
from types import SimpleNamespace

from modules.update_controller import AppUpdateController


class _Speech:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def say(self, text: str, **kwargs) -> None:
        self.calls.append((text, kwargs))


class TestUpdateProgressAnnouncements(unittest.TestCase):
    def setUp(self) -> None:
        self.speech = _Speech()
        self.controller = AppUpdateController.__new__(AppUpdateController)
        self.controller.app = SimpleNamespace(
            state=SimpleNamespace(mode="UPDATING"),
            speech=self.speech,
        )
        self.controller._update_downloaded_bytes = 0
        self.controller._update_total_bytes = 100
        self.controller._last_spoken_download_milestone = 0

    def _set_progress(self, downloaded: int) -> None:
        self.controller._update_downloaded_bytes = downloaded
        self.controller._announce_download_progress_milestone()

    def test_speaks_each_quarter_once(self) -> None:
        for downloaded in (24, 25, 49, 50, 74, 75, 100):
            self._set_progress(downloaded)

        self.assertEqual(
            self.speech.calls,
            [
                ("25 percent.", {"interrupt": False}),
                ("50 percent.", {"interrupt": False}),
                ("75 percent.", {"interrupt": False}),
            ],
        )

    def test_progress_jump_speaks_only_highest_new_milestone(self) -> None:
        self._set_progress(76)
        self._set_progress(90)

        self.assertEqual(self.speech.calls, [("75 percent.", {"interrupt": False})])

    def test_does_not_speak_without_known_total(self) -> None:
        self.controller._update_total_bytes = 0
        self._set_progress(75)

        self.assertEqual(self.speech.calls, [])

    def test_does_not_speak_outside_update_mode(self) -> None:
        self.controller.app.state.mode = "MENU"
        self._set_progress(75)

        self.assertEqual(self.speech.calls, [])


if __name__ == "__main__":
    unittest.main()
