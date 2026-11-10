"""release_bump --apply refuses a release with no new What's New entry.

Fable review ui finding 8. release.ps1's "Require plain-language What's New
update" step passes when docs/user/WHATS_NEW.md is modified, and
release_bump --apply (run by ship_updates.ps1 first) rewrites the top
"Version X" line itself, so that edit alone satisfied the gate. A release
with no new entry went out with the previous notes relabelled.

What these prove: the pure comparison, and that main() runs it before
anything is written. They do not run ship_updates.ps1 (a release script).
"""

import importlib.util
import inspect
import pathlib
import unittest

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev" / "release_bump.py"
SPEC = importlib.util.spec_from_file_location("release_bump_gate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

HEAD = """# New in Key Quest

## Saturday August 15th 2026

Version 1.27.2

- Fixed: something.
"""


class TestWhatsNewGate(unittest.TestCase):
    def test_unchanged_file_is_refused(self):
        with self.assertRaises(SystemExit):
            MODULE.require_new_whats_new_entry(HEAD, HEAD)

    def test_only_the_version_line_changed_is_refused(self):
        relabelled = HEAD.replace("Version 1.27.2", "Version 1.27.3")
        with self.assertRaises(SystemExit):
            MODULE.require_new_whats_new_entry(HEAD, relabelled)

    def test_a_new_entry_passes(self):
        # Negative twin: a real new entry is accepted, whatever version number
        # the author put on it (the bump rewrites it anyway).
        new = HEAD.replace(
            "## Saturday August 15th 2026",
            "## Tuesday November 10th 2026\n\nVersion 1.27.2\n\n- Fixed: Hangman words.\n\n"
            "## Saturday August 15th 2026",
            1,
        )
        MODULE.require_new_whats_new_entry(HEAD, new)

    def test_main_checks_before_writing_anything(self):
        source = inspect.getsource(MODULE.main)
        apply_branch = source.split("if args.apply:", 1)[1]
        self.assertLess(
            apply_branch.index("require_new_whats_new_entry"),
            apply_branch.index("write_version("),
        )


if __name__ == "__main__":
    unittest.main()
