import unittest

from modules import lesson_manager
from modules import lesson_mode


class DummyTracker:
    def __init__(self):
        self.recorded = []

    def get_struggling_keys(self):
        return []

    def record_keystroke(self, key, correct):
        self.recorded.append((key, correct))


class DummyLessonState:
    def __init__(self, stage: int):
        self.stage = stage
        self.tracker = DummyTracker()
        self.review_mode = False
        self.use_words = True
        self.batch_words = []
        self.batch_instructions = []
        self.index = -1
        self.typed = "not-empty"
        self.start_time = None
        self.errors_in_row = 0
        self.show_guidance = False
        self.guidance_message = ""
        self.hint_message = ""


class DummyState:
    def __init__(self, lesson_state):
        self.lesson = lesson_state
        self.settings = type("Settings", (), {"key_stats": {}})()


class DummyApp:
    def __init__(self, lesson_state):
        self.state = DummyState(lesson_state)
        self.guidance_calls = []
        self.prompt_calls = 0
        self.audio = type(
            "Audio",
            (),
            {
                "beep_bad": lambda _self: None,
                "play_success": lambda _self: None,
                "play_progressive": lambda _self, _pct: None,
            },
        )()
        self.speech = type("Speech", (), {"say": lambda _self, _text, **_kwargs: None})()

    def current_word(self):
        return self.state.lesson.batch_words[self.state.lesson.index]

    def trigger_flash(self, *_args, **_kwargs):
        pass

    def provide_key_guidance(self, pressed, target, matched_prefix=""):
        self.guidance_calls.append((pressed, target, matched_prefix))


class TestLessonMode(unittest.TestCase):
    def test_calculate_lesson_stars_early_lessons_accuracy_only(self):
        self.assertEqual(lesson_mode.calculate_lesson_stars(0, 96, 0), 3)
        self.assertEqual(lesson_mode.calculate_lesson_stars(0, 90, 0), 2)
        self.assertEqual(lesson_mode.calculate_lesson_stars(0, 72, 0), 1)
        self.assertEqual(lesson_mode.calculate_lesson_stars(0, 60, 0), 0)

    def test_calculate_lesson_stars_wpm_thresholds(self):
        lesson_num = max(lesson_manager.WPM_REQUIRED_FROM_LESSON, 6)
        self.assertEqual(lesson_mode.calculate_lesson_stars(lesson_num, 95, 30), 3)
        self.assertEqual(lesson_mode.calculate_lesson_stars(lesson_num, 85, 20), 2)
        self.assertEqual(lesson_mode.calculate_lesson_stars(lesson_num, 95, 10), 1)
        self.assertEqual(lesson_mode.calculate_lesson_stars(lesson_num, 60, 50), 0)

    def test_build_lesson_batch_special_key_stage_sets_instructions(self):
        stage = sorted(lesson_manager.SPECIAL_KEY_COMMANDS.keys())[0]
        lesson_state = DummyLessonState(stage)
        app = DummyApp(lesson_state)

        lesson_mode.build_lesson_batch(app)

        commands = lesson_manager.SPECIAL_KEY_COMMANDS[stage]
        expected_words = [cmd[1] for cmd in commands]
        expected_instructions = [cmd[0] for cmd in commands]

        self.assertEqual(lesson_state.batch_words, expected_words)
        self.assertEqual(lesson_state.batch_instructions, expected_instructions)
        self.assertEqual(lesson_state.index, 0)
        self.assertEqual(lesson_state.typed, "")
        self.assertIsInstance(lesson_state.start_time, float)

    def test_build_lesson_batch_early_stage_front_loads_new_key_repetition(self):
        lesson_state = DummyLessonState(stage=1)
        app = DummyApp(lesson_state)

        lesson_mode.build_lesson_batch(app)

        self.assertEqual(len(lesson_state.batch_words), lesson_manager.LESSON_BATCH)
        self.assertEqual(lesson_state.batch_words[:3], ["sss", "ss", "ssss"])
        self.assertTrue(all(len(word) in (2, 3, 4) for word in lesson_state.batch_words[:6]))

    def test_lesson_prompt_speaks_remaining_suffix_only(self):
        lesson_state = DummyLessonState(stage=0)
        lesson_state.batch_words = ["asdf"]
        lesson_state.index = 0
        lesson_state.typed = "as"
        messages = []
        app = DummyApp(lesson_state)
        app.speech = type("Speech", (), {"say": lambda _self, text, **_kwargs: messages.append(text)})()

        lesson_mode.lesson_prompt(app)

        self.assertEqual(messages[-1], "Type d, f")

    def test_process_lesson_typing_preserves_correct_prefix_after_error(self):
        lesson_state = DummyLessonState(stage=0)
        lesson_state.batch_words = ["asdf"]
        lesson_state.index = 0
        lesson_state.typed = "as"
        app = DummyApp(lesson_state)

        event = type("Event", (), {"unicode": "x", "key": None})()
        lesson_mode.process_lesson_typing(app, event)

        self.assertEqual(lesson_state.typed, "as")
        self.assertEqual(app.guidance_calls[-1], ("x", "asdf", "as"))

    def test_lesson_prompt_speaks_full_word_from_start(self):
        lesson_state = DummyLessonState(stage=0)
        lesson_state.batch_words = ["as"]
        lesson_state.index = 0
        lesson_state.typed = ""
        spoken = []
        app = DummyApp(lesson_state)
        app.speech = type("Speech", (), {"say": lambda _self, text, **_kwargs: spoken.append(text)})()

        lesson_mode.lesson_prompt(app)

        self.assertTrue(spoken[-1].startswith("Type "), spoken)
        self.assertIn("a", spoken[-1])

    def test_lesson_prompt_speaks_instruction_text_when_batch_instructions_set(self):
        lesson_state = DummyLessonState(stage=0)
        lesson_state.batch_words = ["Enter"]
        lesson_state.batch_instructions = ["Press the Enter key"]
        lesson_state.index = 0
        lesson_state.typed = ""
        spoken = []
        app = DummyApp(lesson_state)
        app.speech = type("Speech", (), {"say": lambda _self, text, **_kwargs: spoken.append(text)})()

        lesson_mode.lesson_prompt(app)

        self.assertEqual(spoken[-1], "Press the Enter key")

    def test_process_lesson_typing_special_key_wrong_press_speaks_correction(self):
        keys = sorted(lesson_manager.SPECIAL_KEY_NAMES.keys())
        # Find two keys with distinct names so pressed != target
        pressed_key_code = None
        target_name = None
        pressed_name = None
        for i, k in enumerate(keys):
            name_k = lesson_manager.SPECIAL_KEY_NAMES[k]
            for k2 in keys[i + 1:]:
                name_k2 = lesson_manager.SPECIAL_KEY_NAMES[k2]
                if name_k != name_k2:
                    pressed_key_code = k
                    pressed_name = name_k
                    target_name = name_k2
                    break
            if pressed_key_code is not None:
                break
        if pressed_key_code is None:
            self.skipTest("Could not find two special keys with distinct names")

        lesson_state = DummyLessonState(stage=0)
        lesson_state.batch_words = [target_name]
        lesson_state.batch_instructions = ["Press the key"]
        lesson_state.index = 0
        lesson_state.typed = ""
        spoken = []
        app = DummyApp(lesson_state)
        app.speech = type("Speech", (), {"say": lambda _self, text, **_kwargs: spoken.append(text)})()

        event = type("Event", (), {"key": pressed_key_code, "unicode": ""})()
        lesson_mode.process_lesson_typing(app, event)

        self.assertEqual(spoken[-1], f"That was {pressed_name}. Try {target_name}.")


if __name__ == "__main__":
    unittest.main()
