import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev" / "build_pages_site.py"
SPEC = importlib.util.spec_from_file_location("build_pages_site", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TestBuildPagesSite(unittest.TestCase):
    def test_markdown_to_html_renders_heading_and_list(self):
        html = MODULE.markdown_to_html("# Title\n\n- one\n- two\n")
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>two</li>", html)

    def test_build_index_page_links_to_changelog(self):
        html = MODULE.build_index_page()
        self.assertIn('href="changelog.html"', html)

    def test_build_index_page_inlines_current_app_version(self):
        html = MODULE.build_index_page()
        version = MODULE.read_version()
        self.assertIn(f"Version {version}", html)
        self.assertIn(f"Application</strong>: KeyQuest {version}", html)

    def test_build_index_page_inlines_the_release_date(self):
        # 1.28.1 review, finding 8: the guide's About section said
        # "Release Date: 2026-02-19" under every version since February.
        html = MODULE.build_index_page()
        self.assertIn(f"Release Date</strong>: {MODULE.read_release_date()}", html)
        self.assertNotIn("2026-02-19", html)
        self.assertNotIn("{{APP_RELEASE_DATE}}", html)

    def test_build_changelog_page_uses_user_friendly_title(self):
        html = MODULE.build_changelog_page()
        self.assertIn("<title>New in Key Quest</title>", html)
        self.assertIn("Back to the KeyQuest User Guide", html)


if __name__ == "__main__":
    unittest.main()
