"""A daily challenge finished in a test mode pays the XP it announces.

Fable review 2026-11-10, modules finding 4 (related note) and finding 7. Speed
Test and Sentence Practice said "Daily challenge complete. Earned 100 XP" but
never called xp_manager.award_xp, so the XP total did not change. In the
lesson path, XP from quests and the daily challenge could raise the level with
no level-up notification, because those award results were discarded.

What these still pass on: they prove the XP total and that the level-up
notification is CALLED; they say nothing about what a screen reader voices.
"""

import types
import unittest
from unittest import mock

from modules import challenge_manager, test_modes
from modules.state_manager import Settings


def _app(settings):
    app = mock.MagicMock()
    app.state.settings = settings
    app.state.test = types.SimpleNamespace(
        running=True,
        start_time=0.0,
        duration_seconds=60.0,
        total_chars=100,
        correct_chars=100,
        sentences_started=5,
        sentences_completed=5,
        current="",
        typed="",
        remaining=[],
    )
    app.state.practice = app.state.test
    app.apply_pet_session_progress.return_value = {}
    return app


class TestTestModeChallengeXp(unittest.TestCase):
    def _finish(self, finisher, challenge_type):
        settings = Settings()
        settings.daily_challenge_completed = False
        app = _app(settings)
        challenge = {"type": challenge_type, "target": {}}
        with mock.patch.object(challenge_manager, "get_today_challenge", return_value=challenge), \
                mock.patch.object(challenge_manager, "check_challenge_progress", return_value={"completed": True}), \
                mock.patch.object(challenge_manager, "complete_daily_challenge", return_value={"xp_earned": 100}), \
                mock.patch.object(test_modes.dashboard_manager, "record_session"):
            before = settings.xp
            finisher(app)
        return settings, before, app

    def test_speed_test_challenge_awards_its_xp(self):
        settings, before, app = self._finish(test_modes.finish_test, "speed_test")
        self.assertEqual(settings.xp - before, 100)
        app.show_level_up_notification.assert_called()

    def test_sentence_practice_challenge_awards_its_xp(self):
        settings, before, app = self._finish(test_modes.finish_practice, "sentence_practice")
        self.assertEqual(settings.xp - before, 100)
        app.show_level_up_notification.assert_called()

    def test_no_challenge_no_xp(self):
        """Negative twin: an unfinished challenge awards nothing."""
        settings = Settings()
        settings.daily_challenge_completed = False
        app = _app(settings)
        with mock.patch.object(challenge_manager, "get_today_challenge",
                               return_value={"type": "speed_test", "target": {}}), \
                mock.patch.object(challenge_manager, "check_challenge_progress", return_value={"completed": False}), \
                mock.patch.object(test_modes.dashboard_manager, "record_session"):
            before = settings.xp
            test_modes.finish_test(app)
        self.assertEqual(settings.xp, before)


if __name__ == "__main__":
    unittest.main()
