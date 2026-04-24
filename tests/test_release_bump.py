import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev" / "release_bump.py"
SPEC = importlib.util.spec_from_file_location("release_bump", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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
