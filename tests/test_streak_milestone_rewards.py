"""A streak milestone reached by practising is announced and pays its coins.

Fable review modules finding 14. record_session returns the milestone "rather
than dropped", and all four callers (lesson, speed test, sentence practice,
games) dropped it, so a learner who reached day 7 mid-session heard nothing.
The coin rewards streak_milestone_7, _30 and _100 were never awarded anywhere.

Now the milestone line, with its coins, goes in the results dialog (one
channel) for lessons and test modes, and in the queued reward line for games.

These drive the real finishers with a mocked app and real Settings. They prove
the text reaches the dialog or speech call and the coin total; not what a
screen reader voices.
"""

import types
import unittest
from unittest import mock

from modules import challenge_manager, lesson_mode, quest_manager, streak_manager, test_modes
from modules.keyquest_app import KeyQuestApp
from modules.state_manager import Settings


class TestMilestoneText(unittest.TestCase):
    def test_day_seven_pays_its_coins(self):
        settings = Settings()
        text = streak_manager.award_streak_milestone(settings, 7)
        self.assertEqual(settings.coins, 100)
        self.assertIn("Day 7", text)
        self.assertIn("100 coins", text)

    def test_a_milestone_without_a_coin_reward_still_has_a_line(self):
        settings = Settings()
        text = streak_manager.award_streak_milestone(settings, 3)
        self.assertEqual(settings.coins, 0)
        self.assertIn("Day 3", text)
        self.assertNotIn("coins", text)

    def test_no_milestone_no_text_no_coins(self):
        settings = Settings()
        self.assertEqual(streak_manager.award_streak_milestone(settings, None), "")
        self.assertEqual(settings.coins, 0)


def _test_app(settings):
    app = mock.MagicMock()
    app.state.settings = settings
    app.state.test = types.SimpleNamespace(
        running=True, start_time=0.0, duration_seconds=60.0, total_chars=100,
        correct_chars=100, sentences_started=5, sentences_completed=5,
        current="", typed="", remaining=[],
    )
    app.state.practice = app.state.test
    app.apply_pet_session_progress.return_value = {}
    return app


class TestCallersUseTheMilestone(unittest.TestCase):
    def _finish_test_mode(self, finisher, milestone):
        settings = Settings()
        settings.daily_challenge_completed = True
        app = _test_app(settings)
        with mock.patch.object(test_modes.dashboard_manager, "record_session", return_value=milestone):
            finisher(app)
        return settings, app.show_results_dialog.call_args.args[0]

    def test_speed_test_dialog_names_the_milestone(self):
        settings, text = self._finish_test_mode(test_modes.finish_test, 7)
        self.assertIn("Day 7", text)
        self.assertIn("100 coins", text)

    def test_sentence_practice_dialog_names_the_milestone(self):
        settings, text = self._finish_test_mode(test_modes.finish_practice, 30)
        self.assertIn("Day 30", text)
        self.assertIn("250 coins", text)

    def test_no_milestone_no_line(self):
        # Negative twin.
        _settings, text = self._finish_test_mode(test_modes.finish_test, None)
        self.assertNotIn("Streak milestone", text)

    def test_lesson_dialog_names_the_milestone(self):
        settings = Settings()
        settings.daily_challenge_completed = True
        tracker = mock.MagicMock()
        tracker.overall_accuracy.return_value = 1.0
        tracker.total_attempts = 10
        tracker.total_correct = 10
        tracker.calculate_wpm.return_value = 10.0
        tracker.key_performance = {}
        tracker.should_advance.return_value = False
        tracker.should_slow_down.return_value = False
        app = mock.MagicMock()
        app.state.lesson = types.SimpleNamespace(stage=1, start_time=0.0, end_time=0.0,
                                                 tracker=tracker, review_mode=False)
        app.state.settings = settings
        app.apply_pet_session_progress.return_value = {}
        with mock.patch.object(lesson_mode, "_require_pygame"), \
                mock.patch.object(lesson_mode.time, "time", return_value=60.0), \
                mock.patch.object(lesson_mode.pygame.time, "wait"), \
                mock.patch.object(lesson_mode.dashboard_manager, "record_session", return_value=7), \
                mock.patch.object(challenge_manager, "get_today_challenge",
                                  return_value={"type": "lesson_count", "target": {}}), \
                mock.patch.object(quest_manager, "check_all_active_quests", return_value=[]):
            lesson_mode.evaluate_lesson_performance(app)
        text = app.show_guided_results_dialog.call_args.args[0]
        self.assertIn("Day 7", text)
        self.assertIn("100 coins", text)

    def test_game_reward_line_names_the_milestone(self):
        settings = Settings()
        app = mock.MagicMock()
        app.state.settings = settings
        app.apply_pet_session_progress.return_value = {}
        game = types.SimpleNamespace(NAME="Letter Fall")
        with mock.patch("modules.keyquest_app.dashboard_manager.record_session", return_value=7):
            KeyQuestApp.handle_game_session_complete(app, game, {"accuracy": 90.0})
        spoken = " ".join(c.args[0] for c in app.speech.say.call_args_list)
        self.assertIn("Day 7", spoken)
        self.assertIn("100 coins", spoken)


if __name__ == "__main__":
    unittest.main()
