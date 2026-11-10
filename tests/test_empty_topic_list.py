"""An empty Sentences folder does not crash the app.

Fable review 2026-11-10, modules finding 16. With no topics, cycling Practice
Topic in Options divided by zero, and Sentence Practice's Random Topic and
topic browsing raised IndexError inside handle_event, which ends the app.
"""

import types
import unittest
from unittest import mock

import pygame

from modules import menu_handler, sentences_manager, test_modes
from modules.state_manager import Settings


class TestEmptyTopicList(unittest.TestCase):
    def test_cycling_practice_topic_with_no_topics_keeps_the_current_one(self):
        with mock.patch.object(sentences_manager, "get_practice_topics", return_value=[]):
            self.assertEqual(menu_handler.cycle_language("English", "right"), "English")

    def test_cycling_with_topics_still_moves(self):
        """Negative twin."""
        with mock.patch.object(sentences_manager, "get_practice_topics", return_value=["English", "Spanish"]):
            self.assertEqual(menu_handler.cycle_language("English", "right"), "Spanish")

    def _practice_app(self):
        app = mock.MagicMock()
        app.state.settings = Settings()
        with mock.patch.object(sentences_manager, "get_sentence_topics_from_folder", return_value=[]), \
                mock.patch.object(sentences_manager, "get_practice_topics", return_value=[]):
            test_modes.start_practice(app)
        return app

    def test_random_topic_with_no_topics_does_not_raise(self):
        app = self._practice_app()
        app.practice_setup_index = 0  # Random Topic
        test_modes.handle_practice_setup_input(app, types.SimpleNamespace(key=pygame.K_RETURN), 0)
        self.assertEqual(app.state.mode, "PRACTICE")
        self.assertTrue(app.practice_sentences, "built-in sentences stand in")

    def test_choose_topic_with_no_topics_does_not_raise(self):
        app = self._practice_app()
        app.practice_setup_index = 1  # Choose Topic
        test_modes.handle_practice_setup_input(app, types.SimpleNamespace(key=pygame.K_RETURN), 0)
        test_modes.handle_practice_setup_input(app, types.SimpleNamespace(key=pygame.K_DOWN), 0)


if __name__ == "__main__":
    unittest.main()
