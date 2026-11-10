"""Daily challenge definitions and progress checks."""

from datetime import date, datetime

# =========== Daily Challenge Configuration ===========

# Challenge definitions by day of week
DAILY_CHALLENGES = {
    0: {  # Monday
        "id": "speed_monday",
        "name": "Speed Monday",
        "description": "Type 50 words at 40+ WPM",
        "type": "speed_test",
        "target": {"words": 50, "min_wpm": 40},
        "xp_reward": 100,
        "emoji": "🚀"
    },
    1: {  # Tuesday
        "id": "accuracy_tuesday",
        "name": "Accuracy Tuesday",
        "description": "Complete any lesson with 98%+ accuracy",
        "type": "lesson_accuracy",
        "target": {"min_accuracy": 98.0},
        "xp_reward": 100,
        "emoji": "🎯"
    },
    2: {  # Wednesday
        "id": "sentence_wednesday",
        "name": "Sentence Wednesday",
        "description": "Type 20 practice sentences",
        "type": "sentence_practice",
        "target": {"count": 20},
        "xp_reward": 100,
        "emoji": "📝"
    },
    3: {  # Thursday
        "id": "game_thursday",
        "name": "Game Thursday",
        "description": "Score 500+ in Letter Fall",
        "type": "game_score",
        "target": {"game": "letter_fall", "score": 500},
        "xp_reward": 100,
        "emoji": "🎮"
    },
    4: {  # Friday
        "id": "focus_friday",
        "name": "Focus Friday",
        "description": "Complete 3 lessons in one session",
        "type": "lesson_count",
        "target": {"count": 3},
        "xp_reward": 100,
        "emoji": "🔥"
    },
    5: {  # Saturday
        "id": "weekend_marathon",
        "name": "Marathon Weekend",
        "description": "Complete a 5-minute speed test",
        "type": "speed_test_duration",
        "target": {"duration": 300},  # 5 minutes in seconds
        "xp_reward": 150,
        "emoji": "⏱️"
    },
    6: {  # Sunday
        "id": "weekend_marathon",
        "name": "Marathon Weekend",
        "description": "Complete a 5-minute speed test",
        "type": "speed_test_duration",
        "target": {"duration": 300},
        "xp_reward": 150,
        "emoji": "⏱️"
    }
}


def get_today_challenge() -> dict:
    """Get today's daily challenge.

    Returns:
        Dict with challenge info for today
    """
    today = datetime.now().weekday()  # 0 = Monday, 6 = Sunday
    return DAILY_CHALLENGES[today]


def get_today_date_string() -> str:
    """Get today's date in YYYY-MM-DD format.

    Returns:
        Date string
    """
    return date.today().isoformat()


def check_if_new_day(settings) -> bool:
    """Check if it's a new day (reset challenge).

    Args:
        settings: Settings object

    Returns:
        True if new day, False if same day
    """
    today = get_today_date_string()
    return settings.daily_challenge_date != today


def reset_daily_challenge(settings):
    """Reset daily challenge for new day.

    Args:
        settings: Settings object to update
    """
    today = get_today_date_string()

    # Check if streak should continue
    if settings.daily_challenge_date:
        try:
            last_date = date.fromisoformat(settings.daily_challenge_date)
            days_diff = (date.today() - last_date).days
            # The date is refreshed whenever the app opens on a new day, so a
            # day that was opened but not completed must break the streak too.
            if days_diff > 1 or (days_diff == 1 and not settings.daily_challenge_completed):
                # Missed a day, reset streak
                settings.daily_challenge_streak = 0
        except ValueError:
            settings.daily_challenge_streak = 0

    settings.daily_challenge_date = today
    settings.daily_challenge_completed = False


def check_challenge_progress(challenge_type: str, target: dict, current_data: dict) -> dict:
    """Check progress toward daily challenge.

    Args:
        challenge_type: Type of challenge
        target: Target requirements
        current_data: Current session/activity data

    Returns:
        Dict with completed (bool), progress, target
    """
    if challenge_type == "speed_test":
        # Check if typed enough words at target WPM
        words_typed = current_data.get("words_typed", 0)
        wpm = current_data.get("wpm", 0)
        completed = words_typed >= target["words"] and wpm >= target["min_wpm"]
        return {
            "completed": completed,
            "progress": words_typed,
            "target": target["words"],
            "extra": f"WPM: {wpm:.1f} (need {target['min_wpm']}+)"
        }

    elif challenge_type == "lesson_accuracy":
        accuracy = current_data.get("accuracy", 0)
        completed = accuracy >= target["min_accuracy"]
        return {
            "completed": completed,
            "progress": accuracy,
            "target": target["min_accuracy"],
            "extra": ""
        }

    elif challenge_type == "sentence_practice":
        count = current_data.get("sentences_completed", 0)
        completed = count >= target["count"]
        return {
            "completed": completed,
            "progress": count,
            "target": target["count"],
            "extra": ""
        }

    elif challenge_type == "game_score":
        game = current_data.get("game", "")
        score = current_data.get("score", 0)
        completed = game == target["game"] and score >= target["score"]
        return {
            "completed": completed,
            "progress": score,
            "target": target["score"],
            "extra": f"Game: {game}"
        }

    elif challenge_type == "lesson_count":
        count = current_data.get("lessons_completed", 0)
        completed = count >= target["count"]
        return {
            "completed": completed,
            "progress": count,
            "target": target["count"],
            "extra": ""
        }

    elif challenge_type == "speed_test_duration":
        duration = current_data.get("duration", 0)
        completed = duration >= target["duration"]
        return {
            "completed": completed,
            "progress": duration,
            "target": target["duration"],
            "extra": f"{duration}s / {target['duration']}s"
        }

    return {"completed": False, "progress": 0, "target": 0, "extra": ""}


def complete_daily_challenge(settings) -> dict:
    """Mark daily challenge as complete and award rewards.

    Args:
        settings: Settings object

    Returns:
        Dict with xp_earned, streak, milestone_reached
    """
    if settings.daily_challenge_completed:
        return {"xp_earned": 0, "streak": settings.daily_challenge_streak, "milestone_reached": False}

    settings.daily_challenge_completed = True
    settings.daily_challenge_streak += 1

    challenge = get_today_challenge()
    xp_earned = challenge["xp_reward"]

    # Bonus XP for streak milestones
    milestone_reached = False
    if settings.daily_challenge_streak in [3, 7, 14, 30]:
        xp_earned += 50
        milestone_reached = True

    return {
        "xp_earned": xp_earned,
        "streak": settings.daily_challenge_streak,
        "milestone_reached": milestone_reached
    }


def format_challenge_announcement(settings) -> str:
    """Format today's challenge for announcement.

    Args:
        settings: Settings object

    Returns:
        Formatted challenge string
    """
    # Check if new day
    if check_if_new_day(settings):
        reset_daily_challenge(settings)

    challenge = get_today_challenge()

    if settings.daily_challenge_completed:
        return f"{challenge['emoji']} Daily Challenge Complete!\n" \
               f"{challenge['name']}: {challenge['description']}\n" \
               f"Streak: {settings.daily_challenge_streak} days\n" \
               f"Come back tomorrow for a new challenge!"

    return f"{challenge['emoji']} Today's Challenge: {challenge['name']}\n" \
           f"{challenge['description']}\n" \
           f"Reward: {challenge['xp_reward']} XP\n" \
           f"Current Streak: {settings.daily_challenge_streak} days"
