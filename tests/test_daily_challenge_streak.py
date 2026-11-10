"""A skipped daily challenge ends the streak.

Fable review 2026-11-10, modules finding 12. daily_challenge_date was
refreshed whenever the app opened on a new day, and the streak reset only when
more than one day had passed since that date, so opening the app yesterday
without finishing the challenge kept the streak alive.
"""

import datetime
import unittest

from modules import challenge_manager
from modules.state_manager import Settings


def _settings(streak, last_date, completed):
    settings = Settings()
    settings.daily_challenge_streak = streak
    settings.daily_challenge_date = last_date.isoformat()
    settings.daily_challenge_completed = completed
    return settings


class TestStreak(unittest.TestCase):
    def test_yesterday_opened_but_not_completed_breaks_the_streak(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        settings = _settings(5, yesterday, completed=False)
        challenge_manager.reset_daily_challenge(settings)
        self.assertEqual(settings.daily_challenge_streak, 0)

    def test_yesterday_completed_keeps_the_streak(self):
        """Negative twin."""
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        settings = _settings(5, yesterday, completed=True)
        challenge_manager.reset_daily_challenge(settings)
        self.assertEqual(settings.daily_challenge_streak, 5)
        self.assertFalse(settings.daily_challenge_completed)

    def test_two_days_away_breaks_the_streak(self):
        settings = _settings(5, datetime.date.today() - datetime.timedelta(days=2), completed=True)
        challenge_manager.reset_daily_challenge(settings)
        self.assertEqual(settings.daily_challenge_streak, 0)


if __name__ == "__main__":
    unittest.main()
