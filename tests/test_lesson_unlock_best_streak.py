"""The lesson unlock looks at the best streak reached in the lesson.

Casey's decision, 2026-11-10: one late typo should not undo a lesson that
was typed at high accuracy. The streak used to be read only at the end,
so 80 correct keys, one slip and one last correct key gave a streak of 1
and "Keep practicing" at 98.8 percent accuracy.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.state_manager import AdaptiveTracker


def _type(tracker: AdaptiveTracker, keys: str, correct: bool = True) -> None:
    for key in keys:
        tracker.record_keystroke(key, correct)


class TestBestStreakUnlock(unittest.TestCase):
    def test_one_late_typo_after_a_long_clean_run_still_advances(self) -> None:
        tracker = AdaptiveTracker()
        _type(tracker, "asdf" * 20)
        _type(tracker, "j", correct=False)
        _type(tracker, "a")

        self.assertGreater(tracker.overall_accuracy(), 0.95)
        self.assertEqual(tracker.consecutive_correct, 1)
        self.assertTrue(tracker.should_advance())

    def test_no_run_of_three_anywhere_still_does_not_advance(self) -> None:
        # Negative twin: the streak requirement still exists. Alternate one
        # correct key and one miss, so no run ever reaches three.
        tracker = AdaptiveTracker()
        for key in "asdfasdfasdf":
            tracker.record_keystroke(key, True)
            tracker.record_keystroke("x", False)
        self.assertFalse(tracker.should_advance())

    def test_a_long_run_does_not_rescue_low_accuracy(self) -> None:
        tracker = AdaptiveTracker()
        _type(tracker, "asdf")
        _type(tracker, "qwerty" * 3, correct=False)
        self.assertLess(tracker.overall_accuracy(), 0.80)
        self.assertFalse(tracker.should_advance())

    def test_best_streak_is_not_counted_on_repeated_keys(self) -> None:
        # The end-of-lesson streak ignored repeats of the same key; the best
        # streak must follow the same rule or "aaaa" would unlock a lesson.
        tracker = AdaptiveTracker()
        _type(tracker, "aaaaaaa")
        self.assertFalse(tracker.should_advance())


if __name__ == "__main__":
    unittest.main()
