"""Emoji are stripped from speech and kept out of dialog text; real scripts are not.

Fable review 2026-11-10, modules finding 11.
(a) The stopwatch U+23F1 used for the weekend challenge was below every range
    in _EMOJI_RE and was spoken.
(b) Quest and challenge text reaches wx dialogs, which the screen reader reads
    through UI Automation without passing Speech.say, so their emoji were read
    out; CLAUDE.md asks for plain text in visual dialogs too.
(c) The catch-all range U+24C2 to U+1F251 also removed all CJK, kana, Hangul,
    fullwidth forms and ligatures, so a user sentence in those scripts was
    dropped as "empty-after-emoji-strip".
"""

import unicodedata
import unittest

from modules import challenge_manager, quest_manager
from modules.speech_manager import _EMOJI_RE
from modules.state_manager import Settings


def _has_pictograph(text):
    return any(unicodedata.category(ch) == "So" and ord(ch) > 0x2000 for ch in text)


class TestEmojiRegex(unittest.TestCase):
    def test_the_stopwatch_is_stripped(self):
        self.assertEqual(_EMOJI_RE.sub("", "⏱️ Five minute test").strip(), "Five minute test")

    def test_common_emoji_are_still_stripped(self):
        """Negative twin: the ranges that worked must keep working."""
        for emoji in ("\U0001F600", "\U0001F680", "✅", "⚡", "⭐", "\U0001F3C6", "\U0001F4DC"):
            self.assertEqual(_EMOJI_RE.sub("", f"a{emoji}b"), "ab", hex(ord(emoji)))

    def test_real_scripts_survive(self):
        for text in ("日本語", "한국어", "中文", "ひらがな", "カタカナ", "ＡＢＣ", "ﬁne"):
            self.assertEqual(_EMOJI_RE.sub("", text), text, text)


class TestDialogTextIsPlain(unittest.TestCase):
    def test_quest_list_has_no_emoji(self):
        settings = Settings()
        quest_manager.initialize_quests(settings)
        settings.completed_quests.add("speed_demon")
        self.assertFalse(_has_pictograph(quest_manager.format_quest_list(settings, show_inactive=True)))

    def test_quest_completion_has_no_emoji(self):
        self.assertFalse(_has_pictograph(quest_manager.format_quest_completion("speed_demon")))

    def test_challenge_text_has_no_emoji(self):
        settings = Settings()
        for completed in (False, True):
            settings.daily_challenge_completed = completed
            settings.daily_challenge_date = challenge_manager.get_today_date_string()
            text = challenge_manager.format_challenge_announcement(settings)
            self.assertFalse(_has_pictograph(text), text)


if __name__ == "__main__":
    unittest.main()
