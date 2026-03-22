import unittest

from modules import dashboard_manager


class _Settings:
    def __init__(self, session_history):
        self.session_history = session_history


class TestPracticeLogFormatting(unittest.TestCase):
    def test_day_summary_names_the_activity_and_uses_clear_day_comparison(self):
        settings = _Settings(
            [
                {
                    "type": "speed_test",
                    "summary": "Speed Test (English)",
                    "timestamp": "2026-03-08T15:19:00",
                    "date": "2026-03-08",
                    "time": "3:19 PM",
                    "duration": 300,
                    "wpm": 50.1,
                    "accuracy": 93.8,
                },
                {
                    "type": "speed_test",
                    "summary": "Speed Test (English)",
                    "timestamp": "2026-03-09T15:19:00",
                    "date": "2026-03-09",
                    "time": "3:19 PM",
                    "duration": 129,
                    "wpm": 37.5,
                    "accuracy": 37.5,
                },
            ]
        )

        log_text = dashboard_manager.format_practice_log(settings)

        self.assertIn("1 activity: Speed Test (English).", log_text)
        self.assertIn(
            "Compared with your previous recorded practice day, today was 12.6 WPM slower on average",
            log_text,
        )
        self.assertIn("today was 56.3 accuracy points lower in accuracy.", log_text)

    def test_session_entry_compares_to_last_similar_activity(self):
        settings = _Settings(
            [
                {
                    "type": "speed_test",
                    "summary": "Speed Test (English)",
                    "timestamp": "2026-03-08T15:19:00",
                    "date": "2026-03-08",
                    "time": "3:19 PM",
                    "duration": 300,
                    "wpm": 45.0,
                    "accuracy": 90.0,
                },
                {
                    "type": "speed_test",
                    "summary": "Speed Test (English)",
                    "timestamp": "2026-03-09T15:19:00",
                    "date": "2026-03-09",
                    "time": "3:19 PM",
                    "duration": 180,
                    "wpm": 48.5,
                    "accuracy": 92.0,
                },
            ]
        )

        log_text = dashboard_manager.format_practice_log(settings)

        self.assertIn(
            "Change: this was 3.5 WPM faster than your last Speed Test (English).",
            log_text,
        )
        self.assertIn(
            "accuracy was 2.0 accuracy points higher than your last Speed Test (English).",
            log_text,
        )

    def test_session_entry_reports_escape_ended_early_status(self):
        settings = _Settings(
            [
                {
                    "type": "game",
                    "summary": "Letter Fall",
                    "timestamp": "2026-03-09T15:19:00",
                    "date": "2026-03-09",
                    "time": "3:19 PM",
                    "duration": 75,
                    "ended_early": True,
                    "exit_reason": "escape",
                },
            ]
        )

        log_text = dashboard_manager.format_practice_log(settings)

        self.assertIn("Status: Ended early with Escape.", log_text)


if __name__ == "__main__":
    unittest.main()
