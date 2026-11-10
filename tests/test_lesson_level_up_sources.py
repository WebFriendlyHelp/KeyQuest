"""A level reached through quest or daily-challenge XP is announced.

Fable review 2026-11-10, modules finding 4 (related note). In
evaluate_lesson_performance only the main lesson award reached
show_level_up_notification; the award_xp results for quest rewards and the
daily challenge were discarded, so a level gained from them changed
settings.level silently and paid no level-up coins.

Drives the real evaluate_lesson_performance with a mocked app and real
Settings. What it would still pass on: it proves the notification is called
with the right level, not what the learner hears.
"""

import types
import unittest
from unittest import mock

from modules import challenge_manager, lesson_mode, quest_manager, xp_manager
from modules.state_manager import Settings


def _run_lesson(settings):
    tracker = mock.MagicMock()
    tracker.overall_accuracy.return_value = 1.0
    tracker.total_attempts = 10
    tracker.total_correct = 10
    tracker.calculate_wpm.return_value = 10.0
    tracker.key_performance = {}
    tracker.should_advance.return_value = False
    tracker.should_slow_down.return_value = False
    lesson = types.SimpleNamespace(stage=1, start_time=0.0, end_time=0.0, tracker=tracker, review_mode=False)
    app = mock.MagicMock()
    app.state.lesson = lesson
    app.state.settings = settings
    app.apply_pet_session_progress.return_value = {}
    with mock.patch.object(lesson_mode, "_require_pygame"), \
            mock.patch.object(lesson_mode.time, "time", return_value=60.0), \
            mock.patch.object(lesson_mode.pygame.time, "wait"), \
            mock.patch.object(lesson_mode.dashboard_manager, "record_session"), \
            mock.patch.object(challenge_manager, "get_today_challenge",
                              return_value={"type": "lesson_count", "target": {}}), \
            mock.patch.object(quest_manager, "check_all_active_quests", return_value=["accuracy_expert"]):
        lesson_mode.evaluate_lesson_performance(app)
    return app


class TestQuestXpLevelUpIsAnnounced(unittest.TestCase):
    def test_quest_reward_that_crosses_a_level_reaches_the_notification(self):
        # Measure what the lesson alone earns, so the start point leaves the
        # lesson award one XP short of level 2 and only the quest crosses it.
        probe = Settings()
        probe.daily_challenge_completed = True
        with mock.patch.object(quest_manager, "get_quest_info", return_value=None):
            _run_lesson(probe)
        lesson_xp = probe.xp
        level_two = xp_manager.LEVELS[1]["xp_required"]
        settings = Settings()
        settings.xp = level_two - lesson_xp - 1
        settings.daily_challenge_completed = True
        app = _run_lesson(settings)
        self.assertLess(settings.xp - 200, level_two, "setup: only the 200 XP quest reward crosses level 2")
        self.assertGreaterEqual(settings.level, 2, "the quest reward must cross the level")
        results = [c.args[0] for c in app.show_level_up_notification.call_args_list]
        self.assertTrue(any(r.get("leveled_up") and r.get("new_level") == settings.level for r in results),
                        results)

    def test_no_level_crossed_no_level_up(self):
        """Negative twin: XP that stays inside the level reports no level up."""
        settings = Settings()
        settings.daily_challenge_completed = True
        with mock.patch.object(quest_manager, "get_quest_info", return_value=None):
            app = _run_lesson(settings)
        results = [c.args[0] for c in app.show_level_up_notification.call_args_list]
        self.assertFalse(any(r.get("leveled_up") for r in results), results)


if __name__ == "__main__":
    unittest.main()
