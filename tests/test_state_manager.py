import json
import os
import tempfile
import unittest
from unittest.mock import patch

from modules.state_manager import AppState, ProgressManager, PROGRESS_SCHEMA_VERSION


class TestProgressManager(unittest.TestCase):
    def test_load_sets_current_and_unlocks(self):
        state = AppState()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": PROGRESS_SCHEMA_VERSION,
                        "current_lesson": 3,
                        "unlocked_lessons": [1, 2],
                        "speech_mode": "tts",
                        "typing_sound_intensity": "strong",
                        "visual_theme": "dark",
                        "focus_assist": True,
                        "sentence_language": "Spanish",
                        "auto_update_check": False,
                        "auto_start_next_lesson": True,
                        "lesson_stars": {"1": 2},
                        "lesson_best_wpm": {"1": 25.5},
                        "lesson_best_accuracy": {"1": 92.0},
                        "earned_badges": ["badge_a"],
                        "owned_items": ["hat"],
                    },
                    f,
                    indent=2,
                )

            ProgressManager(path).load(state, stage_letters_count=50)

        self.assertEqual(state.settings.current_lesson, 3)
        self.assertEqual(state.lesson.stage, 3)
        self.assertIn(0, state.settings.unlocked_lessons)
        self.assertIn(3, state.settings.unlocked_lessons)
        self.assertIn(2, state.settings.unlocked_lessons)
        self.assertEqual(state.settings.speech_mode, "tts")
        self.assertEqual(state.settings.typing_sound_intensity, "strong")
        self.assertEqual(state.settings.visual_theme, "dark")
        self.assertTrue(state.settings.focus_assist)
        self.assertEqual(state.settings.sentence_language, "Spanish")
        self.assertFalse(state.settings.auto_update_check)
        self.assertTrue(state.settings.auto_start_next_lesson)
        self.assertEqual(state.settings.lesson_stars[1], 2)
        self.assertAlmostEqual(state.settings.lesson_best_wpm[1], 25.5)
        self.assertAlmostEqual(state.settings.lesson_best_accuracy[1], 92.0)
        self.assertIn("badge_a", state.settings.earned_badges)
        self.assertIn("hat", state.settings.owned_items)

    def test_load_ignores_invalid_current_lesson(self):
        state = AppState()
        state.settings.current_lesson = 2
        state.lesson.stage = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"current_lesson": 999, "unlocked_lessons": [5]}, f)

            ProgressManager(path).load(state, stage_letters_count=10)

        self.assertEqual(state.settings.current_lesson, 2)
        self.assertEqual(state.lesson.stage, 2)
        self.assertIn(0, state.settings.unlocked_lessons)
        self.assertIn(2, state.settings.unlocked_lessons)
        self.assertIn(5, state.settings.unlocked_lessons)

    def test_load_missing_file_resets_to_defaults(self):
        state = AppState()
        state.settings.current_lesson = 7
        state.lesson.stage = 7
        state.settings.unlocked_lessons = {0, 7}
        state.settings.speech_mode = "off"
        state.settings.visual_theme = "light"
        state.settings.sentence_language = "History Facts"

        ProgressManager("this_file_should_not_exist.json").load(state, stage_letters_count=10)

        self.assertEqual(state.settings.current_lesson, 0)
        self.assertEqual(state.lesson.stage, 0)
        self.assertEqual(state.settings.unlocked_lessons, {0})
        self.assertEqual(state.settings.speech_mode, "auto")
        self.assertEqual(state.settings.visual_theme, "auto")
        self.assertEqual(state.settings.sentence_language, "English")
        self.assertTrue(state.settings.auto_update_check)
        self.assertFalse(state.settings.auto_start_next_lesson)

    def test_save_writes_schema_and_keys(self):
        state = AppState()
        state.settings.current_lesson = 4
        state.settings.unlocked_lessons = {0, 4, 2}
        state.settings.earned_badges = {"b1"}
        state.settings.owned_items = {"item_a"}
        state.settings.typing_sound_intensity = "subtle"
        state.settings.focus_assist = True
        state.settings.auto_update_check = False
        state.settings.auto_start_next_lesson = True

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            ProgressManager(path).save(state)
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)

        self.assertEqual(saved["schema_version"], PROGRESS_SCHEMA_VERSION)
        self.assertEqual(saved["current_lesson"], 4)
        self.assertEqual(saved["typing_sound_intensity"], "subtle")
        self.assertTrue(saved["focus_assist"])
        self.assertFalse(saved["auto_update_check"])
        self.assertTrue(saved["auto_start_next_lesson"])
        self.assertEqual(saved["unlocked_lessons"], [0, 2, 4])
        self.assertEqual(saved["earned_badges"], ["b1"])
        self.assertEqual(saved["owned_items"], ["item_a"])

    def test_default_main_menu_labels_and_order(self):
        state = AppState()
        items = state.menu_items
        self.assertIn("Games: G", items)
        self.assertIn("Quests: Q", items)
        self.assertIn("Pets: P", items)
        self.assertIn("Pet Shop: P", items)
        self.assertIn("Badges: B", items)
        self.assertIn("Check for Updates: U", items)
        self.assertIn("New in Key Quest: N", items)
        self.assertIn("About: A", items)
        self.assertNotIn("View Quests: V", items)
        self.assertNotIn("View Badges: V", items)

        self.assertLess(items.index("Games: G"), items.index("Quests: Q"))
        self.assertLess(items.index("Quests: Q"), items.index("Pets: P"))
        self.assertLess(items.index("Pets: P"), items.index("Pet Shop: P"))
        self.assertLess(items.index("Check for Updates: U"), items.index("Key Quest Instructions: I"))
        self.assertLess(items.index("Key Quest Instructions: I"), items.index("New in Key Quest: N"))
        self.assertLess(items.index("New in Key Quest: N"), items.index("About: A"))
        self.assertLess(items.index("Key Quest Instructions: I"), items.index("About: A"))
        self.assertEqual(items[-1], "Quit: Q")


class TestSchemaMigration(unittest.TestCase):
    """Tests for ProgressManager.load() schema migration and robustness."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _load_from_dict(self, data: dict, stage_letters_count: int = 50) -> AppState:
        """Write *data* to a temp file, call load(), and return the state."""
        state = AppState()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            ProgressManager(path).load(state, stage_letters_count=stage_letters_count)
        return state

    # ------------------------------------------------------------------
    # v0-style data (no schema_version key)
    # ------------------------------------------------------------------

    def test_v0_bare_dict_populates_safe_defaults(self):
        """A legacy dict with no schema_version key and only current_lesson
        must fill every Settings field with its documented default value."""
        state = self._load_from_dict({"current_lesson": 3})

        # current_lesson is within bounds, so it should be loaded
        self.assertEqual(state.settings.current_lesson, 3)
        self.assertEqual(state.lesson.stage, 3)

        # All fields absent from the dict get safe defaults
        self.assertEqual(state.settings.speech_mode, "auto")
        self.assertEqual(state.settings.typing_sound_intensity, "normal")
        self.assertEqual(state.settings.visual_theme, "auto")
        self.assertEqual(state.settings.font_scale, "auto")
        self.assertFalse(state.settings.focus_assist)
        self.assertEqual(state.settings.sentence_language, "English")
        self.assertTrue(state.settings.auto_update_check)
        self.assertFalse(state.settings.auto_start_next_lesson)
        self.assertEqual(state.settings.tts_rate, 200)
        self.assertAlmostEqual(state.settings.tts_volume, 1.0)
        self.assertEqual(state.settings.tts_voice, "")
        self.assertEqual(state.settings.current_streak, 0)
        self.assertEqual(state.settings.last_practice_date, "")
        self.assertEqual(state.settings.longest_streak, 0)
        self.assertEqual(state.settings.lesson_stars, {})
        self.assertEqual(state.settings.lesson_best_wpm, {})
        self.assertEqual(state.settings.lesson_best_accuracy, {})
        self.assertEqual(state.settings.earned_badges, set())
        self.assertEqual(state.settings.badge_notifications, [])
        self.assertEqual(state.settings.total_lessons_completed, 0)
        self.assertAlmostEqual(state.settings.total_practice_time, 0.0)
        self.assertAlmostEqual(state.settings.highest_wpm, 0.0)
        self.assertEqual(state.settings.xp, 0)
        self.assertEqual(state.settings.level, 1)
        self.assertEqual(state.settings.key_stats, {})
        self.assertEqual(state.settings.daily_challenge_date, "")
        self.assertFalse(state.settings.daily_challenge_completed)
        self.assertEqual(state.settings.daily_challenge_streak, 0)
        self.assertEqual(state.settings.active_quests, {})
        self.assertEqual(state.settings.completed_quests, set())
        self.assertEqual(state.settings.quest_notifications, [])
        self.assertEqual(state.settings.session_history, [])
        self.assertEqual(state.settings.coins, 0)
        self.assertEqual(state.settings.total_coins_earned, 0)
        self.assertEqual(state.settings.owned_items, set())
        self.assertEqual(state.settings.inventory, {})
        self.assertEqual(state.settings.pet_type, "")
        self.assertEqual(state.settings.pet_name, "")
        self.assertEqual(state.settings.pet_xp, 0)
        self.assertEqual(state.settings.pet_happiness, 50)
        self.assertEqual(state.settings.pet_mood, "happy")
        self.assertEqual(state.settings.pet_last_fed, "")

        # Lessons 0 and current_lesson are always unlocked
        self.assertIn(0, state.settings.unlocked_lessons)
        self.assertIn(3, state.settings.unlocked_lessons)

    def test_v0_always_unlocks_lesson_zero(self):
        """Even without unlocked_lessons in the file lesson 0 must be unlocked."""
        state = self._load_from_dict({"current_lesson": 0})
        self.assertIn(0, state.settings.unlocked_lessons)

    # ------------------------------------------------------------------
    # schema_version = 1 data (current version)
    # ------------------------------------------------------------------

    def test_v1_known_fields_loaded_correctly(self):
        """schema_version=1 data with a full set of known fields must round-trip."""
        data = {
            "schema_version": 1,
            "current_lesson": 5,
            "unlocked_lessons": [0, 1, 2, 3, 4, 5],
            "speech_mode": "screen_reader",
            "typing_sound_intensity": "subtle",
            "visual_theme": "high_contrast",
            "font_scale": "150%",
            "focus_assist": True,
            "sentence_language": "Spanish",
            "auto_update_check": False,
            "auto_start_next_lesson": True,
            "tts_rate": 150,
            "tts_volume": 0.8,
            "tts_voice": "en-GB",
            "current_streak": 7,
            "last_practice_date": "2024-01-15",
            "longest_streak": 14,
            "lesson_stars": {"3": 2, "4": 3},
            "lesson_best_wpm": {"3": 30.0, "4": 45.5},
            "lesson_best_accuracy": {"3": 88.0, "4": 97.0},
            "earned_badges": ["first_lesson", "speed_demon"],
            "badge_notifications": ["speed_demon"],
            "total_lessons_completed": 10,
            "total_practice_time": 3600.0,
            "highest_wpm": 55.0,
            "xp": 500,
            "level": 3,
            "key_stats": {"a": {"attempts": 20, "correct": 18, "errors": 2}},
            "daily_challenge_date": "2024-01-15",
            "daily_challenge_completed": True,
            "daily_challenge_streak": 5,
            "active_quests": {"quest_1": {"progress": 3, "target": 5, "completed": False}},
            "completed_quests": ["quest_0"],
            "quest_notifications": [],
            "session_history": [{"date": "2024-01-15", "wpm": 45.5}],
            "coins": 120,
            "total_coins_earned": 250,
            "owned_items": ["theme_dark"],
            "inventory": {"hint_token": 2},
            "pet_type": "dragon",
            "pet_name": "Blaze",
            "pet_xp": 80,
            "pet_happiness": 90,
            "pet_mood": "excited",
            "pet_last_fed": "",
        }
        state = self._load_from_dict(data)

        self.assertEqual(state.settings.current_lesson, 5)
        self.assertEqual(state.lesson.stage, 5)
        self.assertEqual(state.settings.unlocked_lessons, {0, 1, 2, 3, 4, 5})
        self.assertEqual(state.settings.speech_mode, "screen_reader")
        self.assertEqual(state.settings.typing_sound_intensity, "subtle")
        self.assertEqual(state.settings.visual_theme, "high_contrast")
        self.assertEqual(state.settings.font_scale, "150%")
        self.assertTrue(state.settings.focus_assist)
        self.assertEqual(state.settings.sentence_language, "Spanish")
        self.assertFalse(state.settings.auto_update_check)
        self.assertTrue(state.settings.auto_start_next_lesson)
        self.assertEqual(state.settings.tts_rate, 150)
        self.assertAlmostEqual(state.settings.tts_volume, 0.8)
        self.assertEqual(state.settings.tts_voice, "en-GB")
        self.assertEqual(state.settings.current_streak, 7)
        self.assertEqual(state.settings.last_practice_date, "2024-01-15")
        self.assertEqual(state.settings.longest_streak, 14)
        self.assertEqual(state.settings.lesson_stars, {3: 2, 4: 3})
        self.assertAlmostEqual(state.settings.lesson_best_wpm[3], 30.0)
        self.assertAlmostEqual(state.settings.lesson_best_wpm[4], 45.5)
        self.assertAlmostEqual(state.settings.lesson_best_accuracy[3], 88.0)
        self.assertAlmostEqual(state.settings.lesson_best_accuracy[4], 97.0)
        self.assertEqual(state.settings.earned_badges, {"first_lesson", "speed_demon"})
        self.assertEqual(state.settings.badge_notifications, ["speed_demon"])
        self.assertEqual(state.settings.total_lessons_completed, 10)
        self.assertAlmostEqual(state.settings.total_practice_time, 3600.0)
        self.assertAlmostEqual(state.settings.highest_wpm, 55.0)
        self.assertEqual(state.settings.xp, 500)
        self.assertEqual(state.settings.level, 3)
        self.assertEqual(state.settings.key_stats["a"]["correct"], 18)
        self.assertEqual(state.settings.daily_challenge_date, "2024-01-15")
        self.assertTrue(state.settings.daily_challenge_completed)
        self.assertEqual(state.settings.daily_challenge_streak, 5)
        self.assertIn("quest_1", state.settings.active_quests)
        self.assertEqual(state.settings.completed_quests, {"quest_0"})
        self.assertEqual(state.settings.session_history, [{"date": "2024-01-15", "wpm": 45.5}])
        self.assertEqual(state.settings.coins, 120)
        self.assertEqual(state.settings.total_coins_earned, 250)
        self.assertEqual(state.settings.owned_items, {"theme_dark"})
        self.assertEqual(state.settings.inventory, {"hint_token": 2})
        self.assertEqual(state.settings.pet_type, "dragon")
        self.assertEqual(state.settings.pet_name, "Blaze")
        self.assertEqual(state.settings.pet_xp, 80)
        self.assertEqual(state.settings.pet_happiness, 90)
        self.assertEqual(state.settings.pet_mood, "excited")

    def test_v1_lesson_star_keys_are_int(self):
        """JSON keys are always strings; load() must convert them to int."""
        data = {
            "schema_version": 1,
            "lesson_stars": {"0": 1, "2": 3},
            "lesson_best_wpm": {"0": 22.0, "2": 40.0},
            "lesson_best_accuracy": {"0": 80.0, "2": 95.0},
        }
        state = self._load_from_dict(data)
        self.assertIn(0, state.settings.lesson_stars)
        self.assertIn(2, state.settings.lesson_stars)
        self.assertNotIn("0", state.settings.lesson_stars)
        self.assertNotIn("2", state.settings.lesson_stars)

    # ------------------------------------------------------------------
    # Completely empty dict
    # ------------------------------------------------------------------

    def test_empty_dict_no_crash_all_defaults(self):
        """An empty dict must not crash and must yield fully-defaulted Settings."""
        state = self._load_from_dict({})

        self.assertEqual(state.settings.current_lesson, 0)
        self.assertEqual(state.lesson.stage, 0)
        self.assertIn(0, state.settings.unlocked_lessons)
        self.assertEqual(state.settings.speech_mode, "auto")
        self.assertEqual(state.settings.visual_theme, "auto")
        self.assertEqual(state.settings.font_scale, "auto")
        self.assertFalse(state.settings.focus_assist)
        self.assertEqual(state.settings.sentence_language, "English")
        self.assertTrue(state.settings.auto_update_check)
        self.assertFalse(state.settings.auto_start_next_lesson)
        self.assertEqual(state.settings.tts_rate, 200)
        self.assertAlmostEqual(state.settings.tts_volume, 1.0)
        self.assertEqual(state.settings.xp, 0)
        self.assertEqual(state.settings.level, 1)
        self.assertEqual(state.settings.coins, 0)
        self.assertEqual(state.settings.pet_type, "")
        self.assertEqual(state.settings.pet_happiness, 50)

    # ------------------------------------------------------------------
    # Corrupted / unreadable file scenarios
    # ------------------------------------------------------------------

    def test_corrupted_json_no_crash_falls_back_to_defaults(self):
        """A file containing invalid JSON must not crash; load() uses defaults."""
        state = AppState()
        # Pre-set non-default values to confirm they get reset
        state.settings.current_lesson = 9
        state.settings.speech_mode = "off"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("this is not valid json }{")
            ProgressManager(path).load(state, stage_letters_count=10)

        self.assertEqual(state.settings.current_lesson, 0)
        self.assertEqual(state.settings.speech_mode, "auto")
        self.assertIn(0, state.settings.unlocked_lessons)

    def test_empty_file_no_crash_falls_back_to_defaults(self):
        """An empty file (zero bytes) must not crash; load() uses defaults."""
        state = AppState()
        state.settings.current_lesson = 5
        state.settings.visual_theme = "dark"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            open(path, "w").close()  # create empty file
            ProgressManager(path).load(state, stage_letters_count=10)

        self.assertEqual(state.settings.current_lesson, 0)
        self.assertEqual(state.settings.visual_theme, "auto")

    def test_file_containing_null_no_crash(self):
        """A file containing only 'null' decodes to Python None; must not crash."""
        state = AppState()
        state.settings.current_lesson = 4

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("null")
            ProgressManager(path).load(state, stage_letters_count=10)

        # Should fall back to defaults without raising
        self.assertEqual(state.settings.current_lesson, 0)
        self.assertIn(0, state.settings.unlocked_lessons)

    def test_file_containing_list_no_crash(self):
        """A file containing a JSON array instead of an object must not crash."""
        state = AppState()
        state.settings.current_lesson = 6

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("[1, 2, 3]")
            ProgressManager(path).load(state, stage_letters_count=10)

        # load() will attempt data.get(...) on a list, which raises AttributeError
        # and falls back to defaults
        self.assertEqual(state.settings.current_lesson, 0)
        self.assertIn(0, state.settings.unlocked_lessons)


class TestProgressManagerReturnValues(unittest.TestCase):
    """Tests that load() returns True/False and that failures are logged."""

    def test_load_returns_true_on_success(self):
        state = AppState()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"schema_version": PROGRESS_SCHEMA_VERSION, "current_lesson": 1}, f)
            result = ProgressManager(path).load(state, stage_letters_count=50)
        self.assertTrue(result)

    def test_load_returns_false_on_missing_file(self):
        state = AppState()
        result = ProgressManager("nonexistent_file.json").load(state, stage_letters_count=50)
        self.assertFalse(result)

    def test_load_returns_false_on_corrupted_file(self):
        state = AppState()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not valid json }{")
            result = ProgressManager(path).load(state, stage_letters_count=50)
        self.assertFalse(result)

    def test_load_failure_is_logged(self):
        state = AppState()
        with patch("modules.error_logging.log_message") as mock_log:
            ProgressManager("nonexistent_file.json").load(state, stage_letters_count=50)
        mock_log.assert_called_once()
        label = mock_log.call_args[0][0]
        self.assertIn("load", label.lower())

    def test_save_failure_is_logged(self):
        state = AppState()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Point save at an unwritable path (a directory, not a file)
            bad_path = os.path.join(tmpdir, "is_a_dir", "progress.json")
            with patch("modules.error_logging.log_message") as mock_log:
                ProgressManager(bad_path).save(state)
        mock_log.assert_called_once()
        label = mock_log.call_args[0][0]
        self.assertIn("save", label.lower())


if __name__ == "__main__":
    unittest.main()
