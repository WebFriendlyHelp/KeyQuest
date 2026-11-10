"""Notifications and progress views use one channel: the dialog.

Fable review modules finding 5 (Casey's decision, 2026-11-10). These spoke a
line and then opened a dialog carrying the same news, which CLAUDE.md rules
out: the screen reader announces the dialog on the focus change and cuts the
spoken line off. The coin awards existed only in that cut-off speech, so a
learner never reliably heard them. Now nothing is spoken before the dialog,
and whatever was speech-only is in the dialog text.

These check what reaches Speech.say and show_info_dialog with stubs. They
prove the order and the text, not what NVDA voices when the dialog opens.
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import badge_manager, notifications, progress_views, quest_manager
from modules.state_manager import Settings


class _App:
    def __init__(self):
        self.state = types.SimpleNamespace(settings=Settings())
        self.events = []
        self.speech = types.SimpleNamespace(say=lambda text, **k: self.events.append(("say", text)))
        self.audio = types.SimpleNamespace(
            play_badge=lambda: None, play_levelup=lambda: None, play_quest=lambda: None
        )

    def show_info_dialog(self, title, content):
        self.events.append(("dialog", title, content))

    def save_progress(self):
        pass

    def _return_to_main_menu(self):
        self.events.append(("menu",))

    def spoken_before_first_dialog(self):
        out = []
        for event in self.events:
            if event[0] == "dialog":
                break
            if event[0] == "say":
                out.append(event[1])
        return out

    def dialogs(self):
        return [e for e in self.events if e[0] == "dialog"]


class TestNotifications(unittest.TestCase):
    def test_badge_coins_are_in_the_dialog_and_nothing_is_spoken_first(self):
        app = _App()
        badge_id = next(iter(badge_manager.BADGES))
        app.state.settings.earned_badges.add(badge_id)
        app.state.settings.badge_notifications.append(badge_id)

        notifications.show_badge_notifications(app)

        self.assertEqual(app.spoken_before_first_dialog(), [])
        (_, title, content), = app.dialogs()
        self.assertIn("50 coins", content)
        self.assertIn(badge_manager.get_badge_info(badge_id)["name"], content)
        self.assertEqual(app.state.settings.coins, 50)

    def test_level_up_coins_are_in_the_dialog(self):
        app = _App()
        notifications.show_level_up_notification(
            app, {"leveled_up": True, "new_level": 3, "level_name": "Apprentice", "total_xp": 1200}
        )
        self.assertEqual(app.spoken_before_first_dialog(), [])
        (_, _title, content), = app.dialogs()
        self.assertIn("100 coins", content)

    def test_no_level_up_shows_nothing(self):
        # Negative twin: no dialog and no coins when there was no level up.
        app = _App()
        notifications.show_level_up_notification(app, {"leveled_up": False})
        self.assertEqual(app.events, [])
        self.assertEqual(app.state.settings.coins, 0)

    def test_quest_coins_are_in_the_dialog(self):
        app = _App()
        quest_id = next(iter(quest_manager.QUESTS))
        app.state.settings.quest_notifications.append(quest_id)

        notifications.show_quest_notifications(app)

        self.assertEqual(app.spoken_before_first_dialog(), [])
        (_, _title, content), = app.dialogs()
        self.assertIn("75 coins", content)
        self.assertIn(quest_manager.get_quest_info(quest_id)["name"], content)


class TestProgressViews(unittest.TestCase):
    VIEWS = (
        "show_badge_viewer",
        "show_quest_viewer",
        "show_progress_dashboard",
        "show_daily_challenge",
        "show_key_performance_report",
    )

    def test_no_view_speaks_before_its_dialog(self):
        for name in self.VIEWS:
            with self.subTest(view=name):
                app = _App()
                getattr(progress_views, name)(app)
                self.assertEqual(app.spoken_before_first_dialog(), [])
                self.assertEqual(len(app.dialogs()), 1)

    def test_practice_log_speaks_nothing_before_its_dialog(self):
        from unittest import mock

        app = _App()
        with mock.patch.object(progress_views.dialog_manager, "show_yes_no_dialog", return_value=False):
            progress_views.show_practice_log(app)
        self.assertEqual(app.spoken_before_first_dialog(), [])

    def test_quest_counts_are_in_the_quest_dialog(self):
        # The counts were spoken only; the list itself does not total them.
        app = _App()
        progress_views.show_quest_viewer(app)
        (_, _title, content), = app.dialogs()
        self.assertIn("active quests", content)
        self.assertIn("completed", content)


if __name__ == "__main__":
    unittest.main()
