"""Starting a speed test does not change the saved Practice Topic.

Fable review 2026-11-10, modules finding 15. begin_test_typing assigned the
speed test's topic, including a randomly drawn one, to
settings.sentence_language, which is the Options "Practice Topic" setting and
is saved, so a learner who set Spanish found a different topic later.
"""

import types
import unittest
from unittest import mock

from modules import sentences_manager, test_modes
from modules.state_manager import Settings


class TestSpeedTestKeepsPracticeTopic(unittest.TestCase):
    def _begin(self, selected):
        app = mock.MagicMock()
        app.state.settings = Settings()
        app.state.settings.sentence_language = "Spanish"
        app.state.test = types.SimpleNamespace(
            duration_seconds=60, remaining=[], current="", typed="", correct_chars=0,
            total_chars=0, sentences_completed=0, sentences_started=0, running=False, start_time=0.0,
        )
        app.test_setup_selected_source = selected
        app.test_setup_topic_options = ["Random Topic", "English", "Science Facts"]
        with mock.patch.object(test_modes.random, "choice", return_value="Science Facts"), \
                mock.patch.object(sentences_manager, "load_practice_sentences_with_status",
                                  return_value=(["One sentence."], "")):
            test_modes.begin_test_typing(app)
        return app

    def test_a_random_topic_speed_test_leaves_the_setting_alone(self):
        app = self._begin("Random Topic")
        self.assertEqual(app.state.settings.sentence_language, "Spanish")
        self.assertEqual(app.speed_test_source, "Random Topic")

    def test_a_chosen_topic_speed_test_leaves_the_setting_alone(self):
        app = self._begin("English")
        self.assertEqual(app.state.settings.sentence_language, "Spanish")
        self.assertEqual(app.speed_test_source, "English")


if __name__ == "__main__":
    unittest.main()
