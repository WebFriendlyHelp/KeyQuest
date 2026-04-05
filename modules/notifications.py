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

        announcement = badge_manager.format_badge_announcement(badge_id)
        coins_earned = currency_manager.award_coins(app.state.settings, "badge_earned")
        app.speech.say(announcement, priority=True, protect_seconds=2.0)
        if coins_earned:
            app.speech.say(currency_manager.get_coin_announcement("badge_earned", coins_earned), priority=True)

        app.show_info_dialog("Badge Unlocked", message)
        app.save_progress()


def show_level_up_notification(app, xp_result: dict) -> None:
    """Show level-up notification."""
    if not xp_result.get("leveled_up", False):
        return

    message = (
        f"Use Up and Down arrows to read this.\n"
        f"Press Enter to continue.\n\n"
        f"LEVEL UP!\n\n"
        f"Level {xp_result['new_level']}: {xp_result['level_name']}\n\n"
        f"Total XP: {xp_result['total_xp']:,}\n\n"
        f"Keep practicing to reach the next level!\n\n"
        f"Press Enter to continue."
    )

    app.audio.play_levelup()

    coins_earned = currency_manager.award_coins(app.state.settings, "level_up")
    announcement = f"Level up! You reached Level {xp_result['new_level']}: {xp_result['level_name']}!"
    app.speech.say(announcement, priority=True, protect_seconds=2.0)
    if coins_earned:
        app.speech.say(currency_manager.get_coin_announcement("level_up", coins_earned), priority=True)

    app.show_info_dialog("Level Up!", message)
    app.save_progress()


def show_quest_notifications(app) -> None:
    """Show any pending quest completion notifications."""
    while app.state.settings.quest_notifications:
        quest_id = app.state.settings.quest_notifications.pop(0)

        message = quest_manager.format_quest_completion(quest_id)

        app.audio.play_quest()

        quest = quest_manager.get_quest_info(quest_id)
        if quest:
            coins_earned = currency_manager.award_coins(app.state.settings, "quest_completed")
            announcement = (
                f"Quest complete! {quest['name']}. "
                f"You earned {quest['xp_reward']} experience points!"
            )
            if coins_earned:
                announcement += f" {currency_manager.get_coin_announcement('quest_completed', coins_earned)}"
            app.speech.say(announcement, priority=True, protect_seconds=2.0)

        app.show_info_dialog("Quest Complete!", message)
        app.save_progress()
