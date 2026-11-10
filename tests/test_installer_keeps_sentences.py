"""Running the installer over an existing install keeps the user's sentences.

Fable review ui finding 6 (Casey's decision, 2026-11-10). The .iss installed
Sentences\\ with ignoreversion, so a by-hand run of KeyQuestSetup.exe (the
file the third update fallback tells the user to run) replaced every edited
sentence file with no backup. Only the in-app updater's bat protected them.

Now the installer writes the shipped set to Sentences only on a first install,
and to _sentences_incoming otherwise, so sentence_merge decides per file at
startup for every route. The updater bats no longer overwrite a set the
installer staged; with an older installer (which still overwrites Sentences)
they stage from Sentences exactly as before.

What these prove: the .iss checks read the script text (Inno is not run, so
the real proof is installing over an edited install on a clean machine); the
bat checks run the generated staging lines through real cmd.exe and robocopy.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import update_manager  # noqa: E402

ISS = ROOT / "tools" / "build" / "installer" / "KeyQuest.iss"
STAGE_FROM_SENTENCES = 'robocopy "%kqApp%\\Sentences" "%kqApp%\\_sentences_incoming"'


def _files_lines():
    text = ISS.read_text(encoding="utf-8")
    section = text.split("[Files]", 1)[1].split("\n[", 1)[0]
    return [line.strip() for line in section.splitlines() if line.strip().startswith("Source:")]


class TestIssKeepsSentences(unittest.TestCase):
    def test_wildcard_entry_excludes_only_the_top_level_sentences(self):
        wildcard = [line for line in _files_lines() if 'dist\\KeyQuest\\*"' in line]
        self.assertEqual(len(wildcard), 1)
        # A leading backslash anchors the pattern at the top of the tree; without
        # it Inno would also drop defaults\Sentences, which the merge needs.
        self.assertIn('Excludes: "\\Sentences\\*"', wildcard[0])

    def test_sentences_go_to_the_folder_only_on_a_first_install(self):
        lines = [line for line in _files_lines() if 'dist\\KeyQuest\\Sentences\\*"' in line]
        by_dest = {re.search(r'DestDir: "([^"]+)"', line).group(1): line for line in lines}
        self.assertEqual(set(by_dest), {"{app}\\Sentences", "{app}\\_sentences_incoming"})
        self.assertIn("Check: IsFirstSentencesInstall", by_dest["{app}\\Sentences"])
        self.assertIn("Check: not IsFirstSentencesInstall", by_dest["{app}\\_sentences_incoming"])

    def test_first_install_is_decided_once_before_files_are_copied(self):
        # A per-file DirExists check would turn false after the first file.
        text = ISS.read_text(encoding="utf-8")
        self.assertIn("CurStep = ssInstall", text)
        self.assertRegex(text, r"HadSentences\s*:=\s*DirExists\(ExpandConstant\('\{app\}\\Sentences'\)\)")


def _staging_block(bat_text: str) -> str:
    """The post-installer lines that stage _sentences_incoming from Sentences."""
    lines = bat_text.splitlines()
    index = next(i for i, line in enumerate(lines) if STAGE_FROM_SENTENCES in line)
    start = index
    while not (lines[start].startswith("if ") and lines[start].endswith("(")):
        start -= 1
    end = index
    while lines[end] != ")":
        end += 1
    return "\r\n".join(lines[start:end + 1])


@unittest.skipUnless(os.name == "nt", "cmd.exe and robocopy only")
class TestUpdaterBatsKeepInnoStaging(unittest.TestCase):
    def _bats(self, tmp: Path):
        installer = tmp / "Setup.exe"
        installer.write_bytes(b"stub")
        primary = update_manager.create_update_launcher(
            installer_path=installer, app_dir=str(tmp / "app"),
            app_exe_path=str(tmp / "app" / "KeyQuest.exe"), current_pid=4242,
            script_path=tmp / "i.bat",
        ).read_text(encoding="ascii")
        fallback = update_manager.create_installer_fallback_bat(
            installer_path=installer, app_dir=str(tmp / "app"),
            app_exe_path=str(tmp / "app" / "KeyQuest.exe"), bat_path=tmp / "if.bat",
        ).read_text(encoding="ascii")
        return {"primary": primary, "fallback": fallback}

    def _run_block(self, tmp: Path, block: str) -> None:
        script = tmp / "block.bat"
        script.write_bytes(
            (
                "@echo off\r\nsetlocal disabledelayedexpansion\r\n"
                f'set "kqApp={tmp / "app"}"\r\nset "kqLog={tmp / "log.txt"}"\r\n'
                f"{block}\r\n"
            ).encode("ascii")
        )
        subprocess.run(["cmd.exe", "/d", "/c", str(script)], cwd=tmp, check=True,
                       capture_output=True, timeout=60)

    def test_a_set_the_new_installer_staged_is_kept(self):
        for label in ("primary", "fallback"):
            with self.subTest(bat=label), tempfile.TemporaryDirectory() as tmp_name:
                tmp = Path(tmp_name)
                block = _staging_block(self._bats(tmp)[label])
                app = tmp / "app"
                (app / "Sentences").mkdir(parents=True)
                (app / "Sentences" / "English.txt").write_text("my own edit\n", encoding="utf-8")
                (app / "_sentences_incoming").mkdir()
                (app / "_sentences_incoming" / "English.txt").write_text("shipped\n", encoding="utf-8")

                self._run_block(tmp, block)

                self.assertEqual(
                    (app / "_sentences_incoming" / "English.txt").read_text(encoding="utf-8"),
                    "shipped\n",
                    "the bat replaced the installer's staged set with the user's own files",
                )

    def test_an_older_installer_that_overwrote_sentences_is_still_staged(self):
        # Negative twin: a rollback to an installer from before this change
        # still overwrites Sentences and stages nothing, so the bat must.
        for label in ("primary", "fallback"):
            with self.subTest(bat=label), tempfile.TemporaryDirectory() as tmp_name:
                tmp = Path(tmp_name)
                block = _staging_block(self._bats(tmp)[label])
                app = tmp / "app"
                (app / "Sentences").mkdir(parents=True)
                (app / "Sentences" / "English.txt").write_text("shipped\n", encoding="utf-8")

                self._run_block(tmp, block)

                self.assertEqual(
                    (app / "_sentences_incoming" / "English.txt").read_text(encoding="utf-8"),
                    "shipped\n",
                )

    def test_a_stale_staged_set_is_cleared_before_the_installer_runs(self):
        # The bat used to clear a leftover _sentences_incoming right before
        # staging. Now that staging can be skipped, it is cleared before the
        # installer runs, so a leftover set never passes for the new one.
        with tempfile.TemporaryDirectory() as tmp_name:
            for label, text in self._bats(Path(tmp_name)).items():
                with self.subTest(bat=label):
                    clear = text.index('rmdir /s /q "%kqApp%\\_sentences_incoming"')
                    run = text.index('"%kqInstaller%" /CURRENTUSER')
                    self.assertLess(clear, run)


if __name__ == "__main__":
    unittest.main()
