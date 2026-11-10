from modules import badge_manager
from modules import challenge_manager
from modules import dashboard_manager
from modules import key_analytics
from modules import quest_manager
from modules import dialog_manager
from modules import error_logging


def show_badge_viewer(app) -> None:
    """Show all earned and locked badges."""
    badge_list = badge_manager.format_badge_list(
        earned_badges=app.state.settings.earned_badges,
        show_locked=True,
    )

    earned_count = len(app.state.settings.earned_badges)
    total_count = badge_manager.get_badge_count()
    announcement = f"Your Badges. You have earned {earned_count} of {total_count} badges."
    app.speech.say(announcement, priority=True, protect_seconds=2.0)

    app.show_info_dialog("Your Badges", badge_list)
    app._return_to_main_menu()


def show_quest_viewer(app) -> None:
    """Show active and completed quests."""
    quest_list = quest_manager.format_quest_list(app.state.settings, show_inactive=True)

    active_count = len(
        [
            q
            for q in app.state.settings.active_quests
            if q not in app.state.settings.completed_quests
        ]
    )
    completed_count = len(app.state.settings.completed_quests)
    announcement = f"Your Quests. {active_count} active quests, {completed_count} completed."
    app.speech.say(announcement, priority=True, protect_seconds=2.0)

    app.show_info_dialog("Your Quests", quest_list)
    app._return_to_main_menu()


def show_progress_dashboard(app) -> None:
    """Show comprehensive progress dashboard."""
    dashboard_text = dashboard_manager.format_dashboard(app.state.settings)

    announcement = (
        f"Progress Dashboard. Level {app.state.settings.level}. "
        f"{app.state.settings.total_lessons_completed} lessons completed."
    )
    app.speech.say(announcement, priority=True, protect_seconds=2.0)

    app.show_info_dialog("Progress Dashboard", dashboard_text)
    app._return_to_main_menu()


def show_practice_log(app) -> None:
    """Show recent practice history."""
    log_text = dashboard_manager.format_practice_log(app.state.settings)
    app.speech.say("Practice Log.", priority=True, protect_seconds=2.0)
    app.show_info_dialog("Practice Log", log_text)
    if dialog_manager.show_yes_no_dialog(
        "Copy Practice Log",
        "Would you like to copy the practice log to the clipboard?",
        yes_label="Copy Log",
        no_label="Close",
    ):
        # The shared Win32 helper, never a tkinter root window (CLAUDE.md).
        if error_logging.copy_text_to_clipboard(log_text):
            app.speech.say("Practice log copied to clipboard.", priority=True)
        else:
            app.speech.say("Unable to copy the practice log to clipboard.", priority=True)
    app._return_to_main_menu()


def show_daily_challenge(app) -> None:
    """Show today's daily challenge."""
    if challenge_manager.check_if_new_day(app.state.settings):
        challenge_manager.reset_daily_challenge(app.state.settings)
        app.save_progress()

    challenge_text = challenge_manager.format_challenge_announcement(app.state.settings)
    if app.state.settings.daily_challenge_completed:
        challenge_text += "\n\nStatus: Completed today."
    else:
        challenge_text += "\n\nStatus: Not completed yet."

    challenge = challenge_manager.get_today_challenge()
    if app.state.settings.daily_challenge_completed:
        announcement = f"Daily Challenge Complete! {challenge['name']}."
    else:
        announcement = (
            f"Today's Daily Challenge: {challenge['name']}. {challenge['description']}."
        )
    app.speech.say(announcement, priority=True, protect_seconds=2.0)

    app.show_info_dialog("Daily Challenge", challenge_text)
    app._return_to_main_menu()


def show_key_performance_report(app) -> None:
    """Show keyboard performance analytics."""
    report_text = key_analytics.format_key_performance_report(app.state.settings, min_attempts=5)

    problem_keys = key_analytics.get_problem_keys(app.state.settings, min_attempts=5)
    if problem_keys:
        announcement = f"Key Performance Report. {len(problem_keys)} keys need practice."
    else:
        announcement = "Key Performance Report. All keys performing well!"
    app.speech.say(announcement, priority=True, protect_seconds=2.0)

    app.show_info_dialog("Key Performance Report", report_text)
    app._return_to_main_menu()
