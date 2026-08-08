"""A deleted sentence file must not still be offered in the menus.

Owner's requirement: "if a user deletes vocab for example it shouldn't then
appear in menus." The topic list is the union of the manifest's topics and a
scan of the folder, so a manifest entry alone was enough to keep advertising a
topic whose file the user had removed. Choosing it then leads to an empty
session, and it quietly overrides a deliberate choice.
"""

import json
import tempfile
import unittest
from pathlib import Path

from modules import sentences_manager


class TestTopicListRespectsDeletedFiles(unittest.TestCase):
    def _make_install(self, root: Path, files: dict, manifest_topics: list) -> None:
        sentences = root / "Sentences"
        sentences.mkdir(parents=True)
        for name, text in files.items():
            (sentences / name).write_text(text, encoding="utf-8")
        (sentences / "manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "speed_test_file": "SpeedTest.txt",
                    "topics": manifest_topics,
                }
            ),
            encoding="utf-8",
        )

    def test_a_topic_whose_file_was_deleted_is_not_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_install(
                root,
                files={"Geography.txt": "a\n"},  # Vocabulary Building.txt deleted
                manifest_topics=[
                    {"name": "Geography", "file": "Geography.txt"},
                    {"name": "Vocabulary Building", "file": "Vocabulary Building.txt"},
                ],
            )

            topics = sentences_manager.get_sentence_topics_from_folder(str(root))

            self.assertIn("Geography", topics)
            self.assertNotIn(
                "Vocabulary Building", topics,
                "the manifest still lists it, but the user deleted the file; offering it "
                "leads to an empty session",
            )

    def test_a_present_topic_is_still_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_install(
                root,
                files={"Geography.txt": "a\n", "Vocabulary Building.txt": "b\n"},
                manifest_topics=[
                    {"name": "Geography", "file": "Geography.txt"},
                    {"name": "Vocabulary Building", "file": "Vocabulary Building.txt"},
                ],
            )

            topics = sentences_manager.get_sentence_topics_from_folder(str(root))

            self.assertIn("Vocabulary Building", topics)

    def test_a_user_created_file_still_appears(self) -> None:
        # Not in the manifest at all; the folder scan must still find it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_install(
                root,
                files={"Geography.txt": "a\n", "My Own Topic.txt": "mine\n"},
                manifest_topics=[{"name": "Geography", "file": "Geography.txt"}],
            )

            topics = sentences_manager.get_sentence_topics_from_folder(str(root))

            self.assertIn("My Own Topic", topics)


if __name__ == "__main__":
    unittest.main()
