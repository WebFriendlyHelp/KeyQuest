import json
import tempfile
import unittest
from pathlib import Path

from modules import sentences_manager


class TestSentenceManifest(unittest.TestCase):
    def test_get_practice_topics_uses_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = Path(tmpdir) / "Sentences"
            sentences_dir.mkdir()
            (sentences_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "speed_test_file": "SpeedTest.txt",
                        "topics": [
                            {
                                "name": "Custom Topic",
                                "file": "custom.txt",
                                "display_name": "Custom Display",
                                "explanation": "Custom explanation.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (sentences_dir / "custom.txt").write_text("Example line.\n", encoding="utf-8")

            self.assertEqual(sentences_manager.get_practice_topics(app_dir=tmpdir), ["Custom Topic"])
            self.assertEqual(
                sentences_manager.get_practice_topic_display_name("Custom Topic", app_dir=tmpdir),
                "Custom Display",
            )
            self.assertEqual(
                sentences_manager.get_practice_topic_explanation("Custom Topic", app_dir=tmpdir),
                "Custom explanation.",
            )

    def test_folder_topics_include_loose_text_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = Path(tmpdir) / "Sentences"
            sentences_dir.mkdir()
            (sentences_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "speed_test_file": "SpeedTest.txt",
                        "topics": [],
                    }
                ),
                encoding="utf-8",
            )
            (sentences_dir / "Bonus Topic.txt").write_text("Bonus line.\n", encoding="utf-8")

            topics = sentences_manager.get_sentence_topics_from_folder(app_dir=tmpdir)
            self.assertIn("Bonus Topic", topics)

    def test_invalid_manifest_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = Path(tmpdir) / "Sentences"
            sentences_dir.mkdir()
            (sentences_dir / "manifest.json").write_text("{not json", encoding="utf-8")
            (sentences_dir / "English Sentences.txt").write_text("Example line.\n", encoding="utf-8")

            self.assertIn("English", sentences_manager.get_practice_topics(app_dir=tmpdir))

    def test_missing_manifest_infers_topic_metadata_from_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = Path(tmpdir) / "Sentences"
            sentences_dir.mkdir()
            (sentences_dir / "English Sentences.txt").write_text("Example line.\n", encoding="utf-8")
            (sentences_dir / "Science Facts.txt").write_text("Fact line.\n", encoding="utf-8")

            self.assertEqual(
                sentences_manager.get_practice_topics(app_dir=tmpdir),
                ["English", "Science Facts"],
            )
            self.assertEqual(
                sentences_manager.get_practice_topic_display_name("English", app_dir=tmpdir),
                "General",
            )
            self.assertEqual(
                sentences_manager.get_practice_topic_display_name("Science Facts", app_dir=tmpdir),
                "Science Facts",
            )
            self.assertEqual(
                sentences_manager.get_practice_topic_explanation("English", app_dir=tmpdir),
                "",
            )

    def test_adding_and_editing_text_files_still_works_without_manifest_updates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = Path(tmpdir) / "Sentences"
            sentences_dir.mkdir()

            custom_topic = sentences_dir / "My Topic.txt"
            custom_topic.write_text("First sentence.\n", encoding="utf-8")

            topics = sentences_manager.get_sentence_topics_from_folder(app_dir=tmpdir)
            self.assertIn("My Topic", topics)
            self.assertEqual(
                sentences_manager.load_practice_sentences(
                    "My Topic",
                    fallback_sentences=["Fallback."],
                    app_dir=tmpdir,
                ),
                ["First sentence."],
            )

            custom_topic.write_text("Updated sentence.\nSecond one.\n", encoding="utf-8")
            self.assertEqual(
                sentences_manager.load_practice_sentences(
                    "My Topic",
                    fallback_sentences=["Fallback."],
                    app_dir=tmpdir,
                ),
                ["Updated sentence.", "Second one."],
            )


if __name__ == "__main__":
    unittest.main()
