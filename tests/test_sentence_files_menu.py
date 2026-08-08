"""The destructive sentence action lives behind a submenu, not on the main menu.

The main menu is long, and arrowing through it is how a screen reader user
reaches everything. "Restore Default Sentences" replaces every sentence file, so
it should not sit on the path someone traverses daily. It was briefly there;
this pins the fix.

The Options menu was considered and rejected: that menu cycles values with
left/right arrows ("Speech: auto", "Visual Theme: dark"), so a one-shot
destructive action does not belong in it.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _main_menu_items() -> list:
    src = Path(__file__).resolve().parents[1] / "modules" / "state_manager.py"
    line = next(
        text for text in src.read_text(encoding="utf-8").splitlines()
        if "menu_items" in text and "Tutorial" in text
    )
    return re.findall(r'"([^"]+)"', line)


class TestSentenceFilesMenu(unittest.TestCase):
    def test_restore_is_not_on_the_main_menu(self) -> None:
        items = _main_menu_items()
        self.assertFalse(
            [i for i in items if "Restore Default" in i],
            "a destructive action must not sit on the menu people arrow through daily",
        )

    def test_a_sentence_files_entry_exists_instead(self) -> None:
        items = _main_menu_items()
        self.assertTrue([i for i in items if i.startswith("Sentence Files")])

    def test_the_entry_is_distinguishable_from_sentence_practice(self) -> None:
        # Both are announced aloud, so near-identical names would be confusing.
        items = _main_menu_items()
        labels = [i.rsplit(":", 1)[0].strip() for i in items]
        self.assertIn("Sentence Practice", labels)
        self.assertIn("Sentence Files", labels)
        self.assertNotIn("Sentences", labels, "too close to 'Sentence Practice' when heard")

    def test_the_submenu_offers_both_actions(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "modules" / "keyquest_app.py").read_text(
            encoding="utf-8"
        )
        block = src.split("self.sentence_files_items = [", 1)[1].split("]", 1)[0]
        self.assertIn("Open Sentences Folder", block)
        self.assertIn("Restore Default Sentences", block)

    def test_restore_is_not_in_the_value_cycling_options_menu(self) -> None:
        # get_options_items builds "Label: Value" entries that cycle on
        # left/right. A destructive action there could be triggered while
        # someone is simply moving through their settings.
        src = (Path(__file__).resolve().parents[1] / "modules" / "menu_handler.py").read_text(
            encoding="utf-8"
        )
        options_fn = src.split("def get_options_items(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("Restore", options_fn)


if __name__ == "__main__":
    unittest.main()
