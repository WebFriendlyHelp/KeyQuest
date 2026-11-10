"""Quest completion pays once, and the WPM quest can finish.

Fable review 2026-11-10, modules finding 4. A completed quest stayed in
active_quests, update_quest_progress answered "completed" for it on every
later lesson, and check_all_active_quests reported it as newly completed each
time, so lesson_mode paid its XP reward again after every lesson. Separately,
"Speed Demon Training" stored progress 1 but compared it with the 40 WPM
target, so it could never complete.
"""

import unittest

from modules import quest_manager
from modules.state_manager import Settings


def _fresh_settings():
    settings = Settings()
    quest_manager.initialize_quests(settings)
    return settings


class TestQuestsPayOnce(unittest.TestCase):
    def test_a_completed_quest_is_reported_once(self):
        settings = _fresh_settings()
        data = {"lesson_num": 3, "accuracy": 99.0, "wpm": 10, "duration": 60}
        reports = []
        for lesson in (1, 2, 3, 4, 5):
            data["lesson_num"] = lesson
            reports.append(quest_manager.check_all_active_quests(settings, dict(data)))
        self.assertIn("accuracy_expert", reports[2], "the third high-accuracy lesson completes it")
        later = [quest for report in reports[3:] for quest in report]
        self.assertNotIn("accuracy_expert", later, "a finished quest must not pay again")

    def test_a_quest_that_has_not_finished_is_not_reported(self):
        """Negative twin: one high-accuracy lesson completes nothing."""
        settings = _fresh_settings()
        report = quest_manager.check_all_active_quests(
            settings, {"lesson_num": 1, "accuracy": 99.0, "wpm": 10, "duration": 60}
        )
        self.assertEqual(report, [])


class TestSpeedDemonCanFinish(unittest.TestCase):
    def test_reaching_the_target_wpm_completes_it(self):
        settings = _fresh_settings()
        result = quest_manager.update_quest_progress(
            settings, "speed_demon", {"wpm": 80, "accuracy": 95, "lesson_num": 9}
        )
        self.assertTrue(result["completed"], result)
        self.assertIn("speed_demon", settings.completed_quests)

    def test_below_the_target_wpm_shows_real_progress(self):
        settings = _fresh_settings()
        quest_manager.update_quest_progress(settings, "speed_demon", {"wpm": 30})
        result = quest_manager.update_quest_progress(settings, "speed_demon", {"wpm": 20})
        self.assertFalse(result["completed"])
        self.assertEqual(settings.active_quests["speed_demon"]["progress"], 30, "keeps the best WPM")
        self.assertIn("Progress: 30/40", quest_manager.format_quest_list(settings))


if __name__ == "__main__":
    unittest.main()
