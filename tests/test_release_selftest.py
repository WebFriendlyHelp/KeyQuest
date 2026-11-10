"""KeyQuest.exe --selftest proves the bundle can load the app.

Fable review ui finding 9. The release smoke test ran KeyQuest.exe --version,
which exits before the app is imported, so it proved only that
modules.version imports and would stay green on a bundle missing wx,
pygame, the Tolk DLLs, or the data files (as Hangman's word list was).

What these prove: the self-test imports the app and loads Tolk from source
and fails on a missing data file. The frozen proof is release.yml running it
against the built exe, which needs a release build (not run here).
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestSelfTest(unittest.TestCase):
    def test_passes_from_the_source_tree(self):
        from modules import selftest

        self.assertEqual(selftest.run(ROOT, load_tolk=False), 0)

    def test_fails_when_a_shipped_data_file_is_missing(self):
        # Negative twin: an app folder without the data files must fail.
        from modules import selftest

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(selftest.run(Path(tmp), load_tolk=False), 1)

    def test_entry_point_handles_the_flag_before_starting_the_app(self):
        # Read, not run: spawning keyquest.pyw starts the full app (with speech
        # through the screen reader) whenever the flag is not handled, which is
        # exactly what happened when this was first written as a subprocess
        # test. The check is that the flag exits before main is imported.
        source = (ROOT / "keyquest.pyw").read_text(encoding="utf-8")
        flag = source.index('"--selftest" in sys.argv')
        self.assertLess(flag, source.index("from modules.keyquest_app import main"))
        self.assertIn("sys.exit(selftest.run(", source[flag:flag + 300])

    def test_release_workflow_smoke_tests_with_it(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn('"--selftest"', workflow)


if __name__ == "__main__":
    unittest.main()
