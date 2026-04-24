import unittest

import pygame

from modules import test_modes


class _DummySpeech:
    def __init__(self):
        self.messages = []

    def say(self, text, priority=False, protect_seconds=0.0):
        self.messages.append(text)


class _DummyAudio:
    def __init__(self):
        self.bad_count = 0
        self.success_count = 0

    def beep_bad(self):
        self.bad_count += 1

    def play_success(self):
        self.success_count += 1


class _DummyTestState:
    def __init__(self, current, typed=""):
        self.current = current
        self.typed = typed
        self.running = True
        self.start_time = 0.0
        self.correct_chars = 0
        self.total_chars = 0
        self.sentences_completed = 0
        self.remaining = []


class _DummyState:
    def __init__(self, test_state):
        self.test = test_state
        self.mode = "TEST_SETUP"
        self.settings = type("Settings", (), {"sentence_language": "English"})()


class _DummyApp:
    def __init__(self, current, typed=""):
        self.state = _DummyState(_DummyTestState(current=current, typed=typed))
        self.speech = _DummySpeech()
        self.audio = _DummyAudio()
        self.test_setup_topic_options = ["Random Topic", "English", "Spanish"]
        self.test_setup_topic_index = 0
        self.test_setup_view = "topics"
        self.test_setup_selected_source = "Random Topic"
        self.pending_compose_mark = None

    def load_next_sentence(self):
        raise AssertionError("load_next_sentence should not be called in this test")

    def load_next_practice_sentence(self):
        raise AssertionError("load_next_practice_sentence should not be called in this test")

    def trigger_flash(self, color, duration=0.12):
        pass


class _DummyEvent:
    def __init__(self, unicode="", key=None):
        self.unicode = unicode
        self.key = key


class TestTestModesAnnouncements(unittest.TestCase):
    def test_speed_test_mistake_spells_then_reads_remaining(self):
        app = _DummyApp(current="aa bb")
        test_modes.process_test_typing(app, _DummyEvent("x"))

        self.assertEqual(app.audio.bad_count, 1)
        self.assertEqual(app.state.test.total_chars, 1)
        self.assertEqual(
            app.speech.messages[-1],
            "Type: a, a. Then: bb",
        )

    def test_sentence_practice_mistake_spells_then_reads_remaining(self):
        app = _DummyApp(current="cat sat", typed="c")
        test_modes.process_practice_typing(app, _DummyEvent("x"))

        self.assertEqual(app.audio.bad_count, 1)
        self.assertEqual(app.state.test.total_chars, 1)
        self.assertEqual(
            app.speech.messages[-1],
            "Type: a, t. Then: sat",
        )

    def test_repeat_remaining_uses_same_feedback_format(self):
        app = _DummyApp(current="aa bb", typed="a")
        test_modes.speak_test_remaining(app)
        self.assertEqual(
            app.speech.messages[-1],
            "Type: a. Then: bb",
        )

    def test_speed_test_setup_uses_english_label(self):
        app = _DummyApp(current="")

        test_modes.start_test(app)

        self.assertEqual(
            app.speech.messages[-1],
            "Speed test setup. General. Use Up and Down to choose a sentence source. Press Enter to continue. Escape returns to menu.",
        )

    def test_speed_test_setup_announces_random_topic_label(self):
        app = _DummyApp(current="")
        app.test_setup_topic_index = 1

        test_modes.handle_test_setup_input(app, _DummyEvent(key=pygame.K_UP))

        self.assertEqual(app.speech.messages[-1], "Random Topic")

    def test_speed_test_setup_can_announce_topic_choices(self):
        app = _DummyApp(current="")
        app.test_setup_topic_index = 1

        test_modes.handle_test_setup_input(app, _DummyEvent(key=pygame.K_RETURN))

        self.assertEqual(
            app.speech.messages[-1],
            "General. How many minutes? Type a number and press Enter.",
        )

    def test_speed_test_setup_can_announce_random_topic_duration_prompt(self):
        app = _DummyApp(current="")
        app.test_setup_topic_index = 0

        test_modes.handle_test_setup_input(app, _DummyEvent(key=pygame.K_RETURN))

        self.assertEqual(
            app.speech.messages[-1],
            "Random Topic. How many minutes? Type a number and press Enter.",
        )

    def test_speed_test_supports_ctrl_quote_acute_compose(self):
        app = _DummyApp(current="áéíóú.")

        test_modes.handle_test_input(app, _DummyEvent(key=pygame.K_QUOTE), pygame.KMOD_CTRL)
        for vowel in "aeiou":
            test_modes.handle_test_input(app, _DummyEvent(unicode=vowel), 0)
            if vowel != "u":
                test_modes.handle_test_input(app, _DummyEvent(key=pygame.K_QUOTE), pygame.KMOD_CTRL)

        self.assertEqual(app.state.test.typed, "áéíóú")
        self.assertIsNone(app.pending_compose_mark)

    def test_speed_test_accepts_direct_spanish_unicode_input(self):
        app = _DummyApp(current="teléfono.")

        for ch in "teléfono":
            test_modes.handle_test_input(app, _DummyEvent(unicode=ch), 0)

        self.assertEqual(app.state.test.typed, "teléfono")

    def test_sentence_practice_supports_ctrl_backquote_tilde_compose(self):
        app = _DummyApp(current="ñ.")

        test_modes.handle_practice_input(app, _DummyEvent(key=pygame.K_BACKQUOTE), pygame.KMOD_CTRL)
        test_modes.handle_practice_input(app, _DummyEvent(unicode="n"), 0)

        self.assertEqual(app.state.test.typed, "ñ")
        self.assertIsNone(app.pending_compose_mark)

    def test_sentence_practice_supports_ctrl_shift_1_inverted_exclamation(self):
        app = _DummyApp(current="¡hola!!")

        test_modes.handle_practice_input(app, _DummyEvent(key=pygame.K_1), pygame.KMOD_CTRL | pygame.KMOD_SHIFT)
        for ch in "hola!":
            test_modes.handle_practice_input(app, _DummyEvent(unicode=ch), 0)

        self.assertEqual(app.state.test.typed, "¡hola!")

    def test_sentence_practice_supports_diaeresis_and_inverted_punctuation_compose(self):
        app = _DummyApp(current="¿pingüino!!")

        test_modes.handle_practice_input(app, _DummyEvent(key=pygame.K_SLASH), pygame.KMOD_CTRL | pygame.KMOD_SHIFT)
        for ch in "ping":
            test_modes.handle_practice_input(app, _DummyEvent(unicode=ch), 0)
        test_modes.handle_practice_input(app, _DummyEvent(key=pygame.K_QUOTE), pygame.KMOD_CTRL | pygame.KMOD_SHIFT)
        test_modes.handle_practice_input(app, _DummyEvent(unicode="u"), 0)
        for ch in "ino!":
            test_modes.handle_practice_input(app, _DummyEvent(unicode=ch), 0)

        self.assertEqual(app.state.test.typed, "¿pingüino!")


class TestPracticeTopicRandomization(unittest.TestCase):
    def test_random_topic_pool_excludes_spanish_topics(self):
        topics = ["English", "Spanish", "Windows Commands", "Spanish Sentences"]
        pool = test_modes._get_random_topic_pool(topics)
        self.assertEqual(pool, ["English", "Windows Commands"])

    def test_random_topic_pool_excludes_non_english_topics(self):
        topics = ["English", "French Fortune", "Windows Commands", "Spanish", "German Basics"]
        pool = test_modes._get_random_topic_pool(topics)
        self.assertEqual(pool, ["English", "Windows Commands"])

    def test_random_topic_pool_keeps_english_named_topics(self):
        topics = ["English Fortune", "Windows Commands", "English Stories", "Spanish"]
        pool = test_modes._get_random_topic_pool(topics)
        self.assertEqual(pool, ["English Fortune", "Windows Commands", "English Stories"])

    def test_random_topic_pool_falls_back_when_only_spanish(self):
        topics = ["Spanish", "Spanish Sentences"]
        pool = test_modes._get_random_topic_pool(topics)
        self.assertEqual(pool, topics)

    def test_speed_test_source_options_put_general_random_and_spanish_first(self):
        original_folder_topics = test_modes.sentences_manager.get_sentence_topics_from_folder
        original_practice_topics = test_modes.sentences_manager.get_practice_topics
        try:
            test_modes.sentences_manager.get_sentence_topics_from_folder = (
                lambda app_dir="": ["English", "Spanish", "Windows Commands", "Science Facts"]
            )
            test_modes.sentences_manager.get_practice_topics = (
                lambda app_dir="": ["English", "Spanish", "Windows Commands", "Science Facts"]
            )
            self.assertEqual(
                test_modes._get_speed_test_source_options(),
                ["English", "Random Topic", "Spanish", "Windows Commands", "Science Facts"],
            )
        finally:
            test_modes.sentences_manager.get_sentence_topics_from_folder = original_folder_topics
            test_modes.sentences_manager.get_practice_topics = original_practice_topics


if __name__ == "__main__":
    unittest.main()
