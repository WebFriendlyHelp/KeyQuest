import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev" / "release_bump.py"
SPEC = importlib.util.spec_from_file_location("release_bump", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TestReleaseDate(unittest.TestCase):
    """1.28.1 review, finding 1: the What's New heading said Wednesday November
    11th, the release was made on Thursday the 12th, and --validate compared
    only version strings, so nothing noticed. The heading, __release_date__ and
    the guide's About line must agree, and release.ps1 requires that date to be
    the day it runs. These test the functions; they do not run release.ps1."""

    WHATS_NEW = (
        "# New in Key Quest\n\n"
        "## Wednesday November 11th 2026\n\n"
        "Version 1.28.1\n\n"
        "Notes.\n\n"
        "## Wednesday November 11th 2026\n\n"
        "Version 1.28.0\n"
    )

    def test_heading_format_with_ordinals(self):
        import datetime as dt

        cases = {
            dt.date(2026, 11, 12): "Thursday November 12th 2026",
            dt.date(2026, 11, 1): "Sunday November 1st 2026",
            dt.date(2026, 11, 2): "Monday November 2nd 2026",
            dt.date(2026, 11, 3): "Tuesday November 3rd 2026",
            dt.date(2026, 11, 11): "Wednesday November 11th 2026",
            dt.date(2026, 11, 13): "Friday November 13th 2026",
            dt.date(2026, 11, 21): "Saturday November 21st 2026",
            dt.date(2026, 11, 22): "Sunday November 22nd 2026",
            dt.date(2026, 11, 23): "Monday November 23rd 2026",
        }
        for date, expected in cases.items():
            with self.subTest(date=date):
                self.assertEqual(MODULE.format_whats_new_heading(date), expected)

    def test_set_whats_new_date_rewrites_only_the_top_heading(self):
        import datetime as dt

        updated = MODULE.set_whats_new_date_text(self.WHATS_NEW, dt.date(2026, 11, 12))
        self.assertTrue(updated.startswith("# New in Key Quest\n\n## Thursday November 12th 2026\n\nVersion 1.28.1"))
        self.assertIn("## Wednesday November 11th 2026\n\nVersion 1.28.0", updated)

    def _validate(self, whats_new, release_date):
        original = (MODULE.read_pyproject_version, MODULE.SITE_INDEX_FILE)
        MODULE.read_pyproject_version = lambda _source=None: "1.28.1"
        MODULE.SITE_INDEX_FILE = pathlib.Path("no-such-site-index.html")
        try:
            MODULE.validate_release_metadata("1.28.1", whats_new, release_date)
        finally:
            MODULE.read_pyproject_version, MODULE.SITE_INDEX_FILE = original

    def test_validate_refuses_a_heading_that_is_not_the_release_date(self):
        with self.assertRaises(SystemExit):
            self._validate(self.WHATS_NEW, "2026-11-12")

    def test_validate_accepts_matching_heading_and_date(self):
        # Twin: the same text with the release date it names passes.
        self._validate(self.WHATS_NEW, "2026-11-11")

    def test_validate_refuses_a_wrong_day_name(self):
        wrong_day = self.WHATS_NEW.replace("## Wednesday November 11th", "## Thursday November 11th", 1)
        with self.assertRaises(SystemExit):
            self._validate(wrong_day, "2026-11-11")

    def test_release_date_must_be_today(self):
        import datetime as dt

        with self.assertRaises(SystemExit):
            MODULE.require_release_date_today("2026-11-11", today=dt.date(2026, 11, 12))
        MODULE.require_release_date_today("2026-11-12", today=dt.date(2026, 11, 12))


class TestReleaseBump(unittest.TestCase):
    def test_sync_readme_version_text_normalises_to_placeholder(self):
        """sync_readme_version_text keeps README.html as a template with {{APP_VERSION}}.

        The real version is substituted at site-generation time by build_index_page().
        Both the placeholder form and a stale hardcoded version should normalise to
        the placeholder so the source file stays clean across releases.
        """
        # Placeholder already present — should remain as-is
        source_placeholder = (
            "<p><strong>Version {{APP_VERSION}}</strong></p>\n"
            "<li><strong>Application</strong>: KeyQuest {{APP_VERSION}}</li>\n"
        )
        updated = MODULE.sync_readme_version_text(source_placeholder, "2.0.1")
        self.assertIn("Version {{APP_VERSION}}", updated)
        self.assertIn("KeyQuest {{APP_VERSION}}", updated)
        self.assertNotIn("2.0.1", updated)

        # Stale hardcoded version — should also normalise to placeholder
        source_hardcoded = (
            "<p><strong>Version 1.9.4</strong></p>\n"
            "<li><strong>Application</strong>: KeyQuest 1.9.4</li>\n"
        )
        updated2 = MODULE.sync_readme_version_text(source_hardcoded, "2.0.1")
        self.assertIn("Version {{APP_VERSION}}", updated2)
        self.assertIn("KeyQuest {{APP_VERSION}}", updated2)
        self.assertNotIn("1.9.4", updated2)

    def test_sync_whats_new_version_text_updates_first_visible_version_only(self):
        source = (
            "# New in Key Quest\n\n"
            "## Friday March 20th 2026\n\n"
            "Version 1.3.0\n\n"
            "Notes.\n\n"
            "Version 1.2.9\n"
        )
        updated = MODULE.sync_whats_new_version_text(source, "1.3.1")
        self.assertIn("Version 1.3.1", updated)
        self.assertIn("Version 1.2.9", updated)

    def test_pyproject_version_helpers_read_and_update_project_version(self):
        source = (
            "[project]\n"
            'name = "keyquest"\n'
            'version = "1.8.0"\n'
            'description = "Accessible typing adventure game"\n'
        )
        self.assertEqual(MODULE.read_pyproject_version(source), "1.8.0")
        updated = MODULE.sync_pyproject_version_text(source, "1.19.0")
        self.assertIn('version = "1.19.0"', updated)
        self.assertNotIn('version = "1.8.0"', updated)

    def test_read_top_whats_new_version_returns_first_visible_version(self):
        source = (
            "# New in Key Quest\n\n"
            "## Saturday March 21st 2026\n\n"
            "Version 1.5.2\n\n"
            "Notes.\n\n"
            "Version 1.5.1\n"
        )
        self.assertEqual(MODULE.read_top_whats_new_version(source), "1.5.2")

    def test_validate_release_metadata_raises_when_versions_do_not_match(self):
        source = (
            "# New in Key Quest\n\n"
            "## Saturday March 21st 2026\n\n"
            "Version 1.5.1\n\n"
            "Notes.\n"
        )
        with self.assertRaises(SystemExit):
            MODULE.validate_release_metadata("1.5.2", source)

    def test_validate_release_metadata_raises_when_pyproject_differs(self):
        source = (
            "# New in Key Quest\n\n"
            "## Saturday March 21st 2026\n\n"
            "Version 1.5.2\n\n"
            "Notes.\n"
        )
        original_reader = MODULE.read_pyproject_version
        MODULE.read_pyproject_version = lambda _source=None: "1.5.1"
        try:
            with self.assertRaises(SystemExit):
                MODULE.validate_release_metadata("1.5.2", source)
        finally:
            MODULE.read_pyproject_version = original_reader


if __name__ == "__main__":
    unittest.main()
