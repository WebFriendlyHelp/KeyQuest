"""Progress dashboard and practice-log formatting for KeyQuest."""

from datetime import datetime, timedelta
from collections import OrderedDict
from typing import Optional


def record_session(settings, session_data: dict):
    """Record a session in history."""
    if len(settings.session_history) >= 100:
        settings.session_history = settings.session_history[-99:]

    now = datetime.now()
    session_data.setdefault("date", now.strftime("%Y-%m-%d"))
    session_data.setdefault("time", now.strftime("%I:%M %p").lstrip("0"))
    session_data.setdefault("timestamp", now.isoformat(timespec="seconds"))
    settings.session_history.append(session_data)


def get_recent_sessions(settings, days: int = 7) -> list:
    """Get sessions from the last N days."""
    if not settings.session_history:
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    return [session for session in settings.session_history if session.get("date", "") >= cutoff_str]


def calculate_average_wpm(sessions: list) -> float:
    """Calculate average WPM from sessions."""
    if not sessions:
        return 0.0

    wpm_values = [session.get("wpm", 0) for session in sessions if session.get("wpm", 0) > 0]
    return sum(wpm_values) / len(wpm_values) if wpm_values else 0.0


def calculate_average_accuracy(sessions: list) -> float:
    """Calculate average accuracy from sessions."""
    if not sessions:
        return 0.0

    accuracy_values = [
        session.get("accuracy", 0) for session in sessions if session.get("accuracy", 0) > 0
    ]
    return sum(accuracy_values) / len(accuracy_values) if accuracy_values else 0.0


def _append_section(lines: list[str], title: str) -> None:
    if lines:
        lines.append("")
    lines.append(title)
    lines.append("-" * 20)


def format_dashboard(settings) -> str:
    """Generate a readable progress dashboard."""
    lines = ["Progress Dashboard"]

    _append_section(lines, "OVERVIEW")
    hours = int(settings.total_practice_time // 3600)
    minutes = int((settings.total_practice_time % 3600) // 60)
    lines.append(f"Total Practice Time: {hours}h {minutes}m")
    lines.append(f"Lessons Completed: {settings.total_lessons_completed}")
    lines.append(f"Current Level: {settings.level}")
    lines.append(f"Current Streak: {settings.current_streak} days")
    if settings.longest_streak > 0:
        lines.append(f"Longest Streak: {settings.longest_streak} days")
    challenge_status = "Complete" if settings.daily_challenge_completed else "Not complete yet"
    lines.append(f"Today's Daily Challenge: {challenge_status}")
    lines.append(f"Daily Challenge Streak: {settings.daily_challenge_streak} days")

    _append_section(lines, "SPEED PROGRESS")
    if settings.highest_wpm > 0:
        lines.append(f"Best WPM Ever: {settings.highest_wpm:.1f}")

    this_week = get_recent_sessions(settings, 7)
    last_week = [session for session in get_recent_sessions(settings, 14) if session not in this_week]
    if this_week:
        this_week_wpm = calculate_average_wpm(this_week)
        lines.append(f"This Week Average: {this_week_wpm:.1f} WPM")
        if last_week:
            last_week_wpm = calculate_average_wpm(last_week)
            lines.append(f"Last Week Average: {last_week_wpm:.1f} WPM")
            improvement = this_week_wpm - last_week_wpm
            if improvement > 0:
                percentage = (improvement / last_week_wpm * 100.0) if last_week_wpm > 0 else 0.0
                lines.append(f"Improvement: +{improvement:.1f} WPM ({percentage:.1f}% increase)")
            elif improvement < 0:
                percentage = (abs(improvement) / last_week_wpm * 100.0) if last_week_wpm > 0 else 0.0
                lines.append(f"Change: {improvement:.1f} WPM ({percentage:.1f}% decrease)")
            else:
                lines.append("Consistent performance")

    _append_section(lines, "ACCURACY TRENDS")
    if this_week:
        this_week_acc = calculate_average_accuracy(this_week)
        lines.append(f"This Week Average: {this_week_acc:.1f}%")
        if last_week:
            last_week_acc = calculate_average_accuracy(last_week)
            lines.append(f"Last Week Average: {last_week_acc:.1f}%")
            improvement = this_week_acc - last_week_acc
            if improvement > 0:
                lines.append(f"Improvement: +{improvement:.1f}%")
            elif improvement < 0:
                lines.append(f"Change: {improvement:.1f}%")
            else:
                lines.append("Consistent accuracy")

    perfect_count = sum(1 for session in settings.session_history if session.get("accuracy", 0) >= 100)
    if perfect_count > 0:
        lines.append(f"Perfect Accuracy Sessions: {perfect_count}")

    _append_section(lines, "ACHIEVEMENTS")
    lines.append(f"Badges Earned: {len(settings.earned_badges)} of 10")
    lines.append(f"Quests Completed: {len(settings.completed_quests)} of 10")
    total_stars = sum(settings.lesson_stars.values())
    max_stars = len(settings.lesson_stars) * 3
    if max_stars > 0:
        lines.append(f"Stars Collected: {total_stars} of {max_stars} possible")

    _append_section(lines, "MILESTONES")
    milestones = []
    if settings.total_lessons_completed >= 1:
        milestones.append("First lesson completed")
    if settings.total_lessons_completed >= 10:
        milestones.append("10 lessons completed")
    if settings.total_lessons_completed >= 20:
        milestones.append("20 lessons completed")
    if settings.total_lessons_completed >= 33:
        milestones.append("All lessons completed")
    if settings.highest_wpm >= 20:
        milestones.append("Reached 20 WPM")
    if settings.highest_wpm >= 40:
        milestones.append("Reached 40 WPM")
    if settings.highest_wpm >= 60:
        milestones.append("Reached 60 WPM")
    if settings.current_streak >= 3:
        milestones.append("3-day streak")
    if settings.current_streak >= 7:
        milestones.append("7-day streak")
    if settings.current_streak >= 30:
        milestones.append("30-day streak")
    if milestones:
        lines.extend(f"* {milestone}" for milestone in milestones)
    else:
        lines.append("Keep practicing to reach milestones.")

    _append_section(lines, "NEXT GOALS")
    next_goals = []
    if settings.total_lessons_completed < 10:
        next_goals.append(f"Complete {10 - settings.total_lessons_completed} more lessons to reach 10 total")
    elif settings.total_lessons_completed < 20:
        next_goals.append(f"Complete {20 - settings.total_lessons_completed} more lessons to reach 20 total")
    elif settings.total_lessons_completed < 33:
        next_goals.append(f"Complete {33 - settings.total_lessons_completed} more lessons to finish all lessons")

    if settings.highest_wpm < 20:
        next_goals.append(f"Reach 20 WPM (currently {settings.highest_wpm:.1f})")
    elif settings.highest_wpm < 40:
        next_goals.append(f"Reach 40 WPM (currently {settings.highest_wpm:.1f})")
    elif settings.highest_wpm < 60:
        next_goals.append(f"Reach 60 WPM (currently {settings.highest_wpm:.1f})")

    if settings.current_streak < 3:
        next_goals.append("Practice 3 days in a row")
    elif settings.current_streak < 7:
        next_goals.append(f"Reach a 7-day streak (currently {settings.current_streak})")
    elif settings.current_streak < 30:
        next_goals.append(f"Reach a 30-day streak (currently {settings.current_streak})")

    if next_goals:
        lines.extend(f"* {goal}" for goal in next_goals[:3])
    else:
        lines.append("You've achieved all major milestones. Keep practicing.")

    lines.append("")
    lines.append("Keep up the great work!")
    return "\n".join(lines)


def format_practice_log(settings, limit: int = 30) -> str:
    """Format recent practice history as a readable log."""
    if not settings.session_history:
        return "Practice Log\n\nNo practice has been recorded yet."

    lines = ["Practice Log", ""]
    recent_sessions = list(settings.session_history)[-max(1, limit):]
    recent_sessions.sort(key=lambda session: _session_datetime(session) or datetime.min, reverse=True)
    previous_same_type_map = _build_previous_same_type_map(recent_sessions)
    grouped_sessions = _group_sessions_by_day(recent_sessions)
    ordered_days = list(grouped_sessions.keys())

    for day_index, day_key in enumerate(ordered_days):
        sessions = grouped_sessions[day_key]
        day_dt = _session_datetime(sessions[0])
        lines.append(_format_day_heading(day_dt, day_key))

        day_summary = _build_day_summary(sessions)
        previous_summary = _build_day_summary(grouped_sessions[ordered_days[day_index + 1]]) if day_index + 1 < len(ordered_days) else None
        comparison_text = _format_day_comparison(day_summary, previous_summary)
        if comparison_text:
            lines.append(comparison_text)

        for session in sessions:
            lines.extend(_format_session_block(session, previous_same_type_map.get(id(session))))
            lines.append("")

    return "\n".join(lines).rstrip()


def _session_datetime(session: dict) -> Optional[datetime]:
    timestamp = session.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        try:
            return datetime.fromisoformat(timestamp)
        except ValueError:
            pass

    date_text = session.get("date", "")
    time_text = session.get("time", "")
    if date_text:
        for candidate in (
            f"{date_text} {time_text}".strip(),
            date_text,
        ):
            try:
                if time_text:
                    return datetime.strptime(candidate, "%Y-%m-%d %I:%M %p")
                return datetime.strptime(candidate, "%Y-%m-%d")
            except ValueError:
                continue
    return None


def _group_sessions_by_day(sessions: list[dict]) -> OrderedDict[str, list[dict]]:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for session in sessions:
        dt = _session_datetime(session)
        key = dt.strftime("%Y-%m-%d") if dt else session.get("date", "Unknown date")
        grouped.setdefault(key, []).append(session)
    return grouped


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format_day_heading(dt: Optional[datetime], fallback: str) -> str:
    if not dt:
        return fallback
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {_ordinal(dt.day)}"


def _format_friendly_datetime(dt: Optional[datetime], fallback: str = "Unknown time") -> str:
    if not dt:
        return fallback
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {_ordinal(dt.day)}, {dt.strftime('%I:%M %p').lstrip('0')}"


def _format_duration(seconds) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""

    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours and minutes == 30 and secs == 0:
        return f"{hours} and a half hours" if hours > 1 else "1 and a half hours"
    if hours:
        if minutes:
            hour_label = "hour" if hours == 1 else "hours"
            minute_label = "minute" if minutes == 1 else "minutes"
            return f"{hours} {hour_label} {minutes} {minute_label}"
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    if minutes:
        if secs:
            minute_label = "minute" if minutes == 1 else "minutes"
            second_label = "second" if secs == 1 else "seconds"
            return f"{minutes} {minute_label} {secs} {second_label}"
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{secs} second" if secs == 1 else f"{secs} seconds"


def _build_day_summary(sessions: list[dict]) -> dict:
    total_duration = sum(
        session.get("duration", 0) for session in sessions if isinstance(session.get("duration"), (int, float))
    )
    wpm_values = [
        session.get("wpm", 0)
        for session in sessions
        if isinstance(session.get("wpm"), (int, float)) and session.get("wpm", 0) > 0
    ]
    accuracy_values = [
        session.get("accuracy", 0)
        for session in sessions
        if isinstance(session.get("accuracy"), (int, float)) and session.get("accuracy", 0) > 0
    ]
    return {
        "count": len(sessions),
        "duration": total_duration,
        "avg_wpm": (sum(wpm_values) / len(wpm_values)) if wpm_values else 0.0,
        "avg_accuracy": (sum(accuracy_values) / len(accuracy_values)) if accuracy_values else 0.0,
        "activities": _summarize_day_activities(sessions),
    }


def _format_delta(current: float, previous: float, better_word: str, worse_word: str, unit: str) -> str:
    if previous <= 0:
        return ""
    delta = current - previous
    if abs(delta) < 0.05:
        return f"about the same {unit}"
    direction = better_word if delta > 0 else worse_word
    return f"{abs(delta):.1f} {unit} {direction}"


def _format_day_comparison(current: dict, previous: Optional[dict]) -> str:
    duration_text = _format_duration(current.get("duration", 0))
    count = current.get("count", 0)
    activity_text = _format_activity_list(current.get("activities", []))
    count_text = f"{count} activity" if count == 1 else f"{count} activities"
    parts = [f"{count_text}: {activity_text}" if activity_text else count_text]
    if duration_text:
        parts.append(f"{duration_text} total")
    if current.get("avg_wpm", 0) > 0:
        parts.append(f"average {current['avg_wpm']:.1f} WPM")
    if current.get("avg_accuracy", 0) > 0:
        parts.append(f"average {current['avg_accuracy']:.1f}% accuracy")

    if previous:
        comparisons = []
        wpm_delta = _format_delta(
            current.get("avg_wpm", 0),
            previous.get("avg_wpm", 0),
            "faster",
            "slower",
            "WPM",
        )
        if wpm_delta:
            comparisons.append(f"today was {wpm_delta} on average")
        acc_delta = _format_delta(
            current.get("avg_accuracy", 0),
            previous.get("avg_accuracy", 0),
            "higher",
            "lower",
            "accuracy points",
        )
        if acc_delta:
            comparisons.append(f"today was {acc_delta} in accuracy")
        if comparisons:
            parts.append("Compared with your previous recorded practice day, " + " and ".join(comparisons))

    return ". ".join(parts) + "."


def _format_session_block(session: dict, previous_similar: Optional[dict] = None) -> list[str]:
    dt = _session_datetime(session)
    lines = [f"- {_format_friendly_datetime(dt, session.get('date', 'Unknown date'))}"]

    summary = _session_summary_text(session)
    lines.append(f"  Did: {summary}")

    duration_text = _format_duration(session.get("duration"))
    if duration_text:
        lines.append(f"  Duration: {duration_text}")

    if session.get("ended_early"):
        exit_reason = str(session.get("exit_reason", "")).strip().lower()
        if exit_reason == "escape":
            lines.append("  Status: Ended early with Escape.")
        else:
            lines.append("  Status: Ended early.")

    performance_bits = []
    wpm = session.get("wpm")
    if isinstance(wpm, (int, float)) and wpm > 0:
        performance_bits.append(f"{wpm:.1f} WPM")
    accuracy = session.get("accuracy")
    if isinstance(accuracy, (int, float)) and accuracy > 0:
        performance_bits.append(f"{accuracy:.1f}% accuracy")
    stars = session.get("stars")
    if isinstance(stars, int) and stars > 0:
        performance_bits.append(f"{stars} stars")
    if performance_bits:
        lines.append(f"  Result: {', '.join(performance_bits)}")

    earned = session.get("earned")
    if earned:
        lines.append(f"  Earned: {earned}")

    comparison_text = _format_session_comparison(session, previous_similar)
    if comparison_text:
        lines.append(f"  Change: {comparison_text}")

    return lines


def _session_summary_text(session: dict) -> str:
    return session.get("summary") or str(session.get("type", "practice")).replace("_", " ").title()


def _build_previous_same_type_map(sessions: list[dict]) -> dict:
    previous_map = {}
    last_by_key = {}
    for session in reversed(sessions):
        compare_key = _session_compare_key(session)
        previous_map[id(session)] = last_by_key.get(compare_key)
        last_by_key[compare_key] = session
    return previous_map


def _session_compare_key(session: dict) -> str:
    summary = session.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    type_name = session.get("type")
    if isinstance(type_name, str) and type_name.strip():
        return type_name.strip()
    return "practice"


def _summarize_day_activities(sessions: list[dict]) -> list[str]:
    activities = []
    seen = set()
    for session in sessions:
        summary = _session_summary_text(session).strip()
        if summary and summary not in seen:
            activities.append(summary)
            seen.add(summary)
    return activities


def _format_activity_list(activities: list[str]) -> str:
    if not activities:
        return ""
    if len(activities) <= 3:
        return ", ".join(activities)
    shown = ", ".join(activities[:3])
    remaining = len(activities) - 3
    return f"{shown}, and {remaining} more"


def _format_session_comparison(session: dict, previous_similar: Optional[dict]) -> str:
    if not previous_similar:
        return ""

    summary = _session_summary_text(session)
    comparisons = []
    wpm_delta = _format_delta(
        session.get("wpm", 0),
        previous_similar.get("wpm", 0),
        "faster",
        "slower",
        "WPM",
    )
    if wpm_delta:
        comparisons.append(f"this was {wpm_delta} than your last {summary}")

    acc_delta = _format_delta(
        session.get("accuracy", 0),
        previous_similar.get("accuracy", 0),
        "higher",
        "lower",
        "accuracy points",
    )
    if acc_delta:
        comparisons.append(f"accuracy was {acc_delta} than your last {summary}")

    return ". ".join(comparisons) + ("." if comparisons else "")


def format_weekly_summary(settings) -> str:
    """Generate weekly summary report."""
    this_week = get_recent_sessions(settings, 7)
    if not this_week:
        return "No practice sessions this week. Start practicing to see your weekly summary!"

    lines = ["This Week's Summary", ""]
    lines.append(f"Practice Sessions: {len(this_week)}")
    total_time = sum(session.get("duration", 0) for session in this_week)
    lines.append(f"Total Practice Time: {int(total_time // 60)} minutes")
    lines.append(f"Average WPM: {calculate_average_wpm(this_week):.1f}")
    lines.append(f"Average Accuracy: {calculate_average_accuracy(this_week):.1f}%")

    best_wpm_session = max(this_week, key=lambda session: session.get("wpm", 0), default=None)
    if best_wpm_session and best_wpm_session.get("wpm", 0) > 0:
        lines.append(f"Best WPM: {best_wpm_session['wpm']:.1f}")

    best_acc_session = max(this_week, key=lambda session: session.get("accuracy", 0), default=None)
    if best_acc_session and best_acc_session.get("accuracy", 0) > 0:
        lines.append(f"Best Accuracy: {best_acc_session['accuracy']:.1f}%")

    return "\n".join(lines)
