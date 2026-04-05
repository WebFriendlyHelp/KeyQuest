"""Lesson management system for KeyQuest.

Centralizes all lesson-related constants, data, and logic for the typing lesson system.
"""

import os
import random

from modules import speech_format

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
except Exception:  # pragma: no cover
    pygame = None


# =========== Lesson Batch Configuration ===========

LESSON_BATCH = 20  # Base lesson length (adapts based on performance)
MIN_LESSON_BATCH = 12  # Minimum items before early completion check
MAX_LESSON_BATCH = 30  # Maximum items for struggling students
MIN_WPM = 20  # Minimum words per minute for advancement (lessons with phrases)
WPM_REQUIRED_FROM_LESSON = 6  # Start requiring WPM from this lesson (when phrases begin)


# =========== Lesson Progression Data ===========

# NEW LESSON PROGRESSION: Start from tutorial keys, immediately add new keys
# Tutorial taught space/enter, now learn letters!
STAGE_LETTERS = [
    {" ", "a"},                 # Lesson 0: Add 'a' (first new key! left pinky)
    {"s"},                      # Lesson 1: Add 's' (left ring)
    {"d"},                      # Lesson 2: Add 'd' (left middle)
    {"f"},                      # Lesson 3: Add 'f' (left index) - LEFT HOMEROW COMPLETE!
    {"j"},                      # Lesson 4: Add 'j' (right index)
    {"k"},                      # Lesson 5: Add 'k' (right middle)
    {"l"},                      # Lesson 6: Add 'l' (right ring)
    {";"},                      # Lesson 7: Add ';' (right pinky) - FULL HOMEROW COMPLETE!
    {"g", "h"},                 # Lesson 8: Add 'g' and 'h' (inner homerow)
    {"e", "r"},                 # Lesson 9: Left top row - middle, index
    {"u", "i"},                 # Lesson 10: Right top row - index, middle
    {"q", "w"},                 # Lesson 11: Left top row - pinky, ring
    {"o", "p"},                 # Lesson 12: Right top row - ring, pinky
    {"t", "y"},                 # Lesson 13: Mid top row
    {"c", "v"},                 # Lesson 14: Left bottom - middle, index
    {"n", "m"},                 # Lesson 15: Right bottom - index, middle
    {"z", "x"},                 # Lesson 16: Left bottom - pinky, ring
    {",", "."},                 # Lesson 17: Right bottom - ring, pinky
    {"b"},                      # Lesson 18: Center bottom
    {"1", "2", "3"},            # Lesson 19: Left numbers
    {"4", "5", "6"},            # Lesson 20: Mid numbers
    {"7", "8", "9", "0"},       # Lesson 21: Right numbers
    {"'", "/"},                 # Lesson 22: Punctuation
    {"[", "]", "-", "="},       # Lesson 23: More punctuation (brackets, minus, equals)
    {"`", "\\"},                # Lesson 24: Backtick and backslash
    {"tab"},                    # Lesson 25: Tab key
    {"backspace", "delete"},    # Lesson 26: Backspace and Delete
    {"insert", "home", "end"},  # Lesson 27: Insert, Home, End
    {"pageup", "pagedown"},     # Lesson 28: Page Up and Page Down
    {"f1", "f2", "f3", "f4"},   # Lesson 29: Function keys F1-F4
    {"f5", "f6", "f7", "f8"},   # Lesson 30: Function keys F5-F8
    {"f9", "f10", "f11", "f12"},# Lesson 31: Function keys F9-F12
    {"capslock"},               # Lesson 32: Caps Lock
]

# Friendly lesson names for the menu
LESSON_NAMES = [
    "Letter A (Left Pinky)",              # 0: First new key!
    "Letter S (Left Ring)",               # 1
    "Letter D (Left Middle)",             # 2
    "Letter F (Left Index)",              # 3: Left homerow complete
    "Letter J (Right Index)",             # 4
    "Letter K (Right Middle)",            # 5
    "Letter L (Right Ring)",              # 6
    "Semicolon (Right Pinky)",            # 7: Full homerow complete!
    "Letters G and H (Center)",           # 8
    "Letters E and R (Top Left)",         # 9
    "Letters U and I (Top Right)",        # 10
    "Letters Q and W (Far Top Left)",     # 11
    "Letters O and P (Far Top Right)",    # 12
    "Letters T and Y (Top Center)",       # 13
    "Letters C and V (Bottom Left)",      # 14
    "Letters N and M (Bottom Right)",     # 15
    "Letters Z and X (Far Bottom Left)",  # 16
    "Comma and Period (Far Bottom Right)",# 17
    "Letter B (Bottom Center)",           # 18
    "Numbers 1, 2, 3",                    # 19
    "Numbers 4, 5, 6",                    # 20
    "Numbers 7, 8, 9, 0",                 # 21
    "Punctuation apostrophe slash",       # 22
    "Brackets Minus Equals",              # 23
    "Backtick and Backslash",             # 24
    "Tab Key",                            # 25
    "Backspace and Delete",               # 26
    "Insert, Home, End",                  # 27
    "Page Up and Page Down",              # 28
    "Function Keys F1-F4",                # 29
    "Function Keys F5-F8",                # 30
    "Function Keys F9-F12",               # 31
    "Caps Lock",                          # 32
]

# Key location descriptions for touch typists.
# These keys are indexed by actual lesson number so the intro always matches the lesson selected.
KEY_LOCATIONS = {
    0: {  # Letter A
        "keys": "a",
        "description": "Letter A is on the home row, left side.",
        "location": "Rest your left hand on the keyboard. Your left pinky finger should naturally rest on the A key. It is the leftmost key of the home row.",
        "finding": "From the space bar, move your left hand up two rows. The leftmost key under your pinky is A.",
    },
    1: {  # Letter S
        "keys": "s",
        "description": "Letter S is on the home row, next to A.",
        "location": "Keep your left hand on the home row. Your left ring finger rests on S, just to the right of A.",
        "finding": "From A, move one key to the right. That is S under your ring finger.",
    },
    2: {  # Letter D
        "keys": "d",
        "description": "Letter D is on the home row, between S and F.",
        "location": "Your left middle finger naturally rests on D. It is the third key from the left on the home row.",
        "finding": "From S, move one key to the right. That is D under your middle finger.",
    },
    3: {  # Letter F
        "keys": "f",
        "description": "Letter F is on the home row. It usually has a small raised bump.",
        "location": "Your left index finger rests on F. Feel for the small bump or ridge on F. If your hand is lined up correctly there, your left pinky should land on A.",
        "finding": "From D, move one key to the right. F has the tactile marker that helps you find home row quickly.",
    },
    4: {  # Letter J
        "keys": "j",
        "description": "Letter J is on the home row, right side, and usually has a small raised bump.",
        "location": "Your right index finger rests on J. Feel for the bump on J to confirm your right hand is on home row.",
        "finding": "From the space bar with your right hand, move up two rows until your index finger feels the bump on J.",
    },
    5: {  # Letter K
        "keys": "k",
        "description": "Letter K is on the home row, next to J.",
        "location": "Your right middle finger rests on K, just to the right of J.",
        "finding": "From J, move one key to the right. That is K under your middle finger.",
    },
    6: {  # Letter L
        "keys": "l",
        "description": "Letter L is on the home row, next to K.",
        "location": "Your right ring finger rests on L.",
        "finding": "From K, move one key to the right. That is L under your ring finger.",
    },
    7: {  # Semicolon
        "keys": ";",
        "description": "Semicolon is on the home row, rightmost.",
        "location": "Your right pinky finger rests on the semicolon key. It is the rightmost key of the home row.",
        "finding": "From L, move one key to the right. That is semicolon under your pinky.",
    },
    8: {  # Letters G and H
        "keys": "gh",
        "description": "Letters G and H are in the center of the home row.",
        "location": "G is just to the right of F for your left index finger. H is just to the left of J for your right index finger.",
        "finding": "Feel the bumps on F and J first. G sits beside F, and H sits beside J.",
    },
    9: {  # Letters E and R
        "keys": "er",
        "description": "Letters E and R are on the top left row.",
        "location": "Your left middle finger reaches up to E. Your left index finger reaches up to R.",
        "finding": "From D, move up to E. From F, move up to R.",
    },
    10: {  # Letters U and I
        "keys": "ui",
        "description": "Letters U and I are on the top right row.",
        "location": "Your right index finger reaches up to U. Your right middle finger reaches up to I.",
        "finding": "From J, move up to U. From K, move up to I.",
    },
}

# Keyboard layout for directional hints: key -> (row, col, finger)
# Row 0 = top (numbers), Row 1 = top letters (qwerty), Row 2 = home row, Row 3 = bottom
# Finger: "left pinky", "left ring", "left middle", "left index", "right index", "right middle", "right ring", "right pinky"
KEYBOARD_LAYOUT = {
    # Home row (row 2)
    'a': (2, 0, "left pinky"), 's': (2, 1, "left ring"), 'd': (2, 2, "left middle"), 'f': (2, 3, "left index"),
    'g': (2, 4, "left index"), 'h': (2, 5, "right index"), 'j': (2, 6, "right index"), 'k': (2, 7, "right middle"),
    'l': (2, 8, "right ring"), ';': (2, 9, "right pinky"),
    # Top row (row 1)
    'q': (1, 0, "left pinky"), 'w': (1, 1, "left ring"), 'e': (1, 2, "left middle"), 'r': (1, 3, "left index"),
    't': (1, 4, "left index"), 'y': (1, 5, "right index"), 'u': (1, 6, "right index"), 'i': (1, 7, "right middle"),
    'o': (1, 8, "right ring"), 'p': (1, 9, "right pinky"),
    # Bottom row (row 3)
    'z': (3, 0, "left pinky"), 'x': (3, 1, "left ring"), 'c': (3, 2, "left middle"), 'v': (3, 3, "left index"),
    'b': (3, 4, "left index"), 'n': (3, 5, "right index"), 'm': (3, 6, "right index"), ',': (3, 7, "right middle"),
    '.': (3, 8, "right ring"), '/': (3, 9, "right pinky"),
    # Numbers (row 0)
    '1': (0, 0, "left pinky"), '2': (0, 1, "left ring"), '3': (0, 2, "left middle"), '4': (0, 3, "left index"),
    '5': (0, 4, "left index"), '6': (0, 5, "right index"), '7': (0, 6, "right index"), '8': (0, 7, "right middle"),
    '9': (0, 8, "right ring"), '0': (0, 9, "right pinky"),
    # Special
    "'": (2, 10, "right pinky"),
    ' ': (4, 0, "thumb"),  # Space bar is special
}

# Common words for each lesson (once user shows proficiency)
STAGE_WORDS = {
    0: ["a"],  # Lesson 0: Add 'a' (first letter!)
    1: ["as"],  # Lesson 1: Add 's'
    2: ["ad", "sad", "dad", "as", "ads"],  # Lesson 2: Add 'd'
    3: ["fad", "sad", "dad", "ads", "adds", "sass"],  # Lesson 3: Add 'f' (left homerow!)
    # Lesson 4: no real English words possible with j, a, s, d, f only
    5: ["ask", "asks"],  # Lesson 5: Add 'k'
    6: ["lad", "lass", "all", "fall", "salad"],  # Lesson 6: Add 'l'
    # Lesson 7: semicolon targets are clearer when spelled out letter by letter
    8: ["had", "has", "gag", "shag", "hash", "gash", "lag", "glad", "flag"],  # Lesson 8: Add g, h
    9: ["red", "fed", "deer", "fear", "read", "seed", "here", "her"],  # Lesson 9: Add e, r
    10: ["rude", "fused", "used", "ruse", "fuse", "user"],  # Lesson 10: Add u, i
    11: ["was", "war", "wed", "weed", "saw", "raw"],  # Lesson 11: Add q, w
    12: ["pop", "rope", "pope", "pore", "sore", "pour", "opus"],  # Lesson 12: Add o, p
    13: ["type", "yet", "toy", "try", "tray", "turf", "your"],  # Lesson 13: Add t, y
    14: ["cave", "vice", "voice", "vector"],  # Lesson 14: Add c, v
    15: ["name", "men", "main", "noun", "norm"],  # Lesson 15: Add n, m
    16: ["zap", "zeal", "exam", "wax", "axes"],  # Lesson 16: Add z, x
    # Lesson 17: punctuation targets are clearer when spelled out (e.g. "m, o, r, e, period")
    # Remaining lessons use random practice
}

# Phrases for later lessons
STAGE_PHRASES = {
    6: ["a lad", "a lass", "all fall"],  # Lesson 6: With 'l'
    8: ["had a", "has a", "gag dash", "add dad", "shag flag"],  # Lesson 8: Full homerow + g, h
    9: ["read here", "feed her", "she read", "feel free"],  # Lesson 9: With e, r
    10: ["use us", "sure fire", "hire us", "fur rug"],  # Lesson 10: With u, i
    11: ["we were", "was here", "saw her", "few were"],  # Lesson 11: With q, w
    12: ["poor pop", "pour pop", "sour pop", "proof read"],  # Lesson 12: With o, p
    13: ["try your", "toy story", "true try", "pretty tray"],  # Lesson 13: With t, y
    # More phrases as needed
}


def _stage_allowed_characters(stage: int) -> set[str]:
    """Return all characters that are valid for the given lesson stage."""
    return set().union(*STAGE_LETTERS[: stage + 1])


def content_uses_only_introduced_keys(stage: int, text: str) -> bool:
    """Return True when every character in text belongs to the lesson's unlocked keys."""
    return set(text) <= _stage_allowed_characters(stage)


def filter_stage_content(stage: int, items: list[str]) -> list[str]:
    """Drop authored lesson content that includes keys from future lessons."""
    return [item for item in items if content_uses_only_introduced_keys(stage, item)]


def get_stage_natural_words(stage: int) -> set[str]:
    """Return authored lowercase words that should be spoken naturally in prompts.

    Accumulates across all stages up to and including the current one so that
    words learned in earlier lessons are still spoken naturally in later lessons.
    """
    natural_words: set[str] = set()

    for s in range(stage + 1):
        for word in filter_stage_content(stage, STAGE_WORDS.get(s, [])):
            cleaned = word.strip().lower()
            if cleaned.isalpha():
                natural_words.add(cleaned)

        for phrase in filter_stage_content(stage, STAGE_PHRASES.get(s, [])):
            for part in phrase.split():
                cleaned = part.strip().lower()
                if cleaned.isalpha():
                    natural_words.add(cleaned)

    return natural_words

# Mapping of pygame key constants to readable key names for special keys.
# Kept optional so the module can be imported in minimal environments (e.g., CI unit tests).
if pygame is not None:
    SPECIAL_KEY_NAMES = {
        pygame.K_TAB: "tab",
        pygame.K_BACKSPACE: "backspace",
        pygame.K_DELETE: "delete",
        pygame.K_INSERT: "insert",
        pygame.K_HOME: "home",
        pygame.K_END: "end",
        pygame.K_PAGEUP: "pageup",
        pygame.K_PAGEDOWN: "pagedown",
        pygame.K_F1: "f1", pygame.K_F2: "f2", pygame.K_F3: "f3", pygame.K_F4: "f4",
        pygame.K_F5: "f5", pygame.K_F6: "f6", pygame.K_F7: "f7", pygame.K_F8: "f8",
        pygame.K_F9: "f9", pygame.K_F10: "f10", pygame.K_F11: "f11", pygame.K_F12: "f12",
        pygame.K_CAPSLOCK: "capslock",
        pygame.K_LEFTBRACKET: "[",
        pygame.K_RIGHTBRACKET: "]",
        pygame.K_MINUS: "-",
        pygame.K_EQUALS: "=",
        pygame.K_BACKQUOTE: "`",
        pygame.K_BACKSLASH: "\\",
    }
else:  # pragma: no cover
    SPECIAL_KEY_NAMES = {}

# Practical keyboard command practice for special keys
# Format: (spoken_instruction, key_to_press)
SPECIAL_KEY_COMMANDS = {
    25: [  # Tab
        ("Press Tab", "tab"),
        ("Press Tab to move to next field", "tab"),
        ("Press Tab to indent in a document", "tab"),
        ("Press Tab to navigate between controls", "tab"),
        ("Press Tab", "tab"),
    ],
    26: [  # Backspace and Delete
        ("Press Backspace", "backspace"),
        ("Press Backspace to delete character before cursor", "backspace"),
        ("Press Delete", "delete"),
        ("Press Delete to remove character after cursor", "delete"),
        ("Press Backspace", "backspace"),
        ("Press Delete", "delete"),
    ],
    27: [  # Insert, Home, End
        ("Press Insert", "insert"),
        ("Press Insert to toggle insert mode", "insert"),
        ("Press Home", "home"),
        ("Press Home to jump to start of line", "home"),
        ("Press End", "end"),
        ("Press End to jump to end of line", "end"),
    ],
    28: [  # Page Up and Page Down
        ("Press Page Up", "pageup"),
        ("Press Page Up to scroll up one screen", "pageup"),
        ("Press Page Down", "pagedown"),
        ("Press Page Down to scroll down one screen", "pagedown"),
        ("Press Page Up", "pageup"),
        ("Press Page Down", "pagedown"),
    ],
    29: [  # F1-F4
        ("Press F1", "f1"),
        ("Press F1 to open help", "f1"),
        ("Press F2", "f2"),
        ("Press F2 to rename file in Windows", "f2"),
        ("Press F3", "f3"),
        ("Press F3 to search in many programs", "f3"),
        ("Press F4", "f4"),
        ("Press F4 to open address bar dropdown", "f4"),
    ],
    30: [  # F5-F8
        ("Press F5", "f5"),
        ("Press F5 to refresh a web page", "f5"),
        ("Press F6", "f6"),
        ("Press F6 to move between panes", "f6"),
        ("Press F7", "f7"),
        ("Press F7 for spell check in Word", "f7"),
        ("Press F8", "f8"),
    ],
    31: [  # F9-F12
        ("Press F9", "f9"),
        ("Press F10", "f10"),
        ("Press F11", "f11"),
        ("Press F11 for fullscreen in browsers", "f11"),
        ("Press F12", "f12"),
        ("Press F12 to save as in Office", "f12"),
    ],
    32: [  # Caps Lock
        ("Press Caps Lock", "capslock"),
        ("Press Caps Lock to toggle capital letters", "capslock"),
        ("Press Caps Lock", "capslock"),
        ("Press Caps Lock to turn off capitals", "capslock"),
    ],
}


# =========== Helper Functions ===========

def generate_words_from_keys(keys, count=15, use_real_words=True):
    """Generate practice words from a given set of keys.

    Args:
        keys: List of keys to use for word generation
        count: Number of words to generate (default 15)
        use_real_words: Whether to attempt to use real words (currently generates random combinations)

    Returns:
        List of generated words/strings
    """
    if not keys:
        keys = ['a', 's', 'd', 'f']  # Fallback to home row

    keys_list = sorted(list(keys))
    words = []

    # Generate random character combinations from the given keys
    for _ in range(count):
        # Vary length between 1-3 characters (keep it short and manageable)
        length = random.randint(1, 3)
        word = "".join(random.choice(keys_list) for _ in range(length))
        words.append(word)

    return words


def get_directional_hint(pressed: str, expected: str) -> str:
    """Generate short directional hint based on key positions."""
    pressed = pressed.lower()
    expected = expected.lower()

    # Handle special cases
    if pressed not in KEYBOARD_LAYOUT or expected not in KEYBOARD_LAYOUT:
        return f"Try {expected}."

    p_row, p_col, p_finger = KEYBOARD_LAYOUT[pressed]
    e_row, e_col, e_finger = KEYBOARD_LAYOUT[expected]

    # Calculate direction
    row_diff = e_row - p_row  # Negative = up, Positive = down
    col_diff = e_col - p_col  # Negative = left, Positive = right

    hints = []

    # Check if wrong row
    if abs(row_diff) > 0:
        if row_diff < 0:
            hints.append("a bit higher")
        else:
            hints.append("a bit lower")

    # Check horizontal direction
    if abs(col_diff) > 0:
        if abs(col_diff) == 1:
            hints.append("just to the " + ("left" if col_diff < 0 else "right"))
        elif abs(col_diff) == 2:
            hints.append("two keys " + ("left" if col_diff < 0 else "right"))
        elif col_diff < 0:
            hints.append("move left")
        else:
            hints.append("move right")

    # Always add finger hint if different finger - this is important!
    if p_finger != e_finger:
        hints.append(f"use {e_finger}")

    # Combine hints - include all important info
    if len(hints) == 0:
        return f"Try {expected}"
    elif len(hints) == 1:
        return hints[0].capitalize()
    elif len(hints) == 2:
        return hints[0].capitalize() + " " + hints[1]
    else:
        # More than 2 hints - prioritize direction + finger
        return hints[0].capitalize() + " " + hints[-1]


# =========== Lesson Manager ===========

class LessonManager:
    """Manages lesson content generation and progression logic."""

    @staticmethod
    def build_batch(lesson_state, stage: int):
        """Build a new batch of practice items for the lesson.

        Args:
            lesson_state: LessonState object to populate
            stage: Current lesson number (0-based)
        """
        lesson = lesson_state

        # Check if this is a special key lesson
        if stage in SPECIAL_KEY_COMMANDS:
            # Special key lesson - use command practice format
            commands = SPECIAL_KEY_COMMANDS[stage]
            lesson.batch_words = [cmd[1] for cmd in commands]  # The keys to press
            lesson.batch_instructions = [cmd[0] for cmd in commands]  # What to say
            lesson.use_words = False
            return

        # Regular character lesson
        lesson.batch_instructions = []  # Clear instructions for regular lessons
        allowed = set().union(*STAGE_LETTERS[:stage + 1])
        allowed_list = sorted(allowed)

        # Focus on new keys for early practice
        new_keys = STAGE_LETTERS[stage]
        new_keys_list = sorted(new_keys)

        batch_size = LESSON_BATCH
        items = []

        # Review mode focuses on struggling keys
        if lesson.review_mode and lesson.review_keys:
            # Mix struggling keys with all learned keys
            for _ in range(batch_size):
                if random.random() < 0.7:  # 70% focus on struggling keys
                    length = random.randint(2, 3)
                    word_chars = []
                    for _ in range(length):
                        if random.random() < 0.8:
                            word_chars.append(random.choice(lesson.review_keys))
                        else:
                            word_chars.append(random.choice(allowed_list))
                    items.append("".join(word_chars))
                else:
                    # General practice
                    length = random.randint(2, 4)
                    items.append("".join(random.choice(allowed_list) for _ in range(length)))
        else:
            # Normal lesson progression
            # Use phrases if available
            if stage in STAGE_PHRASES and lesson.use_words:
                phrases = STAGE_PHRASES[stage]
                for _ in range(batch_size // 2):
                    items.append(random.choice(phrases))

            # Use real words if available and use_words is True
            if stage in STAGE_WORDS and lesson.use_words:
                words = STAGE_WORDS[stage]
                remaining = batch_size - len(items)
                for _ in range(remaining):
                    items.append(random.choice(words))
            else:
                # Generate random character combinations
                remaining = batch_size - len(items)
                for i in range(remaining):
                    # First 60% of batch: focus heavily on new keys
                    if i < batch_size * 0.6:
                        # 80% chance to include at least one new key
                        if random.random() < 0.8 and new_keys_list:
                            length = random.randint(2, 4)
                            word_chars = []
                            # Ensure at least one new key in the word
                            word_chars.append(random.choice(new_keys_list))
                            for _ in range(length - 1):
                                if random.random() < 0.5:
                                    word_chars.append(random.choice(new_keys_list))
                                else:
                                    word_chars.append(random.choice(allowed_list))
                            random.shuffle(word_chars)
                            items.append("".join(word_chars))
                        else:
                            # Mix of new and old keys
                            length = random.randint(2, 4)
                            items.append("".join(random.choice(allowed_list) for _ in range(length)))
                    else:
                        # Last 40%: balanced mix
                        length = random.randint(2, 5)
                        items.append("".join(random.choice(allowed_list) for _ in range(length)))

        lesson.batch_words = items
        lesson.index = 0

    @staticmethod
    def get_prompt_parts(lesson_state):
        """Get the parts for speaking the prompt.

        Returns:
            tuple: (is_instruction, text) where is_instruction indicates if this is a
                   special key instruction or character-by-character prompt
        """
        lesson = lesson_state
        target = lesson.batch_words[lesson.index]

        # Check if this is a special key lesson with instructions
        if lesson.batch_instructions and lesson.index < len(lesson.batch_instructions):
            # Use the instruction for special key lessons
            instruction = lesson.batch_instructions[lesson.index]
            return (True, instruction)
        else:
            speakable = speech_format.spell_text_for_typing_instruction(
                target,
                natural_words=get_stage_natural_words(lesson.stage),
            )
            return (False, f"Type {speakable}")

    @staticmethod
    def extend_practice(lesson_state, stage: int):
        """Extend lesson with additional practice items for struggling students.

        Args:
            lesson_state: LessonState object to extend
            stage: Current lesson number
        """
        lesson = lesson_state
        allowed = set().union(*STAGE_LETTERS[:stage + 1])
        allowed_list = sorted(allowed)

        # Get struggling keys to focus on
        struggling = lesson.tracker.get_struggling_keys()

        # Add 5-10 more items (depending on how much room we have left)
        items_to_add = min(10, MAX_LESSON_BATCH - len(lesson.batch_words))

        new_items = []
        for _ in range(items_to_add):
            if struggling:
                # 60% chance to focus on struggling keys
                if random.random() < 0.6:
                    # Mix struggling keys with some good keys
                    length = random.randint(2, 3)
                    word_chars = []
                    for _ in range(length):
                        if random.random() < 0.7:
                            word_chars.append(random.choice(struggling))
                        else:
                            word_chars.append(random.choice(allowed_list))
                    new_items.append("".join(word_chars))
                else:
                    # Easier practice with all available keys
                    length = random.randint(2, 4)
                    new_items.append("".join(random.choice(allowed_list) for _ in range(length)))
            else:
                # General practice
                length = random.randint(2, 4)
                new_items.append("".join(random.choice(allowed_list) for _ in range(length)))

        # Add to end of batch
        lesson.batch_words.extend(new_items)

    @staticmethod
    def inject_adaptive_content(lesson_state, stage: int, current_index: int):
        """Dynamically adjust lesson difficulty mid-batch based on real-time performance.

        Args:
            lesson_state: LessonState object
            stage: Current lesson number
            current_index: Current position in batch
        """
        lesson = lesson_state

        # Only check every 5 items to avoid over-adjusting
        if current_index % 5 != 0:
            return

        # Get struggling keys
        struggling = lesson.tracker.get_struggling_keys()

        if struggling and lesson.tracker.consecutive_wrong >= 2:
            # User is struggling! Inject easier practice with familiar keys
            allowed = set().union(*STAGE_LETTERS[:stage + 1])

            # Get keys user is doing well with
            good_keys = []
            for key in allowed:
                if key not in struggling:
                    perf = lesson.tracker.key_performance.get(key)
                    if perf and perf.recent_accuracy() > 0.75:
                        good_keys.append(key)

            if good_keys:
                # Insert 3 easier words with familiar keys
                easier_words = []
                for _ in range(3):
                    length = random.randint(2, 3)
                    word = "".join(random.choice(good_keys) for _ in range(length))
                    easier_words.append(word)

                # Inject these easier words into the batch after current position
                insert_position = current_index + 1
                for i, word in enumerate(easier_words):
                    lesson.batch_words.insert(insert_position + i, word)

        elif lesson.tracker.is_excelling():
            # User is doing great! Can optionally add a challenge
            # Current behavior keeps normal progression.
            pass

    @staticmethod
    def should_continue_batch(lesson_state) -> tuple:
        """Check if lesson should continue, complete, or extend.

        Returns:
            tuple: (action, message) where action is "continue", "extend", "complete", or "early_complete"
                   and message is an optional status message
        """
        lesson = lesson_state

        # Check for early completion (if doing exceptionally well)
        if lesson.index >= MIN_LESSON_BATCH and lesson.tracker.is_excelling():
            return ("early_complete", "Excellent work! You've mastered these keys.")

        # Check if batch is complete
        if lesson.index >= len(lesson.batch_words):
            # Check if we should extend for struggling students
            if lesson.tracker.should_slow_down() and len(lesson.batch_words) < MAX_LESSON_BATCH:
                return ("extend", None)
            else:
                return ("complete", None)

        return ("continue", None)
