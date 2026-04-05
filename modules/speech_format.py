"""Helpers for speech-friendly text announcements."""

from __future__ import annotations


SPECIAL_CHAR_NAMES = {
    " ": "space",
    "\t": "tab",
    "\n": "new line",
    ";": "semicolon",
    ",": "comma",
    ".": "period",
    "'": "apostrophe",
    "/": "slash",
    "-": "dash",
    ":": "colon",
    "!": "exclamation mark",
    "?": "question mark",
}


def to_speakable_token(ch: str) -> str:
    """Convert one character to a speech-friendly token."""
    if ch in SPECIAL_CHAR_NAMES:
        return SPECIAL_CHAR_NAMES[ch]
    if ch.isalpha() and ch.isupper():
        return f"capital {ch.lower()}"
    return ch.lower()


def to_typing_instruction_token(ch: str) -> str:
    """Convert one character to a lesson-prompt token without speaking capitalization."""
    if ch in SPECIAL_CHAR_NAMES:
        return SPECIAL_CHAR_NAMES[ch]
    return ch.lower()


def spell_text(text: str) -> str:
    """Spell text character-by-character with separators for SR clarity."""
    if not text:
        return "nothing"
    return ", ".join(to_speakable_token(ch) for ch in text)


def _format_repeated_token(text: str) -> str | None:
    """Return a compact repeated-token phrase when the full text is the same token."""
    if not text:
        return None

    normalized = text.lower()
    if len(set(normalized)) != 1 or len(normalized) < 2:
        return None

    token = to_typing_instruction_token(text[0])
    if len(text) == 2:
        return f"{token} twice"
    return f"{token} {len(text)} times"


def _is_known_natural_word(text: str, natural_words: set[str] | None) -> bool:
    """Return True when a lesson prompt should be spoken naturally.

    A single token matches if it is in natural_words.
    A multi-word phrase matches if every space-separated token is in natural_words.
    """
    if not natural_words or not text:
        return False

    lowered = text.lower()
    if text != lowered:
        return False

    if " " not in lowered:
        return lowered in natural_words

    return all(token in natural_words for token in lowered.split(" ") if token)


def _spell_sequence_with_repeat_pauses(text: str) -> str:
    """Spell a sequence with comma pauses between tokens."""
    return ", ".join(to_typing_instruction_token(ch) for ch in text)


def spell_text_for_typing_instruction(text: str, natural_words: set[str] | None = None) -> str:
    """Format text for `Type ...` prompts."""
    if not text:
        return "nothing"

    repeated = _format_repeated_token(text)
    if repeated:
        return repeated

    if _is_known_natural_word(text, natural_words):
        return text.lower()

    return _spell_sequence_with_repeat_pauses(text)


def build_remaining_text_feedback(remaining: str) -> str:
    """Build consistent mismatch/remaining feedback."""
    if not remaining:
        return "Nothing remaining."

    parts = remaining.split(" ", 1)
    first_word = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    spelled_first_word = spell_text(first_word)

    if rest:
        return f"Type: {spelled_first_word}. Then: {rest}"
    return f"Type: {spelled_first_word}."
