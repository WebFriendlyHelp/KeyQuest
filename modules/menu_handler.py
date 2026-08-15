"""Menu handling utilities for KeyQuest.

Provides menu navigation helpers, option explanations, and Menu classes.
"""

import pygame

from modules import sentences_manager


# =========== Options Explanations ===========

def get_speech_mode_explanation(mode: str) -> str:
    """Get explanation for a speech mode setting."""
    explanations = {
        "auto": "Automatically chooses the most reliable speech backend. It prefers built-in text-to-speech when available and falls back to your screen reader if needed.",
        "screen_reader": "Uses your screen reader only. Screen reader must be running.",
        "tts": "Uses built-in text-to-speech engine only.",
        "off": "Disables all speech output."
    }
    return explanations.get(mode, "")


def get_theme_explanation(theme: str) -> str:
    """Get explanation for a visual theme setting."""
    explanations = {
        "auto": "Automatically detects your system's light or dark theme preference and matches it.",
        "dark": "Dark theme with white text on black background.",
        "light": "Light theme with black text on white background.",
        "high_contrast": "High contrast theme with yellow accents for maximum visibility."
    }
    return explanations.get(theme, "")


def get_language_explanation(language: str) -> str:
    """Get explanation for a sentence language/topic setting."""
    return sentences_manager.get_practice_topic_explanation(language)


def get_tts_rate_explanation(rate: int) -> str:
    """Get explanation for TTS rate setting."""
    return f"Speech speed: {rate} words per minute. Adjust faster or slower to your preference."


def get_tts_volume_explanation(volume: float) -> str:
    """Get explanation for TTS volume setting."""
    percent = int(volume * 100)
    return f"Speech volume: {percent}%. Adjust the loudness of text-to-speech."


def get_tts_voice_explanation(voice_name: str) -> str:
    """Get explanation for TTS voice setting."""
    if not voice_name:
        return "Voice: Default. Use left/right arrows to select a different voice."
    return f"Voice: {voice_name}. Use left/right arrows to change voice."


def get_typing_sound_intensity_explanation(intensity: str) -> str:
    """Get explanation for typing sound intensity setting."""
    explanations = {
        "subtle": "Quieter typing beeps with less emphasis.",
        "normal": "Balanced typing beeps for most environments.",
        "strong": "Louder, clearer typing beeps for noisy setups."
    }
    return explanations.get(intensity, "")


def get_auto_update_explanation(enabled: bool) -> str:
    """Get explanation for the automatic update setting."""
    if enabled:
        return "Checks GitHub for a new installer at startup and installs it automatically from the menu."
    return "Does not check for updates automatically. Use Check for Updates from the main menu."


def get_speech_log_explanation(enabled: bool) -> str:
    """Get explanation for the speech transcript setting."""
    if enabled:
        return (
            "Writing every announcement, and every one that was skipped, to "
            "keyquest_speech.log in the KeyQuest folder. Turn this on only when "
            "asked to, then send the file in."
        )
    return (
        "Off. Turn this on to record what KeyQuest says, which helps diagnose "
        "speech that goes quiet or repeats."
    )


def get_focus_assist_explanation(enabled: bool) -> str:
    """Get explanation for the focus assist setting."""
    if enabled:
        return "Uses stronger panels and focus emphasis to make the active area easier to spot visually."
    return "Uses the standard visual emphasis level."


def get_auto_start_next_lesson_explanation(enabled: bool) -> str:
    """Get explanation for automatic next-lesson start behavior."""
    if enabled:
        return "Starts the next unlocked lesson automatically after a successful lesson."
    return "Shows a choice screen after each lesson so you can start the next lesson, retry, or return to the main menu."


def get_voice_name_from_id(voice_id: str, available_voices: list) -> str:
    """Get voice name from voice ID.

    Args:
        voice_id: Voice ID to lookup
        available_voices: List of (voice_id, voice_name) tuples

    Returns:
        Voice name or "Default" if not found
    """
    if not voice_id:
        return "Default"
    for vid, vname in available_voices:
        if vid == voice_id:
            return vname
    return "Default"


def get_options_items(settings, show_tts_options: bool = False, available_voices: list = None) -> list:
    """Get list of option descriptions for current settings.

    Args:
        settings: Settings object with speech_mode, visual_theme, sentence_language
        show_tts_options: Whether to show TTS-specific options (rate, volume, voice)
        available_voices: List of (voice_id, voice_name) tuples for voice selection

    Returns:
        List of formatted option strings
    """
    speech_desc = f"Speech: {settings.speech_mode}"
    typing_sound_desc = f"Typing Sounds: {settings.typing_sound_intensity}"
    options = [speech_desc, typing_sound_desc]

    # Add TTS options if TTS mode is being used
    if show_tts_options:
        rate_desc = f"TTS Rate: {settings.tts_rate} WPM"
        volume_percent = int(settings.tts_volume * 100)
        volume_desc = f"TTS Volume: {volume_percent}%"
        voice_name = get_voice_name_from_id(settings.tts_voice, available_voices or [])
        voice_desc = f"TTS Voice: {voice_name}"
        options.extend([rate_desc, volume_desc, voice_desc])

    # Add visual and language options
    theme_desc = f"Visual Theme: {settings.visual_theme}"
    language_desc = (
        f"Practice Topic: {sentences_manager.get_practice_topic_display_name(settings.sentence_language)}"
    )
    auto_next_desc = f"Auto Start Next Lesson: {'On' if settings.auto_start_next_lesson else 'Off'}"
    options.extend([theme_desc, auto_next_desc, language_desc])

    return options


# =========== Menu Navigation Helpers ===========

def navigate_up(current_index: int, item_count: int) -> int:
    """Navigate up in a menu (wraps around).

    Args:
        current_index: Current menu index
        item_count: Total number of menu items

    Returns:
        New index after navigation
    """
    return (current_index - 1) % item_count


def navigate_down(current_index: int, item_count: int) -> int:
    """Navigate down in a menu (wraps around).

    Args:
        current_index: Current menu index
        item_count: Total number of menu items

    Returns:
        New index after navigation
    """
    return (current_index + 1) % item_count


def navigate_first(item_count: int) -> int:
    """Navigate to the first item in a menu."""
    return 0 if item_count > 0 else 0


def navigate_last(item_count: int) -> int:
    """Navigate to the last item in a menu."""
    return max(0, item_count - 1)


# =========== Option Cycling ===========

def cycle_speech_mode(current_mode: str, direction: str = "right") -> str:
    """Cycle through speech mode options.

    Args:
        current_mode: Current speech mode
        direction: "right" or "left"

    Returns:
        New speech mode
    """
    modes = ["auto", "screen_reader", "tts", "off"]
    current_idx = modes.index(current_mode)
    if direction == "right":
        new_idx = (current_idx + 1) % len(modes)
    else:
        new_idx = (current_idx - 1) % len(modes)
    return modes[new_idx]


def get_font_scale_explanation(scale: str) -> str:
    """Return a description of the current font scale setting."""
    if scale == "auto":
        return "Automatically matches your display's DPI scaling."
    if scale == "100%":
        return "Default text size."
    if scale == "125%":
        return "Medium larger text, good for HiDPI displays."
    if scale == "150%":
        return "Large text, easiest to read at a distance."
    if scale == "175%":
        return "Extra large text for stronger low-vision support."
    if scale == "200%":
        return "Maximum built-in text size for the clearest reading."
    return ""


def cycle_font_scale(current_scale: str, direction: str = "right") -> str:
    """Cycle through font scale options."""
    scales = ["auto", "100%", "125%", "150%", "175%", "200%"]
    try:
        current_idx = scales.index(current_scale)
    except ValueError:
        current_idx = 0
    if direction == "right":
        new_idx = (current_idx + 1) % len(scales)
    else:
        new_idx = (current_idx - 1) % len(scales)
    return scales[new_idx]


def cycle_theme(current_theme: str, direction: str = "right") -> str:
    """Cycle through visual theme options.

    Args:
        current_theme: Current theme
        direction: "right" or "left"

    Returns:
        New theme
    """
    themes = ["auto", "dark", "light", "high_contrast"]
    current_idx = themes.index(current_theme)
    if direction == "right":
        new_idx = (current_idx + 1) % len(themes)
    else:
        new_idx = (current_idx - 1) % len(themes)
    return themes[new_idx]


def cycle_language(current_language: str, direction: str = "right") -> str:
    """Cycle through sentence language and topic options.

    Args:
        current_language: Current language/topic
        direction: "right" or "left"

    Returns:
        New language/topic
    """
    languages = sentences_manager.get_practice_topics()
    try:
        current_idx = languages.index(current_language)
    except ValueError:
        current_idx = 0  # Default to English if current not found
    if direction == "right":
        new_idx = (current_idx + 1) % len(languages)
    else:
        new_idx = (current_idx - 1) % len(languages)
    return languages[new_idx]


def cycle_tts_rate(current_rate: int, direction: str = "right") -> int:
    """Cycle through TTS rate options.

    Args:
        current_rate: Current rate in WPM
        direction: "right" or "left"

    Returns:
        New rate in WPM
    """
    rates = [50, 100, 150, 200, 250, 300, 350, 400]
    # Find closest rate
    closest_idx = min(range(len(rates)), key=lambda i: abs(rates[i] - current_rate))
    if direction == "right":
        new_idx = min(closest_idx + 1, len(rates) - 1)
    else:
        new_idx = max(closest_idx - 1, 0)
    return rates[new_idx]


def cycle_tts_volume(current_volume: float, direction: str = "right") -> float:
    """Cycle through TTS volume options.

    Args:
        current_volume: Current volume (0.0-1.0)
        direction: "right" or "left"

    Returns:
        New volume (0.0-1.0)
    """
    volumes = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    # Find closest volume
    closest_idx = min(range(len(volumes)), key=lambda i: abs(volumes[i] - current_volume))
    if direction == "right":
        new_idx = min(closest_idx + 1, len(volumes) - 1)
    else:
        new_idx = max(closest_idx - 1, 0)
    return volumes[new_idx]


def cycle_tts_voice(current_voice_id: str, available_voices: list, direction: str = "right") -> str:
    """Cycle through available TTS voices.

    Args:
        current_voice_id: Current voice ID
        available_voices: List of (voice_id, voice_name) tuples
        direction: "right" or "left"

    Returns:
        New voice ID
    """
    if not available_voices:
        return ""

    voice_ids = [v[0] for v in available_voices]

    # Find current index
    try:
        current_idx = voice_ids.index(current_voice_id)
    except ValueError:
        current_idx = -1 if direction == "right" else 0

    if direction == "right":
        new_idx = (current_idx + 1) % len(voice_ids)
    else:
        new_idx = (current_idx - 1) % len(voice_ids)

    return voice_ids[new_idx]


def cycle_bool(current_value: bool, direction: str = "right") -> bool:
    """Toggle a boolean option."""
    return not bool(current_value)


def cycle_typing_sound_intensity(current_intensity: str, direction: str = "right") -> str:
    """Cycle through typing sound intensity presets."""
    levels = ["subtle", "normal", "strong"]
    try:
        current_idx = levels.index(current_intensity)
    except ValueError:
        current_idx = 1
    if direction == "right":
        new_idx = (current_idx + 1) % len(levels)
    else:
        new_idx = (current_idx - 1) % len(levels)
    return levels[new_idx]


# =========== Menu Announcement Builders ===========

def build_main_menu_announcement(current_item: str, streak_text: str = "") -> str:
    """Build the main menu announcement.

    Args:
        current_item: Currently selected menu item
        streak_text: Optional streak announcement text

    Returns:
        Full announcement string
    """
    streak_part = f"{streak_text} " if streak_text else ""
    return (
        f"Key Quest. Main menu. {streak_part}{current_item}. "
        "Use Up and Down to choose, or press first letter to jump. "
        "Press Enter or Space to select. "
        "Control Space repeats these instructions."
    )


def build_lesson_menu_announcement(lesson_name: str) -> str:
    """Build the lesson menu announcement.

    Args:
        lesson_name: Name of currently selected lesson

    Returns:
        Full announcement string
    """
    return (
        f"Lesson menu. {lesson_name}. "
        "Use Up and Down to choose. Press Enter or Space to select. "
        "Press Escape for main menu."
    )


def build_games_menu_announcement(game_name: str, game_description: str) -> str:
    """Build the games menu announcement.

    Args:
        game_name: Name of currently selected game
        game_description: Description of the game

    Returns:
        Full announcement string
    """
    return (
        f"Games menu. {game_name}. {game_description} "
        "Use Up and Down to choose. Press Enter or Space to select. "
        "Press Escape for main menu."
    )


def build_options_menu_announcement(first_option: str, explanation: str) -> str:
    """Build the options menu announcement.

    Args:
        first_option: First option in the menu
        explanation: Explanation of the first option

    Returns:
        Full announcement string
    """
    return (
        f"Options menu. {first_option}. {explanation} "
        "Use Up and Down arrows to navigate. "
        "Use Left and Right arrows to change settings. "
        "Press Escape to return to main menu."
    )


# =========== Menu Classes ===========

class Menu:
    """Generic menu system with navigation and selection.

    Handles common menu operations: up/down navigation, selection, escape.
    Supports both static and dynamic item lists.
    """

    def __init__(self, name, items, speech_system, on_select_callback,
                 get_item_text_func=None, initial_announcement=None,
                 on_escape_callback=None, enable_letter_nav=False):
        """Initialize menu.

        Args:
            name: Menu name for announcements
            items: List of items OR callable that returns list
            speech_system: Speech system for announcements
            on_select_callback: Function(item) called when item selected
            get_item_text_func: Optional function(item) -> str for item announcement
            initial_announcement: Optional custom announcement when menu opens
            on_escape_callback: Optional function() called on escape
            enable_letter_nav: Enable first letter navigation (True for main menu)
        """
        self.name = name
        self._items_source = items
        self.speech = speech_system
        self.on_select = on_select_callback
        self.get_item_text = get_item_text_func or str
        self.initial_announcement = initial_announcement
        self.on_escape = on_escape_callback
        self.current_index = 0
        self.enable_letter_nav = enable_letter_nav
        self.letter_cycle_index = {}  # Track cycling through items with same first letter

    def get_items(self):
        """Get current list of items (supports dynamic lists)."""
        if callable(self._items_source):
            return self._items_source()
        return self._items_source

    def get_current_item(self):
        """Get currently selected item."""
        items = self.get_items()
        if not items:
            return None
        return items[self.current_index]

    def reset_index(self):
        """Reset to first item."""
        self.current_index = 0

    def announce_current(self):
        """Announce the current menu item."""
        item = self.get_current_item()
        if item is not None:
            text = self.get_item_text(item)
            self.speech.say(text)

    def announce_menu(self):
        """Announce menu opening with current item."""
        if self.initial_announcement:
            self.speech.say(self.initial_announcement(), priority=True, protect_seconds=2.0)
        else:
            item = self.get_current_item()
            if item is not None:
                text = self.get_item_text(item)
                self.speech.say(f"{self.name} menu. {text}", priority=True, protect_seconds=2.0)

    def navigate_up(self):
        """Navigate to previous item."""
        items = self.get_items()
        if items:
            self.current_index = (self.current_index - 1) % len(items)
            self.announce_current()

    def navigate_down(self):
        """Navigate to next item."""
        items = self.get_items()
        if items:
            self.current_index = (self.current_index + 1) % len(items)
            self.announce_current()

    def navigate_first(self):
        """Navigate to the first item."""
        items = self.get_items()
        if items:
            self.current_index = navigate_first(len(items))
            self.announce_current()

    def navigate_last(self):
        """Navigate to the last item."""
        items = self.get_items()
        if items:
            self.current_index = navigate_last(len(items))
            self.announce_current()

    def select_current(self):
        """Select the current item."""
        item = self.get_current_item()
        if item is not None and self.on_select:
            self.on_select(item)

    def handle_escape(self):
        """Handle escape key."""
        if self.on_escape:
            self.on_escape()

    def navigate_to_letter(self, letter):
        """Navigate to item starting with letter (cycles if multiple matches).

        Args:
            letter: Letter to search for (case-insensitive)
        """
        if not self.enable_letter_nav:
            return False

        items = self.get_items()
        if not items:
            return False

        letter = letter.upper()

        # Find all items starting with this letter
        matching_indices = []
        for i, item in enumerate(items):
            item_text = self.get_item_text(item)
            if item_text and item_text[0].upper() == letter:
                matching_indices.append(i)

        if not matching_indices:
            return False

        # If only one match, go to it
        if len(matching_indices) == 1:
            self.current_index = matching_indices[0]
            self.announce_current()
            self.letter_cycle_index[letter] = 0
            return True

        # Multiple matches - cycle through them
        if letter not in self.letter_cycle_index:
            # First time pressing this letter, go to first match
            self.letter_cycle_index[letter] = 0
        else:
            # Already cycled before, go to next match
            self.letter_cycle_index[letter] = (self.letter_cycle_index[letter] + 1) % len(matching_indices)

        self.current_index = matching_indices[self.letter_cycle_index[letter]]
        self.announce_current()
        return True

    def handle_input(self, event, mods=None):
        """Handle keyboard input.

        Args:
            event: Pygame event
            mods: Optional keyboard modifiers

        Returns:
            True if input was handled, False otherwise
        """
        if event.key == pygame.K_UP:
            self.navigate_up()
            return True
        elif event.key == pygame.K_DOWN:
            self.navigate_down()
            return True
        elif event.key == pygame.K_HOME:
            self.navigate_first()
            return True
        elif event.key == pygame.K_END:
            self.navigate_last()
            return True
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.select_current()
            return True
        elif event.key == pygame.K_ESCAPE:
            self.handle_escape()
            return True
        elif self.enable_letter_nav and event.unicode and event.unicode.isalpha():
            # First letter navigation
            return self.navigate_to_letter(event.unicode)

        return False


class OptionsMenu:
    """Menu for settings that can be cycled with left/right arrows.

    Each option has multiple values that can be cycled through.
    """

    def __init__(self, name, options, speech_system, on_change_callback,
                 initial_announcement=None, on_escape_callback=None):
        """Initialize options menu.

        Args:
            name: Menu name
            options: List of dicts with 'name', 'get_value', 'set_value', 'get_text', 'get_explanation'
            speech_system: Speech system for announcements
            on_change_callback: Function(option_index, old_value, new_value) called on change
            initial_announcement: Optional custom announcement
            on_escape_callback: Optional function() called on escape
        """
        self.name = name
        self.options = options
        self.speech = speech_system
        self.on_change = on_change_callback
        self.initial_announcement = initial_announcement
        self.on_escape = on_escape_callback
        self.current_index = 0

    def get_current_option(self):
        """Get currently selected option."""
        return self.options[self.current_index]

    def reset_index(self):
        """Reset to first option."""
        self.current_index = 0

    def announce_current(self, include_explanation=True):
        """Announce the current option."""
        opt = self.get_current_option()
        text = opt['get_text']()
        if include_explanation:
            explanation = opt['get_explanation']()
            self.speech.say(f"{text}. {explanation}")
        else:
            self.speech.say(text)

    def announce_menu(self):
        """Announce menu opening."""
        if self.initial_announcement:
            self.speech.say(self.initial_announcement(), priority=True, protect_seconds=3.0)
        else:
            self.announce_current(include_explanation=True)

    def navigate_up(self):
        """Navigate to previous option."""
        self.current_index = (self.current_index - 1) % len(self.options)
        self.announce_current(include_explanation=True)

    def navigate_down(self):
        """Navigate to next option."""
        self.current_index = (self.current_index + 1) % len(self.options)
        self.announce_current(include_explanation=True)

    def navigate_first(self):
        """Navigate to the first option."""
        self.current_index = navigate_first(len(self.options))
        self.announce_current(include_explanation=True)

    def navigate_last(self):
        """Navigate to the last option."""
        self.current_index = navigate_last(len(self.options))
        self.announce_current(include_explanation=True)

    def cycle_current(self, direction):
        """Cycle current option value left or right.

        Args:
            direction: "left" or "right"
        """
        opt = self.get_current_option()
        old_value = opt['get_value']()
        new_value = opt['cycle'](old_value, direction)
        opt['set_value'](new_value)

        if self.on_change:
            self.on_change(self.current_index, old_value, new_value)

        # Announce the change
        text = opt['get_text']()
        explanation = opt['get_explanation']()
        self.speech.say(f"{text}. {explanation}")

    def handle_input(self, event, mods=None):
        """Handle keyboard input.

        Args:
            event: Pygame event
            mods: Optional keyboard modifiers

        Returns:
            True if input was handled, False otherwise
        """
        if event.key == pygame.K_UP:
            self.navigate_up()
            return True
        elif event.key == pygame.K_DOWN:
            self.navigate_down()
            return True
        elif event.key == pygame.K_HOME:
            self.navigate_first()
            return True
        elif event.key == pygame.K_END:
            self.navigate_last()
            return True
        elif event.key == pygame.K_LEFT:
            self.cycle_current("left")
            return True
        elif event.key == pygame.K_RIGHT:
            self.cycle_current("right")
            return True
        elif event.key == pygame.K_ESCAPE:
            if self.on_escape:
                self.on_escape()
            return True

        return False
