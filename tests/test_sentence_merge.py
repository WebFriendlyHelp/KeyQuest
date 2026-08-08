"""Tests for merging shipped sentence content without discarding user edits.

The requirement, in the owner's words: new content added to the program and
content the user adds or modifies "should be merged regardless of whether it
happens in the portable or the full installer."

The hard case is a file that BOTH sides changed.  Timestamps cannot resolve it
(a user's February edit is older than a March build), so the decision is made by
comparing against what previously shipped.
"""

import hashlib
import json
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import sentence_merge
from modules.sentence_merge import (
    INCOMING_DIR_NAME,
    SENTENCES_DIR_NAME,
    merge_sentences,
)


class _Install:
    """A fake install tree: the user's folder, the baseline, and an incoming set."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sentences = root / SENTENCES_DIR_NAME
        self.incoming = root / INCOMING_DIR_NAME
        for d in (self.sentences, self.incoming):
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



    def test_no_incoming_folder_is_a_no_op(self) -> None:
        self.install.write(self.install.sentences, "Geography.txt", "unchanged\n")
        self.install.incoming.rmdir()

        result = merge_sentences(self.install.root)

        self.assertFalse(result.ran)
        self.assertEqual(self.install.read("Geography.txt"), "unchanged\n")





    def test_merge_never_raises_on_a_broken_tree(self) -> None:
        result = merge_sentences(Path("Z:/definitely/not/here"))
        self.assertFalse(result.ran)


class TestShippedHistory(unittest.TestCase):
    """Matching ANY version we ever shipped is what unfreezes the hard cases.

    Comparing against only the previous release cannot tell an untouched file
    from an edited one after a transition (no record existed, so everything was
    conservatively kept, and the baseline then moved on without it) or after a
    one-time failure (a file skipped once, baseline advanced past it). Both left
    that file frozen as "customized" forever, never corrected again.
    """

    def _write_history(self, root: Path, mapping: dict) -> None:
        (root / sentence_merge.HISTORY_FILE_NAME).write_text(
            json.dumps(mapping), encoding="utf-8"
        )

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()

    def test_transition_freeze_is_gone(self) -> None:
        # The user is on an old release with an untouched file, has no baseline
        # at all, and an update is staged. Its content matches a version we
        # shipped, so it is not theirs, and the correction must land.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("v1\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("v3\n", encoding="utf-8")
            self._write_history(root, {"Geography.txt": [self._hash("v1\n"), self._hash("v2\n")]})

            result = merge_sentences(root)

            self.assertEqual(result.updated, ["Geography.txt"])
            self.assertEqual(
                (root / SENTENCES_DIR_NAME / "Geography.txt").read_text(encoding="utf-8"), "v3\n"
            )

    def test_a_real_edit_is_still_kept_even_with_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("MY EDIT\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("v3\n", encoding="utf-8")
            self._write_history(root, {"Geography.txt": [self._hash("v1\n"), self._hash("v2\n")]})

            result = merge_sentences(root)

            self.assertEqual(result.kept_customized, ["Geography.txt"])
            self.assertEqual(
                (root / SENTENCES_DIR_NAME / "Geography.txt").read_text(encoding="utf-8"), "MY EDIT\n"
            )

    def test_a_file_left_behind_by_an_earlier_update_still_catches_up(self) -> None:
        # The user is two releases behind on this one file (an earlier update
        # skipped it, or they never restarted). Its content still matches a
        # version we shipped, so the newest correction lands rather than the
        # file being frozen as "customized" forever.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("v1\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("v3\n", encoding="utf-8")
            self._write_history(root, {"Geography.txt": [self._hash("v1\n"), self._hash("v2\n")]})

            result = merge_sentences(root)

            self.assertEqual(result.updated, ["Geography.txt"])

    def test_the_obsolete_baseline_folder_is_removed(self) -> None:
        # An earlier design kept a duplicate of every sentence file here. It is
        # unnecessary now, and it should not be left sitting in the app folder.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            stale = root / "_sentences_shipped"
            stale.mkdir()
            (stale / "Geography.txt").write_text("old duplicate\n", encoding="utf-8")

            merge_sentences(root)

            self.assertFalse(stale.exists(), "the obsolete duplicate folder should be cleaned up")

    def test_line_endings_do_not_defeat_history_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_bytes(b"a\r\nb\r\n")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("new\n", encoding="utf-8")
            self._write_history(root, {"Geography.txt": [self._hash("a\nb\n")]})

            self.assertEqual(merge_sentences(root).updated, ["Geography.txt"])

    def test_missing_history_falls_back_to_conservative_behaviour(self) -> None:
        # A release that forgot to generate the file must not become a licence
        # to overwrite; it drops back to the baseline comparison.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("mine\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Geography.txt").write_text("shipped\n", encoding="utf-8")

            result = merge_sentences(root)

            self.assertEqual(result.kept_customized, ["Geography.txt"])

    def test_the_shipped_history_file_matches_the_real_sentences_folder(self) -> None:
        # Guards the release step: if sentence content changed and
        # tools/dev/build_sentence_hashes.py was not re-run, every user's copy
        # looks edited and stops receiving corrections.
        repo = Path(__file__).resolve().parents[1]
        history = sentence_merge.load_shipped_history(repo)
        self.assertTrue(history, "sentence_history.json is missing from the repo root")
        missing = [
            path.name
            for path in sorted((repo / SENTENCES_DIR_NAME).iterdir())
            if path.is_file() and sentence_merge.content_hash(path) not in history.get(path.name, set())
        ]
        self.assertEqual(
            missing, [],
            "these sentence files are not recorded in sentence_history.json; "
            "run: py -3.11 tools/dev/build_sentence_hashes.py",
        )


class TestAnnouncement(unittest.TestCase):
    """The spoken summary must be plain and only speak when there is news."""

    def test_silent_when_nothing_happened(self) -> None:
        self.assertEqual(sentence_merge.MergeResult().announcement(), "")

    def test_kept_only_result_does_not_claim_content_changed(self) -> None:
        # Nothing was added or updated, so "Sentence content updated" would be
        # false, and the user cannot look at the folder to check.
        result = sentence_merge.MergeResult(kept_customized=["A.txt"])
        text = result.announcement()

        self.assertNotIn("updated", text)
        self.assertIn("checked", text)
        self.assertIn("left unchanged", text)

    def test_mentions_each_kind_of_change(self) -> None:
        result = sentence_merge.MergeResult(
            added=["A.txt"], updated=["B.txt", "C.txt"], kept_customized=["D.txt"]
        )
        text = result.announcement()

        self.assertIn("1 new sentence file added", text)
        self.assertIn("2 sentence files updated", text)
        self.assertIn("1 of your own sentence file was left unchanged", text)

    def test_announcement_is_speakable_plain_text(self) -> None:
        result = sentence_merge.MergeResult(added=["A.txt"], kept_customized=["B.txt"])
        text = result.announcement()

        self.assertTrue(text.isascii(), "spoken strings must be plain ASCII")
        for symbol in ("*", "->", "|", "#", "_"):
            self.assertNotIn(symbol, text, f"{symbol!r} would be read aloud or skipped")




class TestDeletionsAreRespected(unittest.TestCase):
    """Deleting a sentence file is a choice, not an accident.

    Owner's decision: "deleting counts as modifying, and if a user deletes vocab
    for example it shouldn't then appear in menus." Re-adding a file on the next
    update silently overrides that, and the topic reappears in the menus with it.
    """

    def _install(self, tmp: Path) -> Path:
        (tmp / SENTENCES_DIR_NAME).mkdir()
        defaults = tmp / "defaults" / "Sentences"
        defaults.mkdir(parents=True)
        return defaults

    def test_a_deleted_file_is_not_brought_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = self._install(root)
            (defaults / "Vocabulary Building.txt").write_text("shipped\n", encoding="utf-8")
            (root / SENTENCES_DIR_NAME / "Vocabulary Building.txt").write_text(
                "shipped\n", encoding="utf-8"
            )

            # The install has the file, so we learn it was once present.
            sentence_merge.update_deletion_record(root)
            # The user deletes it.
            (root / SENTENCES_DIR_NAME / "Vocabulary Building.txt").unlink()

            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Vocabulary Building.txt").write_text(
                "shipped\n", encoding="utf-8"
            )
            result = merge_sentences(root)

            self.assertFalse(
                (root / SENTENCES_DIR_NAME / "Vocabulary Building.txt").exists(),
                "a deliberately deleted file must stay deleted",
            )
            self.assertEqual(result.respected_deletions, ["Vocabulary Building.txt"])
            self.assertEqual(result.added, [])

    def test_a_file_that_never_arrived_is_not_mistaken_for_a_deletion(self) -> None:
        # Never seen on this install, so its absence means "new", not "removed".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = self._install(root)
            (defaults / "Astronomy.txt").write_text("new topic\n", encoding="utf-8")
            (root / INCOMING_DIR_NAME).mkdir()
            (root / INCOMING_DIR_NAME / "Astronomy.txt").write_text("new topic\n", encoding="utf-8")

            result = merge_sentences(root)

            self.assertEqual(result.added, ["Astronomy.txt"])

    def test_putting_the_file_back_clears_the_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = self._install(root)
            (defaults / "Geography.txt").write_text("shipped\n", encoding="utf-8")
            live = root / SENTENCES_DIR_NAME / "Geography.txt"
            live.write_text("shipped\n", encoding="utf-8")
            sentence_merge.update_deletion_record(root)
            live.unlink()
            self.assertIn("geography.txt", sentence_merge.update_deletion_record(root))

            live.write_text("I want it back\n", encoding="utf-8")
            self.assertNotIn("geography.txt", sentence_merge.update_deletion_record(root))


class TestRestoreDefaults(unittest.TestCase):
    def test_restores_shipped_files_and_clears_deletions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            defaults = root / "defaults" / "Sentences"
            defaults.mkdir(parents=True)
            (defaults / "Geography.txt").write_text("original\n", encoding="utf-8")
            (root / SENTENCES_DIR_NAME / "Geography.txt").write_text("edited\n", encoding="utf-8")
            (root / SENTENCES_DIR_NAME / "My Own.txt").write_text("mine\n", encoding="utf-8")

            restored, failed = sentence_merge.restore_default_sentences(root)

            self.assertEqual(restored, ["Geography.txt"])
            self.assertEqual(failed, [])
            self.assertEqual(
                (root / SENTENCES_DIR_NAME / "Geography.txt").read_text(encoding="utf-8"),
                "original\n",
            )
            self.assertEqual(
                (root / SENTENCES_DIR_NAME / "My Own.txt").read_text(encoding="utf-8"), "mine\n",
                "a file the user created is not a shipped file and must not be touched",
            )

    def test_restore_undoes_a_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            defaults = root / "defaults" / "Sentences"
            defaults.mkdir(parents=True)
            (defaults / "Geography.txt").write_text("original\n", encoding="utf-8")
            sentence_merge._save_prefs(root, {"seen": ["Geography.txt"], "deleted": ["Geography.txt"]})

            sentence_merge.restore_default_sentences(root)

            self.assertTrue((root / SENTENCES_DIR_NAME / "Geography.txt").exists())
            self.assertEqual(
                sentence_merge._load_prefs(root).get("deleted"), [],
                "restoring is an explicit request for the defaults, so it clears the record",
            )


class TestMergeIsIdempotent(unittest.TestCase):
    """Running with nothing to do must do nothing, and say nothing.

    The defaults fallback means there is always a source to merge from, so
    without a content check the merge rewrote every unedited file on EVERY
    startup and announced "13 sentence files updated" each time. Found by
    running the built app; no test had caught it.
    """

    def test_a_file_already_matching_is_not_rewritten_or_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            defaults = root / "defaults" / "Sentences"
            defaults.mkdir(parents=True)
            (defaults / "Geography.txt").write_text("same\n", encoding="utf-8")
            live = root / SENTENCES_DIR_NAME / "Geography.txt"
            live.write_text("same\n", encoding="utf-8")
            before = live.stat().st_mtime_ns

            result = merge_sentences(root)

            self.assertEqual(result.updated, [], "nothing changed, so nothing was updated")
            self.assertEqual(result.added, [])
            self.assertEqual(result.announcement(), "", "silence is correct when nothing happened")
            self.assertEqual(live.stat().st_mtime_ns, before, "the file should not be rewritten")

    def test_repeated_runs_stay_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SENTENCES_DIR_NAME).mkdir()
            defaults = root / "defaults" / "Sentences"
            defaults.mkdir(parents=True)
            (defaults / "Geography.txt").write_text("v1\n", encoding="utf-8")

            first = merge_sentences(root)
            self.assertEqual(first.added, ["Geography.txt"])

            for _ in range(3):
                again = merge_sentences(root)
                self.assertEqual(again.added, [])
                self.assertEqual(again.updated, [])
                self.assertEqual(again.announcement(), "")

class TestWholesaleLossIsNotADecision(unittest.TestCase):
    """Losing the whole folder is an accident; deleting one file is a choice."""

    def _seed(self, root: Path, names: list) -> None:
        (root / SENTENCES_DIR_NAME).mkdir()
        defaults = root / "defaults" / "Sentences"
        defaults.mkdir(parents=True)
        for n in names:
            (defaults / n).write_text("shipped\n", encoding="utf-8")
            (root / SENTENCES_DIR_NAME / n).write_text("shipped\n", encoding="utf-8")

    def test_deleting_the_whole_folder_restores_it_and_says_so(self) -> None:
        # Deleting the folder is a plausible attempt at exactly the reset this
        # feature offers. Recording it as thirteen deliberate deletions left an
        # empty topic menu, permanently, with nothing spoken to explain it.
        import shutil as _shutil

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root, ["Geography.txt", "Vocabulary Building.txt", "Science Facts.txt"])
            sentence_merge.update_deletion_record(root)
            _shutil.rmtree(root / SENTENCES_DIR_NAME)

            result = merge_sentences(root)

            self.assertEqual(len(result.added), 3, "the defaults should come back")
            self.assertEqual(result.respected_deletions, [])
            self.assertTrue(result.recovered_missing_folder)
            self.assertIn("were missing", result.announcement())
            self.assertEqual(
                sentence_merge._load_prefs(root).get("deleted", []), [],
                "an accident must not be recorded as a decision",
            )

    def test_deleting_one_file_of_many_is_still_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root, ["Geography.txt", "Vocabulary Building.txt", "Science Facts.txt"])
            sentence_merge.update_deletion_record(root)
            (root / SENTENCES_DIR_NAME / "Vocabulary Building.txt").unlink()

            result = merge_sentences(root)

            self.assertEqual(result.respected_deletions, ["Vocabulary Building.txt"])
            self.assertFalse((root / SENTENCES_DIR_NAME / "Vocabulary Building.txt").exists())

    def test_a_case_only_rename_clears_the_deletion(self) -> None:
        # Windows is case-insensitive, so Animals.txt and animals.txt are the
        # same file. A case-sensitive record would never notice it came back.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root, ["Animals.txt", "Geography.txt"])
            sentence_merge.update_deletion_record(root)
            (root / SENTENCES_DIR_NAME / "Animals.txt").unlink()
            self.assertIn("animals.txt", sentence_merge.update_deletion_record(root))

            (root / SENTENCES_DIR_NAME / "animals.txt").write_text("back\n", encoding="utf-8")

            self.assertNotIn("animals.txt", sentence_merge.update_deletion_record(root))



if __name__ == "__main__":
    unittest.main()
