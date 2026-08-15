"""Tests for the diagnostics bundle behind About > Report a Problem.

The point of the feature is that a blind user reporting a bug should not have
to hunt for files. So the tests care most about two things: the bundle contains
what a maintainer actually needs, and the user is told plainly what happened
even when part of it fails.
"""

import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules import about_menu, diagnostics, keyquest_app


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
            self.assertTrue(path.name.startswith("KeyQuest problem report "))
            self.assertTrue(path.name.endswith(".txt"))
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")

    def test_two_reports_do_not_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            first = diagnostics.write_report("a", output_dir=folder, timestamp=1000)
            second = diagnostics.write_report("b", output_dir=folder, timestamp=2000)
            self.assertNotEqual(first.name, second.name)

    def test_two_reports_in_the_same_minute_do_not_overwrite_each_other(self):
        """The name is only accurate to the minute, so this is reachable."""
        with tempfile.TemporaryDirectory() as folder:
            first = diagnostics.write_report("first", output_dir=folder, timestamp=1000)
            second = diagnostics.write_report("second", output_dir=folder, timestamp=1000)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_text(encoding="utf-8"), "first",
                             "the earlier report must survive")
            self.assertIn("(2)", second.name)


class TestTheFileName(unittest.TestCase):
    """It gets read aloud, read back over the phone, and hunted for in a folder."""

    def test_it_reads_as_words_rather_than_a_wall_of_digits(self):
        name = diagnostics.build_filename(1786800000.0)
        self.assertTrue(name.startswith("KeyQuest problem report "))
        self.assertIn(" at ", name)
        self.assertTrue(name.endswith(".txt"))
        self.assertNotIn("diagnostics", name.lower(),
                         "that is our word for it, not the user's")
        digits = max((len(run) for run in re.findall(r"\d+", name)), default=0)
        self.assertLessEqual(digits, 4, f"a run of digits that long is unreadable: {name}")

    def test_the_hour_is_not_zero_padded_and_carries_am_or_pm(self):
        morning = diagnostics.build_filename(time.mktime((2026, 8, 15, 9, 5, 0, 0, 0, -1)))
        evening = diagnostics.build_filename(time.mktime((2026, 8, 15, 13, 26, 0, 0, 0, -1)))
        self.assertIn("at 9-05 AM", morning)
        self.assertIn("at 1-26 PM", evening)

    def test_it_names_the_day_the_way_a_person_would_say_it(self):
        name = diagnostics.build_filename(time.mktime((2026, 8, 15, 14, 46, 0, 0, 0, -1)))
        self.assertIn("for Saturday August 15th 2026", name)

    def test_ordinals_are_right_including_the_ones_that_catch_people_out(self):
        cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th",
                 11: "11th", 12: "12th", 13: "13th",
                 21: "21st", 22: "22nd", 23: "23rd", 31: "31st"}
        for day, expected in cases.items():
            with self.subTest(day=day):
                self.assertEqual(diagnostics._ordinal(day), expected)

    def test_midnight_and_noon_do_not_come_out_as_zero(self):
        midnight = diagnostics.build_filename(time.mktime((2026, 8, 3, 0, 7, 0, 0, 0, -1)))
        noon = diagnostics.build_filename(time.mktime((2026, 8, 3, 12, 7, 0, 0, 0, -1)))
        self.assertIn("at 12-07 AM", midnight)
        self.assertIn("at 12-07 PM", noon)

    def test_it_is_a_legal_windows_filename(self):
        name = diagnostics.build_filename(1786800000.0)
        for illegal in '<>:"/\\|?*':
            self.assertNotIn(illegal, name)


class TestWhereItIsWritten(unittest.TestCase):
    """It said "your Downloads folder" while writing somewhere else entirely."""

    def test_the_real_downloads_folder_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(diagnostics, "_known_folder_downloads",
                              return_value=Path(folder)):
                self.assertEqual(diagnostics.default_output_dir(), Path(folder))

    def test_it_falls_back_to_the_guess_then_to_home(self):
        """OneDrive moves Downloads, so the guess can simply not exist."""
        with patch.object(diagnostics, "_known_folder_downloads", return_value=None):
            with patch.object(Path, "is_dir", return_value=False):
                self.assertEqual(diagnostics.default_output_dir(), Path.home())

    def test_the_known_folder_lookup_never_raises(self):
        """It is ctypes against the shell; a failure must not lose the report."""
        with patch("ctypes.windll") as windll:
            windll.shell32.SHGetKnownFolderPath.side_effect = OSError("no shell")
            self.assertIsNone(diagnostics._known_folder_downloads())
            self.assertIsNotNone(diagnostics.default_output_dir())


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
        )
        self.assertIn("KeyQuest-diagnostics-x.txt", message)
        self.assertIn("Downloads", message)
        for spatial in ("above", "below", "the window that", "on the left", "on the right"):
            self.assertNotIn(spatial, message.lower())

    def test_pasting_is_offered_first(self):
        message = diagnostics.describe_result(Path("x.txt"), True)
        self.assertIn("clipboard", message.lower())
        self.assertLess(
            message.lower().index("clipboard"),
            message.lower().index("saved as"),
            "the paste route should be mentioned before the file route",
        )

    def test_a_failed_clipboard_copy_is_not_silent(self):
        path = Path(r"C:\Users\someone\Downloads\KeyQuest-diagnostics-x.txt")
        without = diagnostics.describe_result(path, False)
        self.assertIn("could not use the clipboard", without.lower())
        self.assertIn(str(path), without,
                      "if the clipboard failed the user must still hear the full path")

    def test_a_shortened_clipboard_says_to_send_the_file_too(self):
        message = diagnostics.describe_result(Path("x.txt"), True, clipboard_shortened=True)
        self.assertIn("too long", message.lower())
        self.assertIn("file", message.lower())

    def test_the_support_address_is_always_given(self):
        for clip in (True, False):
            for shortened in (True, False):
                with self.subTest(clipboard=clip, shortened=shortened):
                    message = diagnostics.describe_result(Path("x.txt"), clip, shortened)
                    self.assertIn(diagnostics.SUPPORT_EMAIL, message)

    def test_the_saved_message_never_claims_to_have_opened_anything(self):
        """Saving and opening are two steps, and only the first has happened."""
        for clip in (True, False):
            message = diagnostics.describe_result(Path("x.txt"), clip).lower()
            for claim in ("folder is now open", "window", "explorer", "selected"):
                self.assertNotIn(
                    claim, message,
                    "the message must not claim to have opened anything")


class TestTheFolderQuestion(unittest.TestCase):
    """Opening Explorer unasked threw the user out of KeyQuest. Owner feedback."""

    PATH = Path(r"C:\Users\someone\Downloads\KeyQuest-diagnostics-x.txt")

    def _question(self, saved="Saved."):
        return diagnostics.open_folder_question(self.PATH, saved)

    def test_it_is_a_question_and_names_what_it_would_open(self):
        question = self._question()
        self.assertTrue(question.title.endswith("?"))
        self.assertIn("Downloads", question.title)
        self.assertIn("KeyQuest-diagnostics-x.txt", question.body)

    def test_the_dialog_carries_the_saved_message_itself(self):
        """Speaking it and then raising a dialog cuts the spoken line off."""
        question = self._question("The diagnostics are on your clipboard.")
        self.assertIn("The diagnostics are on your clipboard.", question.body)

    def test_the_buttons_say_what_they_do(self):
        """By the time you tab to a button, "Yes" has lost its question."""
        question = self._question()
        self.assertNotIn(question.yes_label.lower(), ("yes", "ok"))
        self.assertNotIn(question.no_label.lower(), ("no", "cancel"))
        self.assertIn("Downloads", question.yes_label)
        self.assertIn("KeyQuest", question.no_label)

    def test_declining_is_stated_as_harmless(self):
        body = self._question().body.lower()
        self.assertIn("keyquest stays open", body)

    def test_no_spatial_language_and_no_symbols_anywhere_in_it(self):
        question = self._question()
        for text in question:
            self.assertTrue(text.isascii(), f"non-ASCII in spoken text: {text!r}")
            for spatial in ("above", "below", "on the left", "on the right", "click here"):
                self.assertNotIn(spatial, text.lower())


class TestReportProblemNeverOpensAnythingUnasked(unittest.TestCase):
    """The whole flow, from the About menu item to Explorer or not.

    Built on a bare app object rather than a running one, the way
    test_escape_policy does, so no pygame window or wx app is needed.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.written = Path(self.temp.name) / "KeyQuest-diagnostics-test.txt"

        self.revealed = []
        self.asked = []
        self.spoken = []

        app = object.__new__(keyquest_app.KeyQuestApp)
        app.state = SimpleNamespace(settings=SimpleNamespace(
            speech_mode="auto", speech_log=False, tts_rate=0, tts_volume=100,
            tts_voice=None, current_lesson=1, sentence_language="english",
        ))
        app.speech = SimpleNamespace(
            say=lambda text, **kwargs: self.spoken.append(text),
            describe_for_log=lambda: {"backend": "sapi"},
        )
        self.app = app

    def _run(self, answer, wx_available=True, reveal_ok=True):
        def write_report(text, *args, **kwargs):
            self.written.write_text(text, encoding="utf-8")
            return self.written

        def ask(title, body, **kwargs):
            self.asked.append((title, body, self.written.exists()))
            return answer

        def reveal(path):
            self.revealed.append(path)
            return reveal_ok

        with patch.object(diagnostics, "write_report", write_report), \
             patch.object(keyquest_app.error_logging, "copy_text_to_clipboard",
                          lambda _text: True), \
             patch.object(keyquest_app.dialog_manager, "WX_AVAILABLE", wx_available), \
             patch.object(keyquest_app.dialog_manager, "show_yes_no_dialog", ask), \
             patch.object(keyquest_app.KeyQuestApp, "_reveal_in_explorer",
                          staticmethod(reveal)):
            self.app.save_diagnostics_report()

    def test_declining_opens_nothing(self):
        self._run(answer=False)
        self.assertEqual(len(self.asked), 1, "the user must be asked")
        self.assertEqual(self.revealed, [], "answering no must open nothing")

    def test_accepting_opens_the_file_that_was_just_written(self):
        self._run(answer=True)
        self.assertEqual(self.revealed, [self.written])

    def test_the_file_exists_before_the_question_is_asked(self):
        """Otherwise a fast Yes reveals a file that is not there yet."""
        self._run(answer=True)
        self.assertTrue(self.asked[0][2], "the file must be written before asking")

    def test_nothing_is_spoken_before_the_dialog(self):
        """The dialog announcement would cut a spoken line off partway."""
        self._run(answer=True)
        self.assertEqual(self.spoken, [],
                         "the dialog carries the message; speaking it too talks over it")

    def test_a_failure_to_open_is_spoken_with_the_full_path(self):
        self._run(answer=True, reveal_ok=False)
        self.assertTrue(self.spoken, "a silent failure leaves the user waiting")
        self.assertIn(str(self.written), " ".join(self.spoken))

    def test_without_wx_it_speaks_the_result_and_still_opens_nothing(self):
        """No dialog to read means speech is the only channel left."""
        self._run(answer=True, wx_available=False)
        self.assertEqual(self.asked, [], "no dialog can be shown")
        self.assertEqual(self.revealed, [], "and nothing is opened unasked")
        self.assertIn("clipboard", " ".join(self.spoken).lower())

    def test_the_explorer_command_quotes_a_path_containing_spaces(self):
        """Quoted wrong, Explorer opens the default folder with nothing selected.

        It does not take an unusual file name to reach this, only a user whose
        account name has a space in it.
        """
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command

        target = Path(r"C:\Users\John Smith\Downloads\KeyQuest problem report.txt")
        with patch.object(keyquest_app.subprocess, "run", fake_run):
            ok = keyquest_app.KeyQuestApp._reveal_in_explorer(target)

        self.assertTrue(ok)
        self.assertIsInstance(seen["command"], str,
                              "a list argument lets subprocess re-quote the switch")
        self.assertIn(f'/select,"{target}"', seen["command"])

    def test_a_reveal_that_throws_is_reported_as_a_failure(self):
        with patch.object(keyquest_app.subprocess, "run",
                          side_effect=OSError("no explorer")):
            self.assertFalse(
                keyquest_app.KeyQuestApp._reveal_in_explorer(Path("x.txt")))

    def test_a_write_failure_is_spoken_and_stops_there(self):
        with patch.object(diagnostics, "write_report",
                          side_effect=OSError("disk full")), \
             patch.object(keyquest_app.dialog_manager, "show_yes_no_dialog",
                          lambda *a, **k: self.fail("must not ask after a failure")):
            self.app.save_diagnostics_report()
        self.assertTrue(self.spoken)
        self.assertEqual(self.revealed, [])


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

    def test_the_release_date_comes_from_the_version_file(self):
        """It read February 19 on a build shipped in August, for months."""
        from modules import version as version_module

        items = about_menu.build_about_items("9.9.9")
        item = next(i for i in items if i["id"] == "release_date")
        self.assertIn(version_module.__release_date__, item["display"])
        self.assertNotIn("2026-02-19", item["display"],
                         "the hardcoded date is back")

    def test_the_spoken_release_date_is_words_not_digits(self):
        self.assertEqual(about_menu.speak_release_date("2026-08-15"),
                         "Release date: August 15, 2026.")
        self.assertEqual(about_menu.speak_release_date("2026-01-01"),
                         "Release date: January 1, 2026.")

    def test_a_malformed_release_date_still_says_something(self):
        self.assertIn("nonsense", about_menu.speak_release_date("nonsense"))

    def test_every_fact_comes_from_the_version_module(self):
        """Literals here went stale for months without anyone noticing."""
        import inspect

        source = inspect.getsource(about_menu.build_about_items)
        for literal in ("Casey Mathews", "Web Friendly Help", "webfriendlyhelp.com",
                        "Helping You Tame", "2026"):
            self.assertNotIn(literal, source,
                             f"{literal!r} is typed here instead of read from version.py")

    def test_the_copyright_year_follows_the_release_not_the_clock(self):
        """A 2026 build opened in 2028 was still released in 2026."""
        from modules import version as version_module

        self.assertEqual(version_module.COPYRIGHT_YEAR,
                         version_module.__release_date__[:4])
        item = next(i for i in about_menu.build_about_items("9.9.9")
                    if i["id"] == "copyright")
        self.assertIn(version_module.COPYRIGHT_YEAR, item["display"])

    def test_initialisms_are_spoken_as_letters(self):
        """Otherwise a voice reads LLC as a word and MIT as "mit"."""
        self.assertEqual(about_menu.spell_initials("Web Friendly Help LLC"),
                         "Web Friendly Help L L C")
        self.assertEqual(about_menu.spell_initials("MIT"), "M I T")
        self.assertEqual(about_menu.spell_initials("Casey Mathews"), "Casey Mathews",
                         "ordinary words must not be spelled out")

    def test_the_website_link_and_the_spoken_address_agree(self):
        from modules import version as version_module

        self.assertIn(version_module.WEBSITE, about_menu.WEBSITE_URL)
        item = next(i for i in about_menu.build_about_items("9.9.9")
                    if i["id"] == "website")
        self.assertIn(version_module.WEBSITE, item["speak"])

    def test_no_emoji_or_symbols_in_the_new_item(self):
        items = about_menu.build_about_items("9.9.9")
        item = next(i for i in items if i["id"] == "report_problem")
        for value in (item["display"], item["speak"]):
            self.assertTrue(value.isascii(), f"non-ASCII in spoken text: {value!r}")


if __name__ == "__main__":
    unittest.main()
