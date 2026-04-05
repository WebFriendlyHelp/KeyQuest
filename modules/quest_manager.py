"""Quest definitions and quest-progress helpers."""

# =========== Quest Definitions ===========

QUESTS = {
    "home_row_master": {
        "id": "home_row_master",
        "name": "Master the Home Row",
        "description": "Complete lessons 1-8 (home row keys)",
        "type": "lessons_range",
        "target": {"start": 1, "end": 8, "count": 8},
        "xp_reward": 200,
        "emoji": "🏠"
    },
    "speed_demon": {
        "id": "speed_demon",
        "name": "Speed Demon Training",
        "description": "Reach 40 WPM in any lesson",
        "type": "wpm_milestone",
        "target": {"wpm": 40},
        "xp_reward": 200,
        "emoji": "⚡"
    },
    "accuracy_expert": {
        "id": "accuracy_expert",
        "name": "Accuracy Expert",
        "description": "Achieve 95%+ accuracy in 3 different lessons",
        "type": "accuracy_count",
        "target": {"accuracy": 95.0, "count": 3},
        "xp_reward": 200,
        "emoji": "🎯"
    },
    "marathon_runner": {
        "id": "marathon_runner",
        "name": "Marathon Runner",
        "description": "Complete a 10-minute speed test",
        "type": "speed_test_duration",
        "target": {"duration": 600},  # 10 minutes in seconds
        "xp_reward": 200,
        "emoji": "🏃"
    },
    "game_champion": {
        "id": "game_champion",
        "name": "Game Champion",
        "description": "Score 500+ in Letter Fall",
        "type": "game_score",
        "target": {"game": "letter_fall", "score": 500},
        "xp_reward": 200,
        "emoji": "🏆"
    },
    "language_explorer": {
        "id": "language_explorer",
        "name": "Language Explorer",
        "description": "Try sentence practice in both languages",
        "type": "languages_tried",
        "target": {"languages": ["English", "Spanish"], "count": 2},
        "xp_reward": 200,
        "emoji": "🌍"
    },
    "special_keys_expert": {
        "id": "special_keys_expert",
        "name": "Special Keys Expert",
        "description": "Complete all function key lessons (25-32)",
        "type": "lessons_range",
        "target": {"start": 25, "end": 32, "count": 8},
        "xp_reward": 200,
        "emoji": "🔧"
    },
    "consistent_practitioner": {
        "id": "consistent_practitioner",
        "name": "Consistent Practitioner",
        "description": "Practice 5 days in one week",
        "type": "practice_days",
        "target": {"days": 5},
        "xp_reward": 200,
        "emoji": "📅"
    },
    "lesson_completionist": {
        "id": "lesson_completionist",
        "name": "Lesson Completionist",
        "description": "Complete 15 different lessons",
        "type": "lessons_completed",
        "target": {"count": 15},
        "xp_reward": 300,
        "emoji": "✅"
    },
    "star_collector": {
        "id": "star_collector",
        "name": "Star Collector",
        "description": "Earn 3 stars on 5 different lessons",
        "type": "three_star_count",
        "target": {"stars": 3, "count": 5},
        "xp_reward": 300,
        "emoji": "⭐"
    }
}


def initialize_quests(settings):
    """Initialize active quests if not already set.

    Args:
        settings: Settings object
    """
    if not settings.active_quests:
        # Start with first 3 quests active
        starter_quests = ["home_row_master", "speed_demon", "accuracy_expert"]
        for quest_id in starter_quests:
            if quest_id not in settings.completed_quests:
                settings.active_quests[quest_id] = {
                    "progress": 0,
                    "started_date": ""
                }


def get_quest_info(quest_id: str) -> dict:
    """Get quest information.

    Args:
        quest_id: Quest identifier

    Returns:
        Quest info dict or None if not found
    """
    return QUESTS.get(quest_id)


def check_quest_progress(quest_id: str, current_progress: int, target: int) -> dict:
    """Check if quest is complete.

    Args:
        quest_id: Quest identifier
        current_progress: Current progress value
        target: Target value

    Returns:
        Dict with completed (bool), progress, target, percentage
    """
    percentage = min(100.0, (current_progress / target * 100.0)) if target > 0 else 0.0
    return {
        "completed": current_progress >= target,
        "progress": current_progress,
        "target": target,
        "percentage": percentage
    }


def update_quest_progress(settings, quest_id: str, progress_data: dict) -> dict:
    """Update quest progress based on activity.

    Args:
        settings: Settings object
        quest_id: Quest to update
        progress_data: Dict with relevant progress data

    Returns:
        Dict with updated (bool), completed (bool), progress
    """
    if quest_id not in settings.active_quests:
        return {"updated": False, "completed": False, "progress": 0}

    if quest_id in settings.completed_quests:
        return {"updated": False, "completed": True, "progress": 0}

    quest = get_quest_info(quest_id)
    if not quest:
        return {"updated": False, "completed": False, "progress": 0}

    quest_type = quest["type"]
    target = quest["target"]
    current_progress = settings.active_quests[quest_id].get("progress", 0)

    # Update progress based on quest type
    if quest_type == "lessons_range":
        # Check if completed lesson is in range
        lesson_num = progress_data.get("lesson_num", -1)
        if target["start"] <= lesson_num <= target["end"]:
            # Check if already counted
            completed_lessons = settings.active_quests[quest_id].get("completed_lessons", set())
            if isinstance(completed_lessons, list):
                completed_lessons = set(completed_lessons)
            if lesson_num not in completed_lessons:
                completed_lessons.add(lesson_num)
                settings.active_quests[quest_id]["completed_lessons"] = list(completed_lessons)
                current_progress = len(completed_lessons)
                settings.active_quests[quest_id]["progress"] = current_progress

    elif quest_type == "wpm_milestone":
        wpm = progress_data.get("wpm", 0)
        if wpm >= target["wpm"]:
            current_progress = 1
            settings.active_quests[quest_id]["progress"] = 1

    elif quest_type == "accuracy_count":
        accuracy = progress_data.get("accuracy", 0)
        lesson_num = progress_data.get("lesson_num", -1)
        if accuracy >= target["accuracy"]:
            # Track which lessons achieved this
            high_accuracy_lessons = settings.active_quests[quest_id].get("high_accuracy_lessons", set())
            if isinstance(high_accuracy_lessons, list):
                high_accuracy_lessons = set(high_accuracy_lessons)
            if lesson_num >= 0 and lesson_num not in high_accuracy_lessons:
                high_accuracy_lessons.add(lesson_num)
                settings.active_quests[quest_id]["high_accuracy_lessons"] = list(high_accuracy_lessons)
                current_progress = len(high_accuracy_lessons)
                settings.active_quests[quest_id]["progress"] = current_progress

    elif quest_type == "lessons_completed":
        # Count total unique lessons completed
        current_progress = settings.total_lessons_completed
        settings.active_quests[quest_id]["progress"] = current_progress

    elif quest_type == "three_star_count":
        # Count lessons with 3 stars
        three_star_count = sum(1 for stars in settings.lesson_stars.values() if stars == 3)
        current_progress = three_star_count
        settings.active_quests[quest_id]["progress"] = current_progress

    # Check if completed
    target_value = target.get("count", target.get("wpm", target.get("duration", 1)))
    completed = current_progress >= target_value

    if completed and quest_id not in settings.completed_quests:
        settings.completed_quests.add(quest_id)
        settings.quest_notifications.append(quest_id)
        return {"updated": True, "completed": True, "progress": current_progress}

    return {"updated": True, "completed": False, "progress": current_progress}


def check_all_active_quests(settings, progress_data: dict) -> list:
    """Check all active quests and update progress.

    Args:
        settings: Settings object
        progress_data: Dict with activity data

    Returns:
        List of newly completed quest IDs
    """
    newly_completed = []

    for quest_id in list(settings.active_quests.keys()):
        result = update_quest_progress(settings, quest_id, progress_data)
        if result["completed"] and quest_id not in newly_completed:
            newly_completed.append(quest_id)

    return newly_completed


def format_quest_list(settings, show_inactive: bool = False) -> str:
    """Format quest list for display.

    Args:
        settings: Settings object
        show_inactive: Whether to show completed quests

    Returns:
        Formatted quest list string
    """
    lines = ["📜 Your Quests:\n"]

    # Active quests
    if settings.active_quests:
        lines.append("Active Quests:")
        for quest_id in settings.active_quests:
            if quest_id in settings.completed_quests:
                continue

            quest = get_quest_info(quest_id)
            if quest:
                progress = settings.active_quests[quest_id].get("progress", 0)
                target = quest["target"].get("count", quest["target"].get("wpm", quest["target"].get("duration", 1)))
                percentage = min(100.0, (progress / target * 100.0)) if target > 0 else 0.0

                lines.append(f"\n{quest['emoji']} {quest['name']}")
                lines.append(f"  {quest['description']}")
                lines.append(f"  Progress: {progress}/{target} ({percentage:.0f}%)")
    else:
        lines.append("No active quests. Complete lessons to unlock quests!")

    # Completed quests
    if show_inactive and settings.completed_quests:
        lines.append("\n\nCompleted Quests:")
        for quest_id in settings.completed_quests:
            quest = get_quest_info(quest_id)
            if quest:
                lines.append(f"✅ {quest['emoji']} {quest['name']}")

    completed_count = len(settings.completed_quests)
    total_count = len(QUESTS)
    lines.append(f"\n\nTotal Completed: {completed_count}/{total_count} quests")

    return "\n".join(lines)


def format_quest_completion(quest_id: str) -> str:
    """Format quest completion announcement.

    Args:
        quest_id: Completed quest ID

    Returns:
        Formatted completion string
    """
    quest = get_quest_info(quest_id)
    if not quest:
        return "Quest completed!"

    return (
        f"🎉 Quest Complete! 🎉\n"
        f"Use Up and Down arrows to read.\n"
        f"Press Enter to continue.\n\n"
        f"{quest['emoji']} {quest['name']}\n\n"
        f"{quest['description']}\n\n"
        f"Reward: {quest['xp_reward']} XP\n\n"
        f"Press Enter to continue."
    )
