"""Special-key lessons 25 to 32 can be passed by a perfect typist.

Fable review 2026-11-10, modules finding 6. should_advance needs three correct
NON-REPEATED keys in a row, and from lesson 6 on also 20 WPM, which the code
documents as the bar for "lessons with phrases". Lesson 25 is five presses of
Tab, so the streak never passes 1; lessons 26 to 32 are single presses after a
spoken instruction, so 20 WPM means six presses in 3.6 seconds. A learner with
100 percent accuracy was told "Keep practicing" and nothing unlocked.

Drives the real evaluate_lesson_performance with a real AdaptiveTracker. What
it would still pass on: it proves the unlock and the star count, not what the
results dialog says aloud.
"""

import types
import unittest
from unittest import mock

from modules import challenge_manager, lesson_manager, lesson_mode, quest_manager
from modules.state_manager import AdaptiveTracker, Settings


def _finish(stage, keys, seconds, errors=0):
    tracker = AdaptiveTracker()
    for key in keys:
        tracker.record_keystroke(key, True)
    for _ in range(errors):
        tracker.record_keystroke("x", False)
    settings = Settings()
    settings.daily_challenge_completed = True
    settings.auto_start_next_lesson = False
    lesson = types.SimpleNamespace(stage=stage, start_time=0.0, end_time=0.0, tracker=tracker, review_mode=False)
    app = mock.MagicMock()
    app.state.lesson = lesson
    app.state.settings = settings
    app.apply_pet_session_progress.return_value = {}
    with mock.patch.object(lesson_mode, "_require_pygame"), \
            mock.patch.object(lesson_mode.time, "time", return_value=float(seconds)), \
            mock.patch.object(lesson_mode.pygame.time, "wait"), \
            mock.patch.object(lesson_mode.dashboard_manager, "record_session"), \
            mock.patch.object(challenge_manager, "get_today_challenge",
                              return_value={"type": "lesson_count", "target": {}}), \
            mock.patch.object(quest_manager, "check_all_active_quests", return_value=[]):
        lesson_mode.evaluate_lesson_performance(app)
    return settings


class TestSpecialKeyLessonsAdvance(unittest.TestCase):
    def test_the_lessons_under_test_are_the_special_key_lessons(self):
        self.assertEqual(sorted(lesson_manager.SPECIAL_KEY_COMMANDS), list(range(25, 33)))

    def test_five_perfect_tab_presses_pass_lesson_25(self):
        settings = _finish(25, ["tab"] * 5, seconds=20)
        self.assertIn(26, settings.unlocked_lessons)
        self.assertEqual(settings.lesson_stars.get(25), 3)

    def test_a_slow_perfect_lesson_26_passes(self):
        keys = ["backspace", "delete", "backspace", "delete", "backspace", "delete"]
        settings = _finish(26, keys, seconds=30)
        self.assertIn(27, settings.unlocked_lessons)
        self.assertEqual(settings.lesson_stars.get(26), 3)

    def test_a_poor_special_key_lesson_still_does_not_pass(self):
        """Negative twin: accuracy is still required."""
        settings = _finish(26, ["backspace", "delete"], seconds=30, errors=4)
        self.assertNotIn(27, settings.unlocked_lessons)

    def test_phrase_lessons_still_need_the_speed(self):
        """Negative twin: a slow perfect lesson 10 still does not advance."""
        keys = list("asdfjkl;" * 3)
        settings = _finish(10, keys, seconds=60)
        self.assertNotIn(11, settings.unlocked_lessons)


if __name__ == "__main__":
    unittest.main()
