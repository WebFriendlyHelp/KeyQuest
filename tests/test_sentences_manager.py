import os
import tempfile
import unittest
from unittest.mock import patch

from modules import sentences_manager
from modules.sentences_manager import (
    _load_sentences_file,
    DEFAULT_SPEED_TEST_SENTENCES,
    _find_topic_file,
    _repair_mojibake_text,
    load_practice_sentences,
    load_speed_test_sentences,
    get_sentence_topics_from_folder,
    normalize_sentence_text,
)


class TestSentencesManager(unittest.TestCase):
    def test_practice_topics_are_nonempty_and_have_explanations(self):
        topics = sentences_manager.get_practice_topics()
        self.assertTrue(topics)
        self.assertIn("English", topics)
        for topic in topics:
            self.assertIsInstance(topic, str)
            self.assertNotEqual(topic, "")
            self.assertNotEqual(sentences_manager.get_practice_topic_explanation(topic), "")

    def test_unknown_topic_falls_back_to_english(self):
        fallback = ["Fallback sentence."]
        sentences = sentences_manager.load_practice_sentences(
            "Not A Real Topic",
            fallback_sentences=fallback,
            app_dir="__definitely_not_a_real_app_dir__",
        )
        self.assertEqual(sentences, fallback)


# ---------------------------------------------------------------------------
# _load_sentences_file – low-level reader
# ---------------------------------------------------------------------------

class TestLoadSentencesFileDirect(unittest.TestCase):
    """Tests for the private _load_sentences_file helper."""

    def test_loads_lines_from_valid_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Hello world.\nKeep going.\n")
            result = _load_sentences_file(path)
        self.assertEqual(result, ["Hello world.", "Keep going."])

    def test_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Line one.\n\n  \nLine two.\n")
            result = _load_sentences_file(path)
        self.assertEqual(result, ["Line one.", "Line two."])

    def test_raises_on_nonexistent_file(self):
        """_load_sentences_file raises an OSError/FileNotFoundError for missing paths."""
        with self.assertRaises(OSError):
            _load_sentences_file("/this/path/does/not/exist/file.txt")

    def test_normalizes_smart_punctuation_and_spacing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write('  “Hello\u00a0world”…  \nIt’s\u00a0fine—really.\n')
            result = _load_sentences_file(path)
        self.assertEqual(result, ['"Hello world"...', "It's fine-really."])

    def test_skips_duplicates_and_junk_only_lines_after_normalization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Hello world!\n")
                f.write("hello   world!!\n")
                f.write("🙂🙂🙂\n")
                f.write("***\n")
                f.write("Keep going.\n")
            result = _load_sentences_file(path)
        self.assertEqual(result, ["Hello world!", "Keep going."])

    def test_rewrites_cleaned_content_back_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("•  Hello  world !!\n")
                f.write("hello world!\n")
                f.write("🙂🙂🙂\n")
                f.write("Keep going.\n")

            result = _load_sentences_file(path)

            with open(path, "r", encoding="utf-8") as f:
                saved = f.read()

        self.assertEqual(result, ["Hello world!", "Keep going."])
        self.assertEqual(saved, "Hello world!\nKeep going.\n")


class TestNormalizeSentenceText(unittest.TestCase):
    def test_repairs_common_mojibake_sequences(self):
        self.assertEqual(
            _repair_mojibake_text("El primer ratÃ³n de computadora."),
            "El primer ratón de computadora.",
        )

    def test_preserves_letters_while_cleaning_formatting_noise(self):
        self.assertEqual(
            normalize_sentence_text("  Café\u00a0“mañana”...  "),
            'Café "mañana"...',
        )

    def test_normalizes_full_width_forms(self):
        self.assertEqual(
            normalize_sentence_text("ＡＢＣ　１２３"),
            "ABC 123",
        )

    def test_removes_invisible_copy_paste_artifacts(self):
        self.assertEqual(
            normalize_sentence_text("\ufeffZero\u200bWidth\u200d text\u00ad"),
            "ZeroWidth text",
        )

    def test_strips_common_leading_bullets_and_numbering(self):
        self.assertEqual(
            normalize_sentence_text("•   Practice this sentence."),
            "Practice this sentence.",
        )
        self.assertEqual(
            normalize_sentence_text("12.   Practice that sentence."),
            "Practice that sentence.",
        )

    def test_removes_emoji_and_fixes_punctuation_spacing(self):
        self.assertEqual(
            normalize_sentence_text("Hi  🙂  there ,  friend !!"),
            "Hi there, friend!",
        )

    def test_normalize_sentence_text_repairs_mojibake(self):
        self.assertEqual(
            normalize_sentence_text("Tu telÃ©fono es mÃ¡s potente."),
            "Tu teléfono es más potente.",
        )

    def test_load_sentences_file_skips_irreparable_mojibake_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Valid sentence.\n")
                f.write("Broken \ufffd line.\n")
            result = _load_sentences_file(path)
        self.assertEqual(result, ["Valid sentence."])


# ---------------------------------------------------------------------------
# load_practice_sentences – file-not-found scenarios
# ---------------------------------------------------------------------------

class TestLoadPracticeSentencesMissingFile(unittest.TestCase):
    """Verify load_practice_sentences() never crashes on missing files."""

    def test_nonexistent_app_dir_returns_fallback(self):
        """Pointing at a completely absent directory returns the fallback list."""
        fallback = ["Fallback A.", "Fallback B."]
        result = load_practice_sentences(
            "English",
            fallback_sentences=fallback,
            app_dir="/no/such/directory/anywhere",
        )
        self.assertEqual(result, fallback)

    def test_empty_sentences_dir_returns_fallback(self):
        """An app_dir that exists but has no Sentences sub-folder returns fallback."""
        fallback = ["Only this."]
        with tempfile.TemporaryDirectory() as tmpdir:
            # tmpdir has no Sentences/ sub-folder
            result = load_practice_sentences(
                "English",
                fallback_sentences=fallback,
                app_dir=tmpdir,
            )
        self.assertEqual(result, fallback)

    def test_missing_language_file_returns_fallback(self):
        """A Sentences/ folder that lacks the requested language file returns fallback."""
        fallback = ["Fallback sentence."]
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            # No English.txt or English Sentences.txt created
            result = load_practice_sentences(
                "English",
                fallback_sentences=fallback,
                app_dir=tmpdir,
            )
        self.assertEqual(result, fallback)

    def test_none_fallback_treated_as_default_sentences(self):
        """Passing None as fallback_sentences should not crash and returns a list."""
        result = load_practice_sentences(
            "English",
            fallback_sentences=None,
            app_dir="/definitely/nonexistent",
        )
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_returns_list_not_none_for_missing_path(self):
        """Return value is always a list, never None, when files are absent."""
        result = load_practice_sentences(
            "Spanish",
            fallback_sentences=["ok"],
            app_dir="/nonexistent/path",
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)

    def test_custom_topic_filename_is_loaded(self):
        """A topic discovered from its filename should load from that same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            custom_path = os.path.join(sentences_dir, "My Spanish Practice.txt")
            with open(custom_path, "w", encoding="utf-8") as f:
                f.write("Hola mundo.\nNecesito practicar.\n")

            result = load_practice_sentences("My Spanish Practice", app_dir=tmpdir)

        self.assertEqual(result, ["Hola mundo.", "Necesito practicar."])

    def test_topic_file_match_is_case_insensitive(self):
        """Topic lookup should still find custom files regardless of case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            custom_path = os.path.join(sentences_dir, "mixed Case Topic.txt")
            with open(custom_path, "w", encoding="utf-8") as f:
                f.write("Sentence one.\nSentence two.\n")

            result = load_practice_sentences("Mixed Case Topic", app_dir=tmpdir)

        self.assertEqual(result, ["Sentence one.", "Sentence two."])


# ---------------------------------------------------------------------------
# load_speed_test_sentences – file-not-found scenario
# ---------------------------------------------------------------------------

class TestLoadSpeedTestSentencesMissingFile(unittest.TestCase):
    def test_missing_speedtest_file_returns_default_pool(self):
        """When SpeedTest.txt is absent the built-in pool is returned."""
        result = load_speed_test_sentences(app_dir="/nonexistent")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        # Should match the built-in defaults
        self.assertEqual(result, list(DEFAULT_SPEED_TEST_SENTENCES))


# ---------------------------------------------------------------------------
# get_sentence_topics_from_folder – file-not-found scenarios
# ---------------------------------------------------------------------------

class TestGetSentenceTopicsFromFolder(unittest.TestCase):
    def test_nonexistent_dir_returns_empty_list(self):
        result = get_sentence_topics_from_folder("/no/such/dir/anywhere")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_empty_sentences_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            result = get_sentence_topics_from_folder(tmpdir)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_txt_files_in_sentences_dir_are_discovered(self):
        """Confirms the happy-path so the missing-file tests have a contrast."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            for name in ("English.txt", "Spanish.txt", "SpeedTest.txt"):
                open(os.path.join(sentences_dir, name), "w").close()
            result = get_sentence_topics_from_folder(tmpdir)
        # SpeedTest is filtered out; English and Spanish are returned sorted
        self.assertIn("English", result)
        self.assertIn("Spanish", result)
        self.assertNotIn("SpeedTest", result)


class TestFindTopicFile(unittest.TestCase):
    def test_prefers_explicit_standard_filename_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentences_dir = os.path.join(tmpdir, "Sentences")
            os.makedirs(sentences_dir)
            preferred = os.path.join(sentences_dir, "English.txt")
            alternate = os.path.join(sentences_dir, "English Sentences.txt")
            open(preferred, "w", encoding="utf-8").close()
            open(alternate, "w", encoding="utf-8").close()

            result = _find_topic_file("English", app_dir=tmpdir)

        self.assertEqual(result, preferred)


# ---------------------------------------------------------------------------
# Hangman word / definition file loading – graceful fallback
# ---------------------------------------------------------------------------

class TestHangmanFileLoadingFallback(unittest.TestCase):
    """Verify hangman loader functions fall back cleanly when data files are absent."""

    def setUp(self):
        # Reset module-level caches so each test gets a fresh load attempt.
        import games.hangman as hangman_mod
        hangman_mod._EXTERNAL_WORDS_CACHE = None
        hangman_mod._EXTERNAL_DEFINITIONS_CACHE = None
        hangman_mod._CANDIDATE_POOL_CACHE = None
        hangman_mod._CANDIDATE_LENGTH_BUCKETS_CACHE = None

    def tearDown(self):
        # Restore caches to None so other tests are not affected.
        import games.hangman as hangman_mod
        hangman_mod._EXTERNAL_WORDS_CACHE = None
        hangman_mod._EXTERNAL_DEFINITIONS_CACHE = None
        hangman_mod._CANDIDATE_POOL_CACHE = None
        hangman_mod._CANDIDATE_LENGTH_BUCKETS_CACHE = None

    def test_load_external_words_returns_empty_list_when_file_missing(self):
        """load_external_words() must return [] not raise when the wordlist is absent."""
        import games.hangman as hangman_mod
        from pathlib import Path
        nonexistent = Path("/no/such/path/hangman_words.txt")
        with patch.object(hangman_mod, "EXTERNAL_WORDLIST_PATH", nonexistent):
            # Also patch definitions so _determine_max_word_length doesn't error
            with patch.object(hangman_mod, "EXTERNAL_DEFINITIONS_PATH", Path("/no/such/path/defs.json")):
                result = hangman_mod.load_external_words()
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_load_external_definitions_returns_empty_dict_when_file_missing(self):
        """load_external_definitions() must return {} not raise when the file is absent."""
        import games.hangman as hangman_mod
        from pathlib import Path
        nonexistent = Path("/no/such/path/hangman_definitions.json")
        with patch.object(hangman_mod, "EXTERNAL_DEFINITIONS_PATH", nonexistent):
            result = hangman_mod.load_external_definitions()
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_load_candidate_pool_falls_back_to_word_bank_when_files_missing(self):
        """When both external files are absent the curated WORD_BANK is the pool."""
        import games.hangman as hangman_mod
        from pathlib import Path
        nonexistent_words = Path("/no/such/path/hangman_words.txt")
        nonexistent_defs = Path("/no/such/path/hangman_definitions.json")
        with patch.object(hangman_mod, "EXTERNAL_WORDLIST_PATH", nonexistent_words):
            with patch.object(hangman_mod, "EXTERNAL_DEFINITIONS_PATH", nonexistent_defs):
                pool = hangman_mod.load_candidate_pool()
        self.assertIsInstance(pool, list)
        self.assertTrue(len(pool) > 0, "Pool should contain WORD_BANK entries as fallback")
        # Every candidate must be a (word, definition) tuple
        for word, defn in pool:
            self.assertIsInstance(word, str)
            self.assertIsInstance(defn, str)
            self.assertTrue(len(word) >= 5)
            self.assertTrue(len(defn) > 0)

    def test_load_external_definitions_handles_corrupt_json(self):
        """A definitions file with invalid JSON must return {} without raising."""
        import games.hangman as hangman_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_json = os.path.join(tmpdir, "hangman_definitions.json")
            with open(bad_json, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            from pathlib import Path
            with patch.object(hangman_mod, "EXTERNAL_DEFINITIONS_PATH", Path(bad_json)):
                result = hangman_mod.load_external_definitions()
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_load_external_definitions_handles_non_dict_json(self):
        """A definitions file containing a JSON array instead of object returns {}."""
        import games.hangman as hangman_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            array_json = os.path.join(tmpdir, "hangman_definitions.json")
            with open(array_json, "w", encoding="utf-8") as f:
                f.write('["word1", "word2"]')
            from pathlib import Path
            with patch.object(hangman_mod, "EXTERNAL_DEFINITIONS_PATH", Path(array_json)):
                result = hangman_mod.load_external_definitions()
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
