"""Per-key typing analytics and reporting helpers."""

# =========== Key Statistics Tracking ===========

def record_keystroke(settings, key: str, correct: bool):
    """Record a keystroke for analytics.

    Args:
        settings: Settings object
        key: Key that was pressed
        correct: Whether it was correct
    """
    if key not in settings.key_stats:
        settings.key_stats[key] = {
            "attempts": 0,
            "correct": 0,
            "errors": 0
        }

    settings.key_stats[key]["attempts"] += 1
    if correct:
        settings.key_stats[key]["correct"] += 1
    else:
        settings.key_stats[key]["errors"] += 1


def get_key_accuracy(settings, key: str) -> float:
    """Get accuracy percentage for a specific key.

    Args:
        settings: Settings object
        key: Key to check

    Returns:
        Accuracy percentage (0-100)
    """
    if key not in settings.key_stats or settings.key_stats[key]["attempts"] == 0:
        return 100.0

    stats = settings.key_stats[key]
    return (stats["correct"] / stats["attempts"]) * 100.0


def categorize_keys_by_performance(settings, min_attempts: int = 10) -> dict:
    """Categorize keys into performance tiers.

    Args:
        settings: Settings object
        min_attempts: Minimum attempts needed for categorization

    Returns:
        Dict with strong_keys, good_keys, problem_keys lists
    """
    strong_keys = []
    good_keys = []
    problem_keys = []

    for key, stats in settings.key_stats.items():
        if stats["attempts"] < min_attempts:
            continue  # Not enough data

        accuracy = get_key_accuracy(settings, key)

        if accuracy >= 95:
            strong_keys.append((key, accuracy, stats["errors"]))
        elif accuracy >= 85:
            good_keys.append((key, accuracy, stats["errors"]))
        else:
            problem_keys.append((key, accuracy, stats["errors"]))

    # Sort by accuracy (descending) then by errors (ascending)
    strong_keys.sort(key=lambda x: (-x[1], x[2]))
    good_keys.sort(key=lambda x: (-x[1], x[2]))
    problem_keys.sort(key=lambda x: (x[1], -x[2]))  # Worst first

    return {
        "strong_keys": strong_keys,
        "good_keys": good_keys,
        "problem_keys": problem_keys
    }


def get_problem_keys(settings, min_attempts: int = 10, max_accuracy: float = 85.0) -> list:
    """Get list of keys that need practice.

    Args:
        settings: Settings object
        min_attempts: Minimum attempts to consider
        max_accuracy: Maximum accuracy to be considered a problem

    Returns:
        List of (key, accuracy, errors) tuples
    """
    problem_keys = []

    for key, stats in settings.key_stats.items():
        if stats["attempts"] < min_attempts:
            continue

        accuracy = get_key_accuracy(settings, key)
        if accuracy < max_accuracy:
            problem_keys.append((key, accuracy, stats["errors"]))

    # Sort by accuracy (ascending), then errors (descending)
    problem_keys.sort(key=lambda x: (x[1], -x[2]))

    return problem_keys


def format_key_performance_report(settings, min_attempts: int = 10) -> str:
    """Generate audio-friendly performance report.

    Args:
        settings: Settings object
        min_attempts: Minimum attempts for inclusion

    Returns:
        Formatted report string
    """
    categories = categorize_keys_by_performance(settings, min_attempts)

    lines = ["Keyboard Performance Report\n"]

    # Check if we have enough data
    total_keys = len(settings.key_stats)
    analyzed_keys = len([k for k, s in settings.key_stats.items() if s["attempts"] >= min_attempts])

    if analyzed_keys == 0:
        return "Not enough data yet. Keep practicing to see your keyboard performance report!"

    lines.append(f"Analyzed {analyzed_keys} keys with {min_attempts}+ attempts.\n")

    # Strong keys
    if categories["strong_keys"]:
        lines.append(f"\nStrong Keys ({len(categories['strong_keys'])} keys, 95%+ accuracy):")
        key_names = [key for key, acc, err in categories["strong_keys"][:10]]  # Top 10
        lines.append(f"  {', '.join(key_names)}")

    # Good keys
    if categories["good_keys"]:
        lines.append(f"\nGood Keys ({len(categories['good_keys'])} keys, 85-95% accuracy):")
        key_names = [key for key, acc, err in categories["good_keys"][:10]]
        lines.append(f"  {', '.join(key_names)}")

    # Problem keys
    if categories["problem_keys"]:
        lines.append(f"\nKeys Needing Practice ({len(categories['problem_keys'])} keys, below 85%):")
        for key, accuracy, errors in categories["problem_keys"][:5]:  # Top 5 worst
            lines.append(f"  - {key.upper()}: {accuracy:.1f}% accuracy, {errors} errors")

        # Recommendations
        lines.append("\nRecommendation:")
        worst_keys = [key for key, _, _ in categories["problem_keys"][:3]]
        lines.append(f"  Focus on practicing these keys: {', '.join(worst_keys)}")
        lines.append("  Try Free Practice mode to improve without pressure.")

    # Overall stats
    if settings.key_stats:
        total_attempts = sum(s["attempts"] for s in settings.key_stats.values())
        total_correct = sum(s["correct"] for s in settings.key_stats.values())
        overall_accuracy = (total_correct / total_attempts * 100.0) if total_attempts > 0 else 0

        lines.append("\nOverall Statistics:")
        lines.append(f"  Total keystrokes: {total_attempts:,}")
        lines.append(f"  Overall accuracy: {overall_accuracy:.1f}%")
        lines.append(f"  Keys tracked: {total_keys}")

    return "\n".join(lines)


def get_weakest_finger(settings, min_attempts: int = 10) -> dict:
    """Identify which finger has the most problems.

    Args:
        settings: Settings object
        min_attempts: Minimum attempts to consider

    Returns:
        Dict with finger name and problem keys
    """
    # Map keys to fingers
    finger_map = {
        "left_pinky": ['q', 'a', 'z', '1', '`', 'tab', 'caps lock', 'shift'],
        "left_ring": ['w', 's', 'x', '2'],
        "left_middle": ['e', 'd', 'c', '3'],
        "left_index": ['r', 'f', 'v', 't', 'g', 'b', '4', '5'],
        "right_index": ['y', 'h', 'n', 'u', 'j', 'm', '6', '7'],
        "right_middle": ['i', 'k', ',', '8'],
        "right_ring": ['o', 'l', '.', '9'],
        "right_pinky": ['p', ';', '/', '[', ']', '\\', '-', '=', '0', 'enter', 'backspace']
    }

    finger_stats = {}

    for finger, keys in finger_map.items():
        total_attempts = 0
        total_correct = 0
        problem_keys = []

        for key in keys:
            key_lower = key.lower()
            if key_lower in settings.key_stats:
                stats = settings.key_stats[key_lower]
                if stats["attempts"] >= min_attempts:
                    total_attempts += stats["attempts"]
                    total_correct += stats["correct"]

                    accuracy = get_key_accuracy(settings, key_lower)
                    if accuracy < 85:
                        problem_keys.append((key_lower, accuracy))

        if total_attempts > 0:
            finger_accuracy = (total_correct / total_attempts * 100.0)
            finger_stats[finger] = {
                "accuracy": finger_accuracy,
                "attempts": total_attempts,
                "problem_keys": problem_keys
            }

    if not finger_stats:
        return {"finger": "Unknown", "accuracy": 100.0, "problem_keys": []}

    # Find weakest finger
    weakest = min(finger_stats.items(), key=lambda x: x[1]["accuracy"])

    return {
        "finger": weakest[0].replace("_", " ").title(),
        "accuracy": weakest[1]["accuracy"],
        "problem_keys": [k for k, a in weakest[1]["problem_keys"]],
        "attempts": weakest[1]["attempts"]
    }


def recommend_lessons_for_keys(settings, keys: list) -> list:
    """Recommend lessons that focus on specific keys.

    Args:
        settings: Settings object
        keys: List of keys to practice

    Returns:
        List of recommended lesson numbers
    """
    # This is a simplified mapping; it does not currently bind to
    # lesson_manager.STAGE_LETTERS and returns general recommendations.

    recommendations = []

    # Home row letters (lessons 0-8)
    home_row = ['a', 's', 'd', 'f', 'j', 'k', 'l', ';']
    if any(k in home_row for k in keys):
        recommendations.extend([0, 1, 2, 3, 4, 5, 6, 7, 8])

    # Top row letters (lessons 9-13)
    top_row = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p']
    if any(k in top_row for k in keys):
        recommendations.extend([9, 10, 11, 12, 13])

    # Bottom row letters (lessons 14-18)
    bottom_row = ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/']
    if any(k in bottom_row for k in keys):
        recommendations.extend([14, 15, 16, 17, 18])

    # Remove duplicates and sort
    recommendations = sorted(list(set(recommendations)))

    return recommendations[:5]  # Return top 5
