"""Hangman ships a trimmed, family-friendly word list (Casey's decision, 2026-11-10).

Fable review ui finding 2. The build never copied data/wordlists, so every
installed or portable copy fell back to the 16-word WORD_BANK and repeated
within a session. The full Wiktionary extraction is 62 MB and full of
obscure and inflected entries, so the game now reads a trimmed list built
by tools/dev/build_hangman_common.py from the words in KeyQuest's own
sentence files, and the spec ships it.

The spec checks read the spec text (no build is run here); the real proof is
a built dist with data/wordlists/hangman_common.json in it.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from games import hangman  # noqa: E402

SHIPPED = ROOT / "data" / "wordlists" / "hangman_common.json"
ATTRIBUTION = ROOT / "data" / "wordlists" / "hangman_common_ATTRIBUTION.txt"


def _load():
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


class TestShippedWordList(unittest.TestCase):
    def test_hangman_reads_the_shipped_list(self):
        self.assertEqual(hangman.EXTERNAL_DEFINITIONS_PATH, SHIPPED)

    def test_list_exists_and_is_a_real_size(self):
        data = _load()
        self.assertGreaterEqual(len(data), 1000)
        self.assertLess(SHIPPED.stat().st_size, 1_000_000, "the trimmed list must stay small")

    def test_every_entry_is_playable(self):
        for word, definition in _load().items():
            with self.subTest(word=word):
                self.assertTrue(word.isascii() and word.isalpha() and word == word.lower())
                self.assertGreaterEqual(len(word), hangman.MIN_WORD_LENGTH)
                self.assertTrue(definition.strip())

    def test_no_inflection_or_cross_reference_definitions(self):
        pattern = re.compile(
            r"^(plural of|alternative (form|spelling) of|past tense of|past participle of|"
            r"present participle of|simple past|third-person singular|misspelling of|"
            r"comparative of|superlative of|synonym of|abbreviation of|initialism of|"
            r"obsolete form of)",
            re.IGNORECASE,
        )
        bad = [w for w, d in _load().items() if pattern.match(d.strip())]
        self.assertEqual(bad, [])

    def test_family_friendly(self):
        blocked = re.compile(
            r"\b(sex|sexual|sexually|penis|vagina|genital|genitals|intercourse|erotic|porn|"
            r"pornography|prostitute|prostitution|vulgar|obscene|offensive|derogatory|slur|"
            r"slang|masturbat\w*|rape|cocaine|heroin|drunk|intoxicat\w*)\b",
            re.IGNORECASE,
        )
        bad = [w for w, d in _load().items() if blocked.search(d) or blocked.search(w)]
        self.assertEqual(bad, [])

    def test_attribution_ships_beside_it(self):
        # Definitions come from Wiktionary (CC BY-SA 4.0), which needs
        # attribution and the licence named wherever the data goes.
        text = ATTRIBUTION.read_text(encoding="utf-8")
        self.assertIn("Wiktionary", text)
        self.assertIn("CC BY-SA 4.0", text)

    def test_the_candidate_pool_uses_it(self):
        saved = (hangman._EXTERNAL_DEFINITIONS_CACHE, hangman._CANDIDATE_POOL_CACHE,
                 hangman._CANDIDATE_LENGTH_BUCKETS_CACHE)
        try:
            hangman._EXTERNAL_DEFINITIONS_CACHE = None
            hangman._CANDIDATE_POOL_CACHE = None
            hangman._CANDIDATE_LENGTH_BUCKETS_CACHE = None
            self.assertGreaterEqual(len(hangman.load_candidate_pool()), 1000)
        finally:
            (hangman._EXTERNAL_DEFINITIONS_CACHE, hangman._CANDIDATE_POOL_CACHE,
             hangman._CANDIDATE_LENGTH_BUCKETS_CACHE) = saved


class TestFrozenPath(unittest.TestCase):
    def test_frozen_build_looks_beside_the_exe(self):
        # In a PyInstaller build, games/hangman is imported from the archive
        # and its __file__ points into _internal, so a path built from
        # __file__ looks in _internal/data, where nothing is copied. The spec
        # copies the list to data/wordlists beside KeyQuest.exe.
        import importlib
        from unittest import mock

        fake_exe = str(Path("C:/Apps/KeyQuest/KeyQuest.exe"))
        try:
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", fake_exe):
                reloaded = importlib.reload(hangman)
                path = reloaded.EXTERNAL_DEFINITIONS_PATH
        finally:
            importlib.reload(hangman)
        self.assertEqual(path, Path("C:/Apps/KeyQuest") / "data" / "wordlists" / "hangman_common.json")


class TestBuildShipsIt(unittest.TestCase):
    def setUp(self):
        self.spec = (ROOT / "tools" / "build" / "KeyQuest-RootFolders.spec").read_text(encoding="utf-8")

    def test_spec_copies_the_list_and_attribution(self):
        self.assertIn("hangman_common.json", self.spec)
        self.assertIn("hangman_common_ATTRIBUTION.txt", self.spec)

    def test_spec_refuses_to_build_without_it(self):
        self.assertRegex(self.spec, r"SystemExit\([^)]*hangman_common")

    def test_spec_does_not_ship_the_full_dictionary(self):
        # Negative twin: the 62 MB extraction stays out of the download.
        self.assertNotIn("hangman_definitions.json", self.spec)
        self.assertNotIn("'data'", self.spec.replace(os.sep, "/").split("for folder in")[1].split("]")[0])


if __name__ == "__main__":
    unittest.main()
