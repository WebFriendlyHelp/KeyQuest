"""State management and data classes for KeyQuest.

Centralizes all state/data structures and progress save/load functionality.
"""

import json
import pathlib
import traceback
from datetime import date
from dataclasses import dataclass, field
from collections import Counter, deque
from typing import Dict, List, Set
from modules import error_logging


# =========== Performance Tracking ===========

@dataclass
class KeyPerformance:
    """Track performance for individual keys."""
    key: str
    attempts: int = 0
    correct: int = 0
    recent_attempts: deque = field(default_factory=lambda: deque(maxlen=10))

    def accuracy(self) -> float:
        if self.attempts == 0:
            return 1.0
        return self.correct / self.attempts

    def recent_accuracy(self) -> float:
        if not self.recent_attempts:
            return 1.0
        return sum(self.recent_attempts) / len(self.recent_attempts)

    def record_attempt(self, success: bool):
        self.attempts += 1
        if success:
            self.correct += 1
        self.recent_attempts.append(1 if success else 0)


@dataclass
class AdaptiveTracker:
    """Track overall performance and adapt difficulty."""
    key_performance: Dict[str, KeyPerformance] = field(default_factory=dict)
    recent_keys: deque = field(default_factory=lambda: deque(maxlen=10))  # Track last 10 keys
    consecutive_correct: int = 0
    consecutive_wrong: int = 0
    total_correct: int = 0
    total_attempts: int = 0
    total_characters: int = 0  # Track total characters typed for WPM calculation

    def record_keystroke(self, key: str, correct: bool):
        """Record a keystroke and update adaptive metrics."""
        if key not in self.key_performance:
            self.key_performance[key] = KeyPerformance(key=key)

        self.key_performance[key].record_attempt(correct)
        self.recent_keys.append((key, correct))
        self.total_attempts += 1

        if correct:
            self.total_correct += 1
            self.total_characters += 1  # Count characters for WPM calculation
            self.consecutive_wrong = 0
            # Only count non-consecutive keys for streak
            if len(self.recent_keys) >= 2:
                if self.recent_keys[-1][0] != self.recent_keys[-2][0]:
                    self.consecutive_correct += 1
            else:
                self.consecutive_correct += 1
        else:
            self.consecutive_correct = 0
            # Only count non-consecutive keys for wrong streak
            if len(self.recent_keys) >= 2:
                if self.recent_keys[-1][0] != self.recent_keys[-2][0]:
                    self.consecutive_wrong += 1
            else:
                self.consecutive_wrong += 1

    def overall_accuracy(self) -> float:
        if self.total_attempts == 0:
            return 1.0
        return self.total_correct / self.total_attempts

    def calculate_wpm(self, duration_seconds: float) -> float:
        """Calculate words per minute (WPM). Standard word = 5 characters."""
        if duration_seconds <= 0:
            return 0.0
        minutes = duration_seconds / 60.0
        words = self.total_characters / 5.0  # Standard word is 5 characters
        return words / minutes if minutes > 0 else 0.0

    def should_advance(self, lesson_num: int = 0, duration_seconds: float = 0.0,
                      wpm_required_from_lesson: int = 6, min_wpm: float = 20.0) -> bool:
        """Determine if user should advance to next stage.

        Args:
            lesson_num: Current lesson number
            duration_seconds: Duration of lesson in seconds
            wpm_required_from_lesson: Lesson number where WPM requirement starts
            min_wpm: Minimum WPM required to advance
        """
        # Require at least three correct non-repeated keys in a row.
        if self.consecutive_correct >= 3:
            # Require at least 80% overall accuracy before advancing.
            if self.overall_accuracy() > 0.80:
                # Later lessons also require minimum typing speed.
                if lesson_num >= wpm_required_from_lesson and duration_seconds > 0:
                    wpm = self.calculate_wpm(duration_seconds)
                    return wpm >= min_wpm
                return True
        return False

    def should_slow_down(self) -> bool:
        """Determine if user is struggling."""
        # Slow down after three non-repeated misses or overall accuracy below 65%.
        return self.consecutive_wrong >= 3 or self.overall_accuracy() < 0.65

    def is_excelling(self) -> bool:
        """Determine if user is doing exceptionally well (for early completion)."""
        # 5+ consecutive correct AND accuracy > 90%
        return self.consecutive_correct >= 5 and self.overall_accuracy() > 0.90

    def get_struggling_keys(self) -> List[str]:
        """Return keys user struggles with."""
        struggling = []
        for key, perf in self.key_performance.items():
            if perf.attempts >= 3 and perf.recent_accuracy() < 0.75:
                struggling.append(key)
        return struggling


# =========== State Classes ===========

@dataclass
class LessonState:
    """State for typing lessons."""
    stage: int = 0
    batch_words: list = field(default_factory=list)
    batch_instructions: list = field(default_factory=list)  # Instructions for special key lessons
    index: int = 0
    typed: str = ""
    tracker: AdaptiveTracker = field(default_factory=AdaptiveTracker)
    use_words: bool = False  # Use real words vs random strings
    review_mode: bool = False  # In review mode for struggling keys
    review_keys: List[str] = field(default_factory=list)
    errors_in_row: int = 0  # Track consecutive errors for guidance
    show_guidance: bool = False  # Show tutorial-style guidance
    guidance_message: str = ""  # Visual guidance message
    hint_message: str = ""  # Additional hint text
    start_time: float = 0.0  # Lesson start time (set when batch starts)
    end_time: float = 0.0  # Lesson end time (set when batch completes)


@dataclass
class LessonIntroState:
    """State for lesson introduction (key finding)."""
    lesson_num: int = 0
    required_keys: Set[str] = field(default_factory=set)
    keys_found: Set[str] = field(default_factory=set)
    intro_items: list = field(default_factory=list)  # List of (heading, text) review items
    intro_index: int = 0  # Currently highlighted intro review item


@dataclass
class TestState:
    """State for speed tests."""
    running: bool = False
    start_time: float = 0.0
    duration_seconds: int = 60  # Configurable test duration
    duration_input: str = ""  # User's typed duration
    current: str = ""
    remaining: list = field(default_factory=list)
    typed: str = ""
    correct_chars: int = 0
    total_chars: int = 0
    sentences_completed: int = 0  # Track completed sentences
    sentences_started: int = 0  # Track sentences started (including partials)
    escape_count: int = 0  # Legacy field kept for save compatibility


@dataclass
class TutorialState:
    """State for tutorial mode."""
    phase: int = 1  # 1=space, 2=arrows, 3=enter, 4=control, 5=mix
    sequence: list = field(default_factory=list)
    index: int = 0
    required_name: str = ""
    required_key: int = 0
    counts_done: Counter = field(default_factory=Counter)
    target_counts: dict = field(default_factory=dict)  # key -> required count this phase
    key_errors: Counter = field(default_factory=Counter)  # key -> mistake count
    total_attempts: int = 0
    total_correct: int = 0
    phase_attempts: int = 0
    phase_correct: int = 0
    phase_mistakes: int = 0
    adaptive_mode: str = "normal"  # fast | normal | slow
    in_intro: bool = False  # True when reviewing key-location guidance before a phase
    intro_items: list = field(default_factory=list)  # List of (name, description)
    intro_index: int = 0
    guidance_message: str = ""  # Visual guidance when wrong key pressed
    hint_message: str = ""  # Additional hint text


@dataclass
class FreePracticeState:
    """State for free practice mode."""
    selected_keys: Set[str] = field(default_factory=set)  # Keys selected for practice
    available_keys: Set[str] = field(default_factory=set)  # All learned keys
    available_lessons: List[int] = field(default_factory=list)  # Unlocked lessons available for free practice
    lesson_index: int = 0  # Currently highlighted free practice lesson choice
    selected_lesson: int = 0  # Selected lesson used to build the current practice key set
    in_session: bool = False  # Whether currently practicing


@dataclass
class Settings:
    """User settings and preferences."""
    show_tutorial: bool = True
    unlocked_lessons: Set[int] = field(default_factory=lambda: {0})  # Start with lesson 0 unlocked
    current_lesson: int = 0  # Currently selected lesson
    # Speech options
    speech_mode: str = "auto"  # "auto", "screen_reader", "tts", "off"
    typing_sound_intensity: str = "normal"  # "subtle", "normal", "strong"
    # TTS options (for pyttsx3)
    tts_rate: int = 200  # Words per minute (default 200, range 50-400)
    tts_volume: float = 1.0  # Volume level (0.0-1.0)
    tts_voice: str = ""  # Voice ID (empty = default voice)
    # Visual options
    visual_theme: str = "auto"  # "auto", "dark", "light", "high_contrast"
    font_scale: str = "auto"  # "auto" (DPI-detected), "100%", "125%", "150%"
    focus_assist: bool = False  # Stronger visual emphasis for the active area
    # Sentence language/practice topic (canonical list is in modules/sentences_manager.py)
    sentence_language: str = "English"
    auto_update_check: bool = True  # Check GitHub releases on startup when installed
    auto_start_next_lesson: bool = False  # Skip the post-lesson choice screen and start the next lesson automatically
    # Daily streak tracking
    current_streak: int = 0  # Current streak in days
    last_practice_date: str = ""  # Last practice date in YYYY-MM-DD format
    longest_streak: int = 0  # Longest streak ever achieved
    lesson_stars: Dict[int, int] = field(default_factory=dict)  # lesson_num: stars (1-3)
    lesson_best_wpm: Dict[int, float] = field(default_factory=dict)  # lesson_num: best WPM
    lesson_best_accuracy: Dict[int, float] = field(default_factory=dict)  # lesson_num: best accuracy
    earned_badges: Set[str] = field(default_factory=set)  # Set of earned badge IDs
    badge_notifications: List[str] = field(default_factory=list)  # Queue of badges to announce
    total_lessons_completed: int = 0  # Total count of completed lessons
    total_practice_time: float = 0.0  # Total practice time in seconds
    highest_wpm: float = 0.0  # Highest WPM ever achieved
    xp: int = 0  # Total experience points
    level: int = 1  # Current level (1-10)
    key_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)  # key: {attempts, correct, errors}
    daily_challenge_date: str = ""  # Date of current challenge (YYYY-MM-DD)
    daily_challenge_completed: bool = False  # Whether today's challenge is complete
    daily_challenge_streak: int = 0  # Consecutive days completing challenges
    active_quests: Dict[str, Dict] = field(default_factory=dict)  # quest_id: {progress, target, completed}
    completed_quests: Set[str] = field(default_factory=set)  # Set of completed quest IDs
    quest_notifications: List[str] = field(default_factory=list)  # Queue of quests to announce
    session_history: List[Dict] = field(default_factory=list)  # List of session data
    coins: int = 0  # Virtual currency balance
    total_coins_earned: int = 0  # Lifetime total coins earned
    owned_items: Set[str] = field(default_factory=set)  # Set of owned permanent items
    inventory: Dict[str, int] = field(default_factory=dict)  # item_id: quantity for consumables
    pet_type: str = ""  # Pet type (robot, dragon, owl, cat, dog, phoenix, tribble)
    pet_name: str = ""  # Custom pet name
    pet_xp: int = 0  # Pet's XP (grows with user)
    pet_happiness: int = 50  # Pet happiness (0-100)
    pet_mood: str = "happy"  # Current mood
    pet_last_fed: str = ""  # Last fed timestamp (ISO format)


@dataclass
class AppState:
    """Overall application state."""
    mode: str = "MENU"
    settings: Settings = field(default_factory=Settings)
    lesson: LessonState = field(default_factory=LessonState)
    lesson_intro: LessonIntroState = field(default_factory=LessonIntroState)
    test: TestState = field(default_factory=TestState)
    tutorial: TutorialState = field(default_factory=TutorialState)
    free_practice: FreePracticeState = field(default_factory=FreePracticeState)
    results_title: str = ""
    results_instructions: str = ""
    results_text: str = ""
    results_action: str = ""
    results_next_lesson: int = 0
    results_options: List[str] = field(default_factory=list)
    results_index: int = 0
    backend_label: str = ""
    menu_items: list = field(default_factory=lambda: ["Tutorial: T", "Keyboard Explorer: K", "Lessons: L", "Free Practice: F", "Speed Test: S", "Sentence Practice: S", "Open Sentences Folder: O", "Games: G", "Quests: Q", "Pets: P", "Pet Shop: P", "Badges: B", "Progress Dashboard: P", "Practice Log: P", "Daily Challenge: D", "Key Performance: K", "Options: O", "Learn Sounds: L", "Check for Updates: U", "Key Quest Instructions: I", "New in Key Quest: N", "About: A", "Quit: Q"])
    menu_index: int = 0
    lesson_menu_index: int = 0  # Index in lesson submenu
    options_index: int = 0  # Index in options menu
    games_menu_index: int = 0  # Index in games submenu


# =========== Progress Management ===========

PROGRESS_SCHEMA_VERSION = 1

class ProgressManager:
    """Manages saving and loading user progress."""

    def __init__(self, filename: str = "progress.json"):
        self.filename = filename

    def load(self, state: AppState, stage_letters_count: int) -> bool:
        """Load progress from file and update app state.

        Args:
            state: AppState object to update
            stage_letters_count: Number of available lessons (for validation)

        Returns:
            True if progress loaded successfully, False if defaults were used.
        """
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            _schema_version = int(data.get("schema_version", 0))

            # Load current lesson
            current = int(data.get("current_lesson", 0))
            if 0 <= current < stage_letters_count:
                state.settings.current_lesson = current
                state.lesson.stage = current

            # Load unlocked lessons
            unlocked = data.get("unlocked_lessons", [0])
            state.settings.unlocked_lessons = set(unlocked)

            # Load options
            state.settings.speech_mode = data.get("speech_mode", "auto")
            state.settings.typing_sound_intensity = data.get("typing_sound_intensity", "normal")
            state.settings.visual_theme = data.get("visual_theme", "auto")
            state.settings.font_scale = data.get("font_scale", "auto")
            state.settings.focus_assist = data.get("focus_assist", False)
            state.settings.sentence_language = data.get("sentence_language", "English")
            state.settings.auto_update_check = data.get("auto_update_check", True)
            state.settings.auto_start_next_lesson = data.get("auto_start_next_lesson", False)

            state.settings.tts_rate = data.get("tts_rate", 200)
            state.settings.tts_volume = data.get("tts_volume", 1.0)
            state.settings.tts_voice = data.get("tts_voice", "")

            state.settings.current_streak = data.get("current_streak", 0)
            state.settings.last_practice_date = data.get("last_practice_date", "")
            state.settings.longest_streak = data.get("longest_streak", 0)

            lesson_stars_data = data.get("lesson_stars", {})
            state.settings.lesson_stars = {int(k): int(v) for k, v in lesson_stars_data.items()}

            lesson_best_wpm_data = data.get("lesson_best_wpm", {})
            state.settings.lesson_best_wpm = {int(k): float(v) for k, v in lesson_best_wpm_data.items()}

            lesson_best_accuracy_data = data.get("lesson_best_accuracy", {})
            state.settings.lesson_best_accuracy = {int(k): float(v) for k, v in lesson_best_accuracy_data.items()}

            state.settings.earned_badges = set(data.get("earned_badges", []))
            state.settings.badge_notifications = data.get("badge_notifications", [])
            state.settings.total_lessons_completed = data.get("total_lessons_completed", 0)
            state.settings.total_practice_time = data.get("total_practice_time", 0.0)
            state.settings.highest_wpm = data.get("highest_wpm", 0.0)

            state.settings.xp = data.get("xp", 0)
            state.settings.level = data.get("level", 1)
            state.settings.key_stats = data.get("key_stats", {})
            state.settings.daily_challenge_date = data.get("daily_challenge_date", "")
            state.settings.daily_challenge_completed = data.get("daily_challenge_completed", False)
            state.settings.daily_challenge_streak = data.get("daily_challenge_streak", 0)
            state.settings.active_quests = data.get("active_quests", {})
            state.settings.completed_quests = set(data.get("completed_quests", []))
            state.settings.quest_notifications = data.get("quest_notifications", [])
            state.settings.session_history = data.get("session_history", [])
            state.settings.coins = data.get("coins", 0)
            state.settings.total_coins_earned = data.get("total_coins_earned", 0)
            state.settings.owned_items = set(data.get("owned_items", []))
            state.settings.inventory = data.get("inventory", {})
            state.settings.pet_type = data.get("pet_type", "")
            state.settings.pet_name = data.get("pet_name", "")
            state.settings.pet_xp = data.get("pet_xp", 0)
            state.settings.pet_happiness = data.get("pet_happiness", 50)
            state.settings.pet_mood = data.get("pet_mood", "happy")
            state.settings.pet_last_fed = data.get("pet_last_fed", "")

            # Passive happiness decay: 5 points per day since last fed, floor at 0.
            if state.settings.pet_type and state.settings.pet_last_fed:
                try:
                    last_fed = date.fromisoformat(state.settings.pet_last_fed[:10])
                    days_away = (date.today() - last_fed).days
                    if days_away > 0:
                        state.settings.pet_happiness = max(
                            0, state.settings.pet_happiness - days_away * 5
                        )
                except ValueError:
                    pass

            # Ensure current lesson is unlocked and at least lesson 0 is unlocked
            state.settings.unlocked_lessons.add(0)
            state.settings.unlocked_lessons.add(state.settings.current_lesson)
            return True
        except FileNotFoundError:
            state.settings.current_lesson = 0
            state.settings.unlocked_lessons = {0}
            state.lesson.stage = 0
            state.settings.speech_mode = "auto"
            state.settings.typing_sound_intensity = "normal"
            state.settings.visual_theme = "auto"
            state.settings.font_scale = "auto"
            state.settings.focus_assist = False
            state.settings.sentence_language = "English"
            state.settings.auto_update_check = True
            state.settings.auto_start_next_lesson = False
            return False
        except Exception:
            # Use defaults on load failure
            error_logging.log_message(
                "Progress load failed — using defaults",
                f"File: {self.filename}",
                traceback.format_exc(),
            )
            state.settings.current_lesson = 0
            state.settings.unlocked_lessons = {0}
            state.lesson.stage = 0
            state.settings.speech_mode = "auto"
            state.settings.typing_sound_intensity = "normal"
            state.settings.visual_theme = "auto"
            state.settings.font_scale = "auto"
            state.settings.focus_assist = False
            state.settings.sentence_language = "English"
            state.settings.auto_update_check = True
            state.settings.auto_start_next_lesson = False
            return False

    def save(self, state: AppState) -> None:
        """Save progress to file.

        Args:
            state: AppState object to save
        """
        try:
            data = {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "current_lesson": int(state.settings.current_lesson),
                "unlocked_lessons": sorted(list(state.settings.unlocked_lessons)),
                "speech_mode": state.settings.speech_mode,
                "typing_sound_intensity": state.settings.typing_sound_intensity,
                "visual_theme": state.settings.visual_theme,
                "font_scale": state.settings.font_scale,
                "focus_assist": state.settings.focus_assist,
                "sentence_language": state.settings.sentence_language,
                "auto_update_check": state.settings.auto_update_check,
                "auto_start_next_lesson": state.settings.auto_start_next_lesson,
                "tts_rate": state.settings.tts_rate,
                "tts_volume": state.settings.tts_volume,
                "tts_voice": state.settings.tts_voice,
                "current_streak": state.settings.current_streak,
                "last_practice_date": state.settings.last_practice_date,
                "longest_streak": state.settings.longest_streak,
                "lesson_stars": {str(k): v for k, v in state.settings.lesson_stars.items()},
                "lesson_best_wpm": {str(k): v for k, v in state.settings.lesson_best_wpm.items()},
                "lesson_best_accuracy": {str(k): v for k, v in state.settings.lesson_best_accuracy.items()},
                "earned_badges": sorted(list(state.settings.earned_badges)),
                "badge_notifications": state.settings.badge_notifications,
                "total_lessons_completed": state.settings.total_lessons_completed,
                "total_practice_time": state.settings.total_practice_time,
                "highest_wpm": state.settings.highest_wpm,
                "xp": state.settings.xp,
                "level": state.settings.level,
                "key_stats": state.settings.key_stats,
                "daily_challenge_date": state.settings.daily_challenge_date,
                "daily_challenge_completed": state.settings.daily_challenge_completed,
                "daily_challenge_streak": state.settings.daily_challenge_streak,
                "active_quests": state.settings.active_quests,
                "completed_quests": sorted(list(state.settings.completed_quests)),
                "quest_notifications": state.settings.quest_notifications,
                "session_history": state.settings.session_history,
                "coins": state.settings.coins,
                "total_coins_earned": state.settings.total_coins_earned,
                "owned_items": sorted(list(state.settings.owned_items)),
                "inventory": state.settings.inventory,
                "pet_type": state.settings.pet_type,
                "pet_name": state.settings.pet_name,
                "pet_xp": state.settings.pet_xp,
                "pet_happiness": state.settings.pet_happiness,
                "pet_mood": state.settings.pet_mood,
                "pet_last_fed": state.settings.pet_last_fed
            }
            tmp = pathlib.Path(str(self.filename) + ".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self.filename)
        except Exception:
            # Progress save failures should not crash the app.
            error_logging.log_message(
                "Progress save failed",
                f"File: {self.filename}",
                traceback.format_exc(),
            )
