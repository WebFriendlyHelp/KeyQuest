import unittest

from modules import lesson_manager


# The keys each lesson introduces, in order. Pinned deliberately so that losing
# a lesson, reordering the progression, or dropping a key from one is a test
# failure here rather than something a learner discovers. Adding a lesson is a
# real change and should update this list on purpose, not by accident.
EXPECTED_LESSON_KEYS = [
    {" ", "a"}, {"s"}, {"d"}, {"f"}, {"j"}, {"k"}, {"l"}, {";"},
    {"g", "h"}, {"e", "r"}, {"u", "i"}, {"q", "w"}, {"o", "p"}, {"t", "y"},
    {"c", "v"}, {"n", "m"}, {"z", "x"}, {",", "."}, {"b"},
    {"1", "2", "3"}, {"4", "5", "6"}, {"7", "8", "9", "0"},
    {"'", "/"}, {"[", "]", "-", "="}, {"`", "\\"},
    {"tab"}, {"backspace", "delete"}, {"insert", "home", "end"},
    {"pageup", "pagedown"},
    {"f1", "f2", "f3", "f4"}, {"f5", "f6", "f7", "f8"}, {"f9", "f10", "f11", "f12"},
    {"capslock"},
]


class TestLessonContentIsIntact(unittest.TestCase):
    """Guards against silently losing lessons or the keys they teach."""

    def test_lesson_count_is_unchanged(self):
        self.assertEqual(
            len(lesson_manager.STAGE_LETTERS),
            len(EXPECTED_LESSON_KEYS),
            "the number of lessons changed; update EXPECTED_LESSON_KEYS only if "
            "that was intended",
        )

    def test_every_lesson_still_teaches_its_own_keys(self):
        for index, expected in enumerate(EXPECTED_LESSON_KEYS):
            with self.subTest(lesson=index):
                self.assertEqual(
                    lesson_manager.STAGE_LETTERS[index],
                    expected,
                    f"lesson {index} no longer introduces the keys it used to",
                )

    def test_every_lesson_still_has_a_name(self):
        for index in range(len(lesson_manager.STAGE_LETTERS)):
            with self.subTest(lesson=index):
                name = lesson_manager.LESSON_NAMES[index]
                self.assertTrue(name and name.strip(), f"lesson {index} has no name")

    def test_authored_practice_content_survives(self):
        """The hand-written words and phrases, not the generated ones."""
        self.assertTrue(lesson_manager.STAGE_WORDS, "authored lesson words are gone")
        self.assertTrue(lesson_manager.STAGE_PHRASES, "authored lesson phrases are gone")
        self.assertTrue(
            lesson_manager.SPECIAL_KEY_COMMANDS,
            "the special-key command drills are gone",
        )
        self.assertTrue(lesson_manager.KEY_LOCATIONS, "key location descriptions are gone")
        for stage, commands in lesson_manager.SPECIAL_KEY_COMMANDS.items():
            with self.subTest(stage=stage):
                self.assertTrue(commands, f"lesson {stage} lost its command drills")
                for spoken, key in commands:
                    self.assertTrue(spoken.strip(), f"lesson {stage} has an unspoken drill")
                    self.assertTrue(key.strip(), f"lesson {stage} has a drill with no key")


class TestLessonData(unittest.TestCase):
    def test_stage_letters_and_names_align(self):
        self.assertEqual(len(lesson_manager.STAGE_LETTERS), len(lesson_manager.LESSON_NAMES))
        self.assertGreater(len(lesson_manager.STAGE_LETTERS), 0)

    def test_stage_zero_contains_space_and_a(self):
        self.assertIn(" ", lesson_manager.STAGE_LETTERS[0])
        self.assertIn("a", lesson_manager.STAGE_LETTERS[0])

    def test_stage_keys_are_nonempty_strings(self):
        for stage_keys in lesson_manager.STAGE_LETTERS:
            self.assertTrue(stage_keys)
            for key in stage_keys:
                self.assertIsInstance(key, str)
                self.assertNotEqual(key, "")

    def test_key_locations_align_with_actual_lessons(self):
        self.assertEqual(lesson_manager.KEY_LOCATIONS[4]["keys"], "j")
        self.assertEqual(lesson_manager.KEY_LOCATIONS[5]["keys"], "k")
        self.assertEqual(lesson_manager.KEY_LOCATIONS[6]["keys"], "l")
        self.assertEqual(lesson_manager.KEY_LOCATIONS[7]["keys"], ";")

    def test_authored_words_and_phrases_only_use_introduced_keys(self):
        for stage, words in lesson_manager.STAGE_WORDS.items():
            for word in words:
                self.assertTrue(
                    lesson_manager.content_uses_only_introduced_keys(stage, word),
                    msg=f"Stage {stage} word uses future keys: {word}",
                )

        for stage, phrases in lesson_manager.STAGE_PHRASES.items():
            for phrase in phrases:
                self.assertTrue(
                    lesson_manager.content_uses_only_introduced_keys(stage, phrase),
                    msg=f"Stage {stage} phrase uses future keys: {phrase}",
                )


if __name__ == "__main__":
    unittest.main()
