"""Hangman sentence practice never asks for text the keyboard cannot type.

Fable review 2026-11-10, ui finding 14. The "definition" templates pasted the
raw dictionary definition into a sentence that must be typed exactly. 1.7
percent of definitions contain non-ASCII characters and the longest is 1,073
characters, and there is no skip key, so the learner was stuck.

The length cap (120 characters) is a judgment call, recorded in the report.
"""

import unittest
from unittest import mock

from games.hangman import build_sentence_practice_items


class TestDefinitionSentences(unittest.TestCase):
    def _all_sentences(self, definition):
        sentences = set()
        for seed in range(40):
            with mock.patch("games.hangman.random.shuffle", lambda seq: seq.reverse() if seed % 2 else None), \
                    mock.patch("games.hangman.random.choice", side_effect=lambda seq: seq[seed % len(seq)]):
                sentences.update(build_sentence_practice_items("cafe", definition, count=21))
        return sentences

    def test_a_non_ascii_definition_is_never_typed(self):
        sentences = self._all_sentences("a small restaurant serving café au lait")
        self.assertTrue(sentences)
        self.assertFalse(any("café" in s for s in sentences), sentences)
        self.assertTrue(all(s.isascii() for s in sentences))

    def test_a_very_long_definition_is_never_typed(self):
        long_definition = "a word " * 100
        sentences = self._all_sentences(long_definition)
        self.assertTrue(all(len(s) < 200 for s in sentences), max(sentences, key=len))

    def test_a_short_plain_definition_is_still_used(self):
        """Negative twin: ordinary definitions keep their template."""
        sentences = self._all_sentences("a small restaurant")
        self.assertTrue(any("a small restaurant" in s for s in sentences), sentences)


if __name__ == "__main__":
    unittest.main()
