import unittest

from modules import speech_format


class TestSpeechFormat(unittest.TestCase):
    def test_spell_text_spaces_and_repeated_letters(self):
        self.assertEqual(speech_format.spell_text("aa"), "a, a")
        self.assertEqual(speech_format.spell_text("a a"), "a, space, a")

    def test_spell_text_for_typing_instruction_compacts_repeated_identical_letters(self):
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("aa"),
            "a twice",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("aaa"),
            "a 3 times",
        )

    def test_spell_text_for_typing_instruction_keeps_plain_words_natural(self):
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("sad", natural_words={"sad", "dad"}),
            "sad",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("dad", natural_words={"sad", "dad"}),
            "dad",
        )

    def test_spell_text_for_typing_instruction_spells_non_words(self):
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("a a"),
            "a, space, a",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("df"),
            "d, f",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("sAA"),
            "s, a, a",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("aass"),
            "a, a, s, s",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("asas", natural_words={"sad", "dad"}),
            "a, s, a, s",
        )

    def test_natural_phrase_names_the_space_between_words(self):
        """Reported bug: lesson 0 said "a a" for a target needing a, space, a.

        Both tokens are authored natural words, so the phrase was read out as
        plain text and the space bar was never mentioned. The learner pressed A
        twice, got an error, and only then was told to press space.
        """
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("a a", natural_words={"a"}),
            "a, space, a",
        )
        # Lesson 1, where S is introduced and "as" becomes an authored word.
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("as a", natural_words={"a", "as"}),
            "as, space, a",
        )
        # Authored multi-word phrases from STAGE_PHRASES take the same treatment.
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("a lad", natural_words={"a", "lad"}),
            "a, space, lad",
        )

    def test_single_natural_word_is_unchanged(self):
        """The space joiner must not disturb prompts that have no space in them."""
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("salad", natural_words={"salad"}),
            "salad",
        )

    def test_partially_typed_target_still_names_a_leading_space(self):
        """After typing "a" of "a a", the remaining text is " a".

        The only key left that the learner cannot guess is the space, so an
        empty leading token must fall through to spelling rather than being
        dropped silently.
        """
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction(" a", natural_words={"a"}),
            "space, a",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("a ", natural_words={"a"}),
            "a, space",
        )
        self.assertEqual(
            speech_format.spell_text_for_typing_instruction("a  a", natural_words={"a"}),
            "a, space, space, a",
        )

    def test_every_space_in_a_prompt_is_announced(self):
        """Invariant, not a fixed string: a space in the target is always spoken.

        Asserted over the shapes the lesson generator actually produces, so a
        future change to the natural-word rules cannot quietly reintroduce a
        prompt whose spaces are silent.
        """
        natural = {"a", "as", "sad", "lad", "all", "fall"}
        targets = [
            "a a", "a as", "as a", "as as", "a a a", "sad lad",
            "all fall", "a sad lad", " a", "a ", "a  a", "zz a", "a zz",
        ]
        for target in targets:
            with self.subTest(target=target):
                spoken = speech_format.spell_text_for_typing_instruction(
                    target, natural_words=natural
                )
                self.assertEqual(
                    spoken.count("space"),
                    target.count(" "),
                    f"{target!r} was announced as {spoken!r}",
                )

    def test_build_remaining_text_feedback(self):
        msg = speech_format.build_remaining_text_feedback("a a")
        self.assertEqual(msg, "Type: a. Then: a")

    def test_build_remaining_text_feedback_names_the_space_at_a_word_boundary(self):
        """Pausing between words used to be reported as "Type: nothing."

        In sentence practice and the speed test the remainder is the untyped
        suffix, so stopping after a word leaves a leading space. Splitting on
        it produced an empty first word, and spelling that returned the word
        "nothing" instead of naming the space bar the typist actually needs.
        """
        self.assertEqual(
            speech_format.build_remaining_text_feedback(" world"),
            "Type: space. Then: world",
        )
        self.assertEqual(
            speech_format.build_remaining_text_feedback(" "),
            "Type: space.",
        )

    def test_build_remaining_text_feedback_never_says_nothing_for_real_text(self):
        """Invariant: only genuinely empty input may be reported as nothing left."""
        for remaining in [" world", " ", "  x", "a a", "world", " a b c"]:
            with self.subTest(remaining=remaining):
                message = speech_format.build_remaining_text_feedback(remaining)
                self.assertNotIn(
                    "nothing",
                    message.lower(),
                    f"{remaining!r} still has text left but was announced as {message!r}",
                )

    def test_build_remaining_text_feedback_preserves_caps_and_punctuation_in_first_word(self):
        msg = speech_format.build_remaining_text_feedback("Hello, world.")
        self.assertEqual(
            msg,
            "Type: capital h, e, l, l, o, comma. Then: world.",
        )


if __name__ == "__main__":
    unittest.main()
