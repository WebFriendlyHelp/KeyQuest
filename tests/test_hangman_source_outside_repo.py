"""The 62 MB Wiktionary extraction lives outside git (Casey's decision, 2026-11-10).

It is only the input to tools/dev/build_hangman_common.py, so it sits in the
git-ignored tools/dev/hangman_source/ folder. When it is missing, the tool must
say which folder it expected and how to fill it, instead of failing obscurely.

These run the tool's main() in-process with its paths pointed at a temp folder.
Nothing is launched.
"""

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "dev" / "hangman_source"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "dev" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestHangmanSourceFolder(unittest.TestCase):
    def test_both_tools_use_the_ignored_source_folder(self):
        common = _load("build_hangman_common")
        dictionary = _load("build_hangman_dictionary")
        self.assertEqual(common.FULL_PATH.parent, SOURCE_DIR)
        self.assertEqual(dictionary.DATA_DIR, SOURCE_DIR)

    def test_the_folder_is_git_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(SOURCE_DIR / "hangman_definitions.json")],
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, "tools/dev/hangman_source/ must be git-ignored")

    def test_the_shipped_list_is_not_ignored(self):
        # Negative twin: only the build input is ignored, never what ships.
        result = subprocess.run(
            ["git", "check-ignore", "-q", "data/wordlists/hangman_common.json"], cwd=ROOT
        )
        self.assertEqual(result.returncode, 1)

    def test_missing_input_names_the_folder_and_the_fix(self):
        common = _load("build_hangman_common")
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "hangman_source" / "hangman_definitions.json"
            err = io.StringIO()
            with mock.patch.object(common, "FULL_PATH", missing), \
                    mock.patch.object(common, "OUT_PATH", Path(tmp) / "out.json"), \
                    contextlib.redirect_stderr(err):
                code = common.main()
        self.assertEqual(code, 1)
        message = err.getvalue()
        self.assertIn(str(missing.parent), message)
        self.assertIn("build_hangman_dictionary.py", message)
        self.assertFalse((Path(tmp) / "out.json").exists())


if __name__ == "__main__":
    unittest.main()
