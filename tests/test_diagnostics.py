"""Tests for the diagnostics bundle behind About > Report a Problem.

The point of the feature is that a blind user reporting a bug should not have
to hunt for files. So the tests care most about two things: the bundle contains
what a maintainer actually needs, and the user is told plainly what happened
even when part of it fails.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import about_menu, diagnostics


class TestReportContents(unittest.TestCase):
    def test_report_names_the_version_and_platform(self):
        report = diagnostics.build_report()
        from modules.version import __version__

        self.assertIn(__version__, report)
        self.assertIn("Python:", report)
        self.assertIn("Windows:", report)

    def test_speech_state_and_settings_are_included(self):
        report = diagnostics.build_report(
            speech_state={"backend": "sapi", "screen_reader": "none"},
            settings={"speech_mode": "auto", "tts_voice": "(default)"},
        )
        self.assertIn("backend: sapi", report)
        self.assertIn("screen_reader: none", report)
        self.assertIn("speech_mode: auto", report)

    def test_both_logs_get_a_section_even_when_absent(self):
        """A missing log is information, so it must still be reported."""
        report = diagnostics.build_report()
        self.assertIn("Error log", report)
        self.assertIn("Speech log", report)

    def test_absent_speech_log_explains_how_to_produce_one(self):
        with patch(
            "modules.speech_log.get_log_path",
            return_value=os.path.join(tempfile.gettempdir(), "definitely-not-here.log"),
        ):
            report = diagnostics.build_report()
        self.assertIn("Turn on Speech Log in Options", report)

    def test_a_large_log_is_tailed_not_truncated_from_the_front(self):
        """A fault is at the END of a log, so the tail is the useful half."""
        handle, path = tempfile.mkstemp(suffix="-speech.log")
        os.close(handle)
        with open(path, "w", encoding="utf-8") as file:
            file.write("OLDEST-LINE\n")
            file.write("filler line\n" * 40000)
            file.write("NEWEST-LINE\n")
        try:
            with patch("modules.speech_log.get_log_path", return_value=path):
                report = diagnostics.build_report()
        finally:
            os.unlink(path)

        self.assertIn("NEWEST-LINE", report, "the most recent entries were dropped")
        self.assertNotIn("OLDEST-LINE", report)
        self.assertIn("trimmed to the most recent entries", report)


class TestWriting(unittest.TestCase):
    def test_writes_a_timestamped_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = diagnostics.write_report("hello", output_dir=folder)
            self.assertTrue(path.exists())
            self.assertTrue(path.name.startswith("KeyQuest-diagnostics-"))
            self.assertTrue(path.name.endswith(".txt"))
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")

    def test_two_reports_do_not_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            first = diagnostics.write_report("a", output_dir=folder, timestamp=1000)
            second = diagnostics.write_report("b", output_dir=folder, timestamp=2000)
            self.assertNotEqual(first.name, second.name)


class TestClipboardIsThePrimaryRoute(unittest.TestCase):
    """Pasting is one keystroke; attaching means a file dialog with a screen reader."""

    def test_a_short_report_goes_to_the_clipboard_whole(self):
        report = diagnostics.build_report(speech_state={"backend": "sapi"})
        if len(report) > 60_000:
            self.skipTest("local logs are large; covered by the shortening test")
        text, shortened = diagnostics.clipboard_text(report, "file.txt")
        self.assertFalse(shortened)
        self.assertEqual(text, report)

    def test_a_huge_report_is_shortened_to_the_summary(self):
        report = "KeyQuest diagnostics\nversion line\n" + diagnostics._SECTION_MARKER \
            + "Error log =====\n" + ("x" * 200_000)
        text, shortened = diagnostics.clipboard_text(report, "bundle.txt")
        self.assertTrue(shortened)
        self.assertLess(len(text), 60_000)
        self.assertIn("KeyQuest diagnostics", text, "the summary must survive")
        self.assertIn("bundle.txt", text, "must name the file that has the rest")
        self.assertNotIn("x" * 1000, text, "the log body should not be pasted")


class TestWhatTheUserIsTold(unittest.TestCase):
    """No visual-only references, and no silent failures."""

    def test_names_the_file_and_folder_rather_than_pointing(self):
        message = diagnostics.describe_result(
            Path(r"C:\Users\someone\Downloads\KeyQuest-diagnostics-x.txt"),
            clipboard_ok=True,
            folder_ok=True,
        )
        self.assertIn("KeyQuest-diagnostics-x.txt", message)
        self.assertIn("Downloads", message)
        for spatial in ("above", "below", "the window that", "on the left", "on the right"):
            self.assertNotIn(spatial, message.lower())

    def test_pasting_is_offered_first(self):
        message = diagnostics.describe_result(Path("x.txt"), True, True)
        self.assertIn("clipboard", message.lower())
        self.assertLess(
            message.lower().index("clipboard"),
            message.lower().index("saved as"),
            "the paste route should be mentioned before the file route",
        )

    def test_a_failed_clipboard_copy_is_not_silent(self):
        path = Path(r"C:\Users\someone\Downloads\KeyQuest-diagnostics-x.txt")
        without = diagnostics.describe_result(path, False, True)
        self.assertIn("could not use the clipboard", without.lower())
        self.assertIn(str(path), without,
                      "if the clipboard failed the user must still hear the full path")

    def test_a_shortened_clipboard_says_to_send_the_file_too(self):
        message = diagnostics.describe_result(Path("x.txt"), True, True, clipboard_shortened=True)
        self.assertIn("too long", message.lower())
        self.assertIn("file", message.lower())

    def test_the_support_address_is_always_given(self):
        for clip in (True, False):
            for shortened in (True, False):
                with self.subTest(clipboard=clip, shortened=shortened):
                    message = diagnostics.describe_result(Path("x.txt"), clip, False, shortened)
                    self.assertIn(diagnostics.SUPPORT_EMAIL, message)


class TestAboutMenuWiring(unittest.TestCase):
    def test_report_item_exists_and_is_actionable(self):
        items = about_menu.build_about_items("9.9.9")
        ids = [item["id"] for item in items]
        self.assertIn("report_problem", ids)
        self.assertLess(ids.index("report_problem"), ids.index("back"),
                        "Report a Problem should come before Back to Main Menu")

    def test_selecting_it_calls_the_handler(self):
        called = []
        spoken = []
        speech = type("S", (), {"say": lambda _s, text, **_k: spoken.append(text)})()
        about_menu.handle_about_select(
            {"id": "report_problem"},
            speech=speech,
            return_to_main_menu=lambda: None,
            open_url=lambda *a, **k: None,
            donate_url="",
            save_diagnostics=lambda: called.append(True),
        )
        self.assertEqual(called, [True])

    def test_it_says_something_when_diagnostics_are_unavailable(self):
        spoken = []
        speech = type("S", (), {"say": lambda _s, text, **_k: spoken.append(text)})()
        about_menu.handle_about_select(
            {"id": "report_problem"},
            speech=speech,
            return_to_main_menu=lambda: None,
            open_url=lambda *a, **k: None,
            donate_url="",
        )
        self.assertTrue(spoken, "an unavailable feature must not fail silently")

    def test_no_emoji_or_symbols_in_the_new_item(self):
        items = about_menu.build_about_items("9.9.9")
        item = next(i for i in items if i["id"] == "report_problem")
        for value in (item["display"], item["speak"]):
            self.assertTrue(value.isascii(), f"non-ASCII in spoken text: {value!r}")


if __name__ == "__main__":
    unittest.main()
