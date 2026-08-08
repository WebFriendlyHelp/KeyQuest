"""Tests for merging shipped sentence content without discarding user edits.

The requirement, in the owner's words: new content added to the program and
content the user adds or modifies "should be merged regardless of whether it
happens in the portable or the full installer."

The hard case is a file that BOTH sides changed.  Timestamps cannot resolve it
(a user's February edit is older than a March build), so the decision is made by
comparing against what previously shipped.
"""

import unittest
import tempfile
from pathlib import Path

from modules import sentence_merge
from modules.sentence_merge import (
    INCOMING_DIR_NAME,
    SENTENCES_DIR_NAME,
    SHIPPED_DIR_NAME,
    merge_sentences,
)


class _Install:
    """A fake install tree: the user's folder, the baseline, and an incoming set."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sentences = root / SENTENCES_DIR_NAME
        self.shipped = root / SHIPPED_DIR_NAME
        self.incoming = root / INCOMING_DIR_NAME
        for d in (self.sentences, self.shipped, self.incoming):
            d.mkdir(parents=True, exist_ok=True)

    def write(self, where: Path, name: str, text: str) -> None:
        (where / name).write_text(text, encoding="utf-8")

    def read(self, name: str) -> str:
        return (self.sentences / name).read_text(encoding="utf-8")


class TestSentenceMerge(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = _Install(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_new_shipped_file_is_added(self) -> None:
        self.install.write(self.install.incoming, "Astronomy.txt", "stars\n")
        result = merge_sentences(self.install.root)

        self.assertEqual(result.added, ["Astronomy.txt"])
        self.assertEqual(self.install.read("Astronomy.txt"), "stars\n")

    def test_untouched_file_receives_corrections(self) -> None:
        # Same content in the user's folder and the baseline means they never
        # edited it, so a correction should land.
        self.install.write(self.install.sentences, "Geography.txt", "old text\n")
        self.install.write(self.install.shipped, "Geography.txt", "old text\n")
        self.install.write(self.install.incoming, "Geography.txt", "corrected text\n")

        result = merge_sentences(self.install.root)

        self.assertEqual(result.updated, ["Geography.txt"])
        self.assertEqual(self.install.read("Geography.txt"), "corrected text\n")

    def test_user_edited_file_is_never_overwritten(self) -> None:
        # This is the case timestamps get wrong: the user's edit is older than
        # the new build, but it is still their work.
        self.install.write(self.install.sentences, "Geography.txt", "MY OWN VERSION\n")
        self.install.write(self.install.shipped, "Geography.txt", "old text\n")
        self.install.write(self.install.incoming, "Geography.txt", "corrected text\n")

        result = merge_sentences(self.install.root)

        self.assertEqual(result.kept_customized, ["Geography.txt"])
        self.assertEqual(self.install.read("Geography.txt"), "MY OWN VERSION\n")

    def test_user_created_file_is_untouched(self) -> None:
        self.install.write(self.install.sentences, "My Practice.txt", "personal\n")
        self.install.write(self.install.incoming, "Geography.txt", "shipped\n")

        merge_sentences(self.install.root)

        self.assertEqual(self.install.read("My Practice.txt"), "personal\n")

    def test_user_file_colliding_with_a_new_shipped_name_is_kept(self) -> None:
        # They created Astronomy.txt before we ever shipped one. Theirs wins.
        self.install.write(self.install.sentences, "Astronomy.txt", "mine\n")
        self.install.write(self.install.incoming, "Astronomy.txt", "ours\n")

        result = merge_sentences(self.install.root)

        self.assertEqual(result.kept_customized, ["Astronomy.txt"])
        self.assertEqual(self.install.read("Astronomy.txt"), "mine\n")

    def test_line_ending_changes_do_not_count_as_customization(self) -> None:
        # Opening a file in an editor that rewrites CRLF is not an edit.
        (self.install.sentences / "Geography.txt").write_bytes(b"line one\nline two\n")
        (self.install.shipped / "Geography.txt").write_bytes(b"line one\r\nline two\r\n")
        self.install.write(self.install.incoming, "Geography.txt", "corrected\n")

        result = merge_sentences(self.install.root)

        self.assertEqual(result.updated, ["Geography.txt"])

    def test_incoming_becomes_the_next_baseline(self) -> None:
        self.install.write(self.install.sentences, "Geography.txt", "v1\n")
        self.install.write(self.install.shipped, "Geography.txt", "v1\n")
        self.install.write(self.install.incoming, "Geography.txt", "v2\n")

        merge_sentences(self.install.root)

        self.assertFalse(self.install.incoming.exists(), "incoming should be consumed")
        self.assertEqual(
            (self.install.shipped / "Geography.txt").read_text(encoding="utf-8"), "v2\n",
            "the baseline must record what we shipped, so the NEXT update can tell "
            "an untouched file from an edited one",
        )

    def test_second_update_still_respects_a_customization(self) -> None:
        # Regression shape: after one merge, a user's edit must survive the next
        # update too, not just the first.
        self.install.write(self.install.sentences, "Geography.txt", "v1\n")
        self.install.write(self.install.shipped, "Geography.txt", "v1\n")
        self.install.write(self.install.incoming, "Geography.txt", "v2\n")
        merge_sentences(self.install.root)

        (self.install.sentences / "Geography.txt").write_text("user edit\n", encoding="utf-8")
        self.install.incoming.mkdir(parents=True, exist_ok=True)
        self.install.write(self.install.incoming, "Geography.txt", "v3\n")
        result = merge_sentences(self.install.root)

        self.assertEqual(result.kept_customized, ["Geography.txt"])
        self.assertEqual(self.install.read("Geography.txt"), "user edit\n")

    def test_no_incoming_folder_is_a_no_op(self) -> None:
        self.install.write(self.install.sentences, "Geography.txt", "unchanged\n")
        self.install.incoming.rmdir()

        result = merge_sentences(self.install.root)

        self.assertFalse(result.ran)
        self.assertEqual(self.install.read("Geography.txt"), "unchanged\n")

    def test_missing_baseline_is_created_from_the_current_folder(self) -> None:
        # Installs predating this feature have no baseline. Recording the
        # current state is the only honest option: assuming nothing was
        # customized would overwrite pre-existing edits.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("existing\n", encoding="utf-8")

            result = merge_sentences(root)

            self.assertTrue(result.baseline_created)
            self.assertEqual(
                (root / SHIPPED_DIR_NAME / "Geography.txt").read_text(encoding="utf-8"),
                "existing\n",
            )

    def test_first_run_with_an_update_already_staged_keeps_everything(self) -> None:
        """The first merge must not overwrite anything, and here is why.

        On an install predating this feature there is no baseline, so one is
        created from the live folder.  Every file then trivially matches it, and
        a naive comparison concludes nothing was ever customized and replaces
        the lot.  Caught by the integration harness, which staged an update on a
        baseline-less install and watched a user's edit vanish.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text(
                "YEARS OF MY OWN EDITS\n", encoding="utf-8"
            )
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("shipped\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME / "Astronomy.txt").write_text("brand new\n", encoding="utf-8")

            result = merge_sentences(root)

            self.assertEqual(
                (root / SENTENCES_DIR_NAME / "Geography.txt").read_text(encoding="utf-8"),
                "YEARS OF MY OWN EDITS\n",
                "a manufactured baseline must never authorise an overwrite",
            )
            self.assertEqual(result.kept_customized, ["Geography.txt"])
            # A genuinely new file is still safe to add: there is nothing to lose.
            self.assertEqual(result.added, ["Astronomy.txt"])

    def test_merge_never_raises_on_a_broken_tree(self) -> None:
        result = merge_sentences(Path("Z:/definitely/not/here"))
        self.assertFalse(result.ran)


class TestAnnouncement(unittest.TestCase):
    """The spoken summary must be plain and only speak when there is news."""

    def test_silent_when_nothing_happened(self) -> None:
        self.assertEqual(sentence_merge.MergeResult().announcement(), "")

    def test_mentions_each_kind_of_change(self) -> None:
        result = sentence_merge.MergeResult(
            added=["A.txt"], updated=["B.txt", "C.txt"], kept_customized=["D.txt"]
        )
        text = result.announcement()

        self.assertIn("1 new sentence file added", text)
        self.assertIn("2 sentence files updated", text)
        self.assertIn("1 of your customized file was kept unchanged", text)

    def test_announcement_is_speakable_plain_text(self) -> None:
        result = sentence_merge.MergeResult(added=["A.txt"], kept_customized=["B.txt"])
        text = result.announcement()

        self.assertTrue(text.isascii(), "spoken strings must be plain ASCII")
        for symbol in ("*", "->", "|", "#", "_"):
            self.assertNotIn(symbol, text, f"{symbol!r} would be read aloud or skipped")


if __name__ == "__main__":
    unittest.main()
