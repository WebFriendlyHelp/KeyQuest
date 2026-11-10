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

    # One channel: the dialog. Nothing is spoken first, because the screen
    # reader cuts a spoken line off when it announces the dialog (CLAUDE.md).
    # The badge list already says how many are earned.
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
    # One channel: the dialog (see show_badge_viewer). The counts were spoken
    # only, so they lead the dialog text.
    summary = f"{active_count} active quests, {completed_count} completed."
    app.show_info_dialog("Your Quests", f"{summary}\n\n{quest_list}")
    app._return_to_main_menu()


def show_progress_dashboard(app) -> None:
    """Show comprehensive progress dashboard."""
    dashboard_text = dashboard_manager.format_dashboard(app.state.settings)

    # One channel: the dialog (see show_badge_viewer). The dashboard text
    # already gives the level and lessons completed.
    app.show_info_dialog("Progress Dashboard", dashboard_text)
    app._return_to_main_menu()


def show_practice_log(app) -> None:
    """Show recent practice history."""
    log_text = dashboard_manager.format_practice_log(app.state.settings)
    # One channel: the dialog, whose title is "Practice Log".
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

    # One channel: the dialog (see show_badge_viewer). The challenge text
    # already names the challenge and its status.
    app.show_info_dialog("Daily Challenge", challenge_text)
    app._return_to_main_menu()


def show_key_performance_report(app) -> None:
    """Show keyboard performance analytics."""
    report_text = key_analytics.format_key_performance_report(app.state.settings, min_attempts=5)

    # One channel: the dialog (see show_badge_viewer). The report lists the
    # keys that need practice.
    app.show_info_dialog("Key Performance Report", report_text)
    app._return_to_main_menu()
