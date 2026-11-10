from modules import badge_manager
from modules import currency_manager
from modules import quest_manager


def show_badge_notifications(app) -> None:
    """Show any pending badge unlock notifications."""
    while app.state.settings.badge_notifications:
        badge_id = app.state.settings.badge_notifications.pop(0)
        badge = badge_manager.get_badge_info(badge_id)

        message = (
            f"Badge Unlocked!\n\n"
            f"{badge['name']}\n\n"
            f"{badge['description']}\n\n"
            f"You now have {len(app.state.settings.earned_badges)} "
            f"of {badge_manager.get_badge_count()} badges!"
        )

        app.audio.play_badge()

        # One channel: the dialog. A line spoken just before it is cut off when
        # the screen reader announces the dialog (CLAUDE.md), and the coins
        # used to be in that speech only.
        coins_earned = currency_manager.award_coins(app.state.settings, "badge_earned")
        if coins_earned:
            message += f"\n\nYou earned {coins_earned} coins."

        app.show_info_dialog("Badge Unlocked", message)
        app.save_progress()


def show_level_up_notification(app, xp_result: dict) -> None:
    """Show level-up notification."""
    if not xp_result.get("leveled_up", False):
        return

    app.audio.play_levelup()

    # One channel: the dialog (see show_badge_notifications).
    coins_earned = currency_manager.award_coins(app.state.settings, "level_up")
    coins_line = f"You earned {coins_earned} coins.\n\n" if coins_earned else ""
    message = (
        f"Use Up and Down arrows to read this.\n"
        f"Press Enter to continue.\n\n"
        f"LEVEL UP!\n\n"
        f"Level {xp_result['new_level']}: {xp_result['level_name']}\n\n"
        f"Total XP: {xp_result['total_xp']:,}\n\n"
        f"{coins_line}"
        f"Keep practicing to reach the next level!\n\n"
        f"Press Enter to continue."
    )

    app.show_info_dialog("Level Up!", message)
    app.save_progress()


def show_quest_notifications(app) -> None:
    """Show any pending quest completion notifications."""
    while app.state.settings.quest_notifications:
        quest_id = app.state.settings.quest_notifications.pop(0)

        message = quest_manager.format_quest_completion(quest_id)

        app.audio.play_quest()

        # One channel: the dialog (see show_badge_notifications). The quest
        # name and XP are already in the completion text.
        quest = quest_manager.get_quest_info(quest_id)
        if quest:
            coins_earned = currency_manager.award_coins(app.state.settings, "quest_completed")
            if coins_earned:
                body, sep, tail = message.rpartition("Press Enter to continue.")
                coins_line = f"You earned {coins_earned} coins.\n\n"
                message = f"{body}{coins_line}{sep}{tail}" if sep else f"{message}\n\n{coins_line}"

        app.show_info_dialog("Quest Complete!", message)
        app.save_progress()
