from __future__ import annotations

from datetime import date, datetime


MILESTONES = (3, 7, 14, 30, 60, 100)


def award_streak_milestone(settings, milestone: int | None) -> str:
    """Pay any coins for a streak milestone and return the line that says so.

    Returns "" when there is no milestone. The coin rewards exist only for
    days 7, 30 and 100 (currency_manager.COIN_REWARDS).
    """
    if milestone is None:
        return ""
    from modules import currency_manager

    text = f"Streak milestone! Day {milestone} of your typing streak! Keep it up!"
    coins = currency_manager.award_coins(settings, f"streak_milestone_{milestone}")
    if coins:
        text += f" You earned {coins} coins."
    return text


def get_streak_announcement(settings) -> str:
    """Return the current streak announcement for the menu."""
    streak = int(getattr(settings, "current_streak", 0) or 0)
    if streak <= 0:
        return ""
    if streak == 1:
        return "Day 1 of your streak!"
    return f"Day {streak} streak! Keep going!"


def check_and_update_streak(settings, today: date | None = None) -> int | None:
    """Update daily streak counters in-place.

    Returns:
        milestone day number if a milestone was reached, else None.
    """
    if today is None:
        today = datetime.now().date()

    today_str = today.strftime("%Y-%m-%d")
    last_practice_date = getattr(settings, "last_practice_date", "") or ""

    # First time: initialize streak.
    if not last_practice_date:
        settings.current_streak = 1
        settings.last_practice_date = today_str
        settings.longest_streak = 1
        return None

    # Parse last practice date.
    try:
        last_date = datetime.strptime(last_practice_date, "%Y-%m-%d").date()
    except ValueError:
        settings.current_streak = 1
        settings.last_practice_date = today_str
        settings.longest_streak = max(int(getattr(settings, "longest_streak", 0) or 0), 1)
        return None

    days_since = (today - last_date).days
    if days_since == 0:
        return None

    if days_since == 1:
        settings.current_streak = int(getattr(settings, "current_streak", 0) or 0) + 1
        settings.last_practice_date = today_str
        if settings.current_streak > int(getattr(settings, "longest_streak", 0) or 0):
            settings.longest_streak = settings.current_streak

        return settings.current_streak if settings.current_streak in MILESTONES else None

    settings.current_streak = 1
    settings.last_practice_date = today_str
    return None

