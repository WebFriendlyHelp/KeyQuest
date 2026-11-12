"""Uninstalling KeyQuest removes everything KeyQuest itself wrote.

Casey, 2026-11-11: "if kq is removed then everything should go with it as it's
part of that program. uninstall should remove everything." Up to 1.28.0 the
uninstaller removed only what the installer had copied, so progress.json,
sentence_prefs.json and the error log stayed behind (found in the VM).

How this test works: it points every writer at a temporary install folder and
a temporary TEMP folder, makes each one write the way the real app does, and
then requires every file and folder that appeared to be covered by an entry in
KeyQuest.iss [UninstallDelete]. Files that only appear in rare cases (a
rotated speech log, an unreadable progress file set aside) are listed by hand
next to the code that names them.

What this would still pass on: Inno Setup is not run, so a mistake in how Inno
expands a constant or a wildcard would pass here. A writer added later that
this file does not exercise would also pass. The real proof is the VM
checklist: install, use, uninstall, list what is left.

The updater must never run the uninstaller, or an update would now lose
progress; test_updater_never_runs_the_uninstaller pins that.
"""

import fnmatch
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import (  # noqa: E402
    error_logging,
    sentence_merge,
    speech_log,
    state_manager,
    update_manager,
)

ISS = ROOT / "tools" / "build" / "installer" / "KeyQuest.iss"


def uninstall_entries(text: str | None = None) -> list[tuple[str, str]]:
    """(Type, Name) for each [UninstallDelete] line, comments skipped."""
    text = ISS.read_text(encoding="utf-8") if text is None else text
    if "[UninstallDelete]" not in text:
        return []
    section = text.split("[UninstallDelete]", 1)[1].split("\n[", 1)[0]
    entries = []
    for line in section.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        kind = re.search(r'Type:\s*(\w+)', line, re.IGNORECASE)
        name = re.search(r'Name:\s*"([^"]+)"', line, re.IGNORECASE)
        if kind and name:
            entries.append((kind.group(1).lower(), name.group(1)))
    return entries


def _expand(name: str, app_dir: Path, temp_dir: Path) -> str:
    expanded = name.replace("{app}", str(app_dir)).replace("{%TEMP}", str(temp_dir))
    return os.path.normcase(os.path.normpath(expanded))


def is_covered(path: Path, entries, app_dir: Path, temp_dir: Path) -> bool:
    """Would one of the entries delete this path (or a folder holding it)?"""
    target = os.path.normcase(os.path.normpath(str(path)))
    for kind, name in entries:
        pattern = _expand(name, app_dir, temp_dir)
        if kind in ("files", "filesandordirs") and fnmatch.fnmatchcase(target, pattern):
            return True
        if kind == "filesandordirs":
            # A folder entry takes everything inside it.
            for parent in Path(target).parents:
                if fnmatch.fnmatchcase(os.path.normcase(str(parent)), pattern):
                    return True
    return False


def write_everything(app_dir: Path, temp_dir: Path) -> None:
    """Make each KeyQuest writer write into app_dir and temp_dir."""
    app = str(app_dir)
    with mock.patch.object(error_logging, "get_app_dir", return_value=app), mock.patch.object(
        speech_log, "get_app_dir", return_value=app
    ), mock.patch.object(state_manager, "get_app_dir", return_value=app), mock.patch.object(
        update_manager.tempfile, "gettempdir", return_value=str(temp_dir)
    ), mock.patch.dict(os.environ, {"KEYQUEST_PROGRESS_PATH": ""}):
        error_logging.log_message("Uninstall test", "a line in the error log")

        log = speech_log.SpeechLog()
        log.enable()
        log.record("SPOKE", "hello")
        log.disable()

        manager = state_manager.ProgressManager()
        manager.save(state_manager.AppState())

        sentence_merge._save_prefs(app_dir, {"customised": ["Animals.txt"]})
        update_manager.write_pending_update_marker(app, "9.9.9")
        update_manager.create_app_backup_zip(app, "1.28.0")
        (update_manager.get_updates_dir() / "run_keyquest_update.bat").write_text("rem", encoding="utf-8")

    # Folders the merge and the update bats create.
    incoming = app_dir / sentence_merge.INCOMING_DIR_NAME
    incoming.mkdir()
    (incoming / "Animals.txt").write_text("cat\n", encoding="utf-8")
    # A sentence file the learner made themselves; the installer never knew it.
    (app_dir / "Sentences" / "My own sentences.txt").write_text("mine\n", encoding="utf-8")


# Written only in rare cases, each named where the code names it.
def rare_paths(app_dir: Path, temp_dir: Path) -> list[Path]:
    progress = app_dir / "progress.json"
    speech = app_dir / speech_log.LOG_FILENAME
    return [
        progress.with_name(progress.name + ".unreadable-1731300000"),  # state_manager, unreadable file set aside
        progress.with_suffix(".recovered.json"),  # state_manager, original could not be rescued
        Path(str(progress.with_suffix(".recovered.json")) + ".tmp"),  # its atomic-write temp
        Path(str(progress) + ".tmp"),  # state_manager.save atomic-write temp
        Path(str(speech) + ".1"),  # speech_log rotation
        app_dir / ".keyquest-installed",  # KeyQuest.iss [Run] marker, not in the uninstall log
        app_dir / "updates" / "old.exe",  # older releases staged updates here
        temp_dir / "keyquest_update.sha256",  # update_manager sidecar download
    ]


def _all_paths(root: Path) -> set[Path]:
    return {p for p in root.rglob("*")}


class TestUninstallRemovesEverything(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.app_dir = base / "Programs" / "KeyQuest"
        self.temp_dir = base / "Temp"
        self.app_dir.mkdir(parents=True)
        self.temp_dir.mkdir()
        # What the installer copies (and so its own uninstall log removes).
        (self.app_dir / "KeyQuest.exe").write_bytes(b"MZ")
        (self.app_dir / "Sentences").mkdir()
        (self.app_dir / "Sentences" / "Animals.txt").write_text("dog\n", encoding="utf-8")
        self.installed = _all_paths(self.app_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _uncovered(self, entries) -> list[str]:
        write_everything(self.app_dir, self.temp_dir)
        made = (_all_paths(self.app_dir) - self.installed) | _all_paths(self.temp_dir)
        made |= set(rare_paths(self.app_dir, self.temp_dir))
        missing = [
            str(p)
            for p in sorted(made)
            if not is_covered(p, entries, self.app_dir, self.temp_dir)
            # A folder is fine uncovered when it only exists to hold covered files.
            and not (p.is_dir() and all(is_covered(c, entries, self.app_dir, self.temp_dir) for c in p.rglob("*") if c.is_file()))
        ]
        return missing

    def test_every_file_keyquest_writes_is_removed_on_uninstall(self):
        entries = uninstall_entries()
        missing = self._uncovered(entries)
        self.assertEqual(missing, [], "Left behind after uninstall:\n" + "\n".join(missing))
        # The writers really ran: the progress file and the error log exist.
        self.assertTrue((self.app_dir / "progress.json").is_file())
        self.assertTrue((self.app_dir / error_logging.LOG_FILE).is_file())
        self.assertTrue((self.app_dir / sentence_merge.PREFS_FILE_NAME).is_file())

    def test_the_check_can_fail(self):
        # Negative twin: drop the progress entry and the progress file must be reported.
        entries = [e for e in uninstall_entries() if "progress" not in e[1].lower()]
        missing = self._uncovered(entries)
        self.assertTrue(any(m.endswith("progress.json") for m in missing), missing)

    def test_never_deletes_the_whole_install_folder_blind(self):
        # A user can pass /DIR= to the installer. Deleting {app} wholesale would then
        # take files that are not KeyQuest's. Each entry names something KeyQuest owns.
        for kind, name in uninstall_entries():
            if kind == "dirifempty":
                continue  # removes the folder only once nothing is left in it
            normalized = name.rstrip("\\")
            self.assertNotIn(normalized, ("{app}", "{app}\\*", "{%TEMP}", "{%TEMP}\\*"), (kind, name))
            if name.startswith("{%TEMP}"):
                self.assertIn("keyquest", name.lower(), name)


class TestUpdatesKeepProgress(unittest.TestCase):
    def test_updater_never_runs_the_uninstaller(self):
        # [UninstallDelete] now removes progress, so an update path that ran the
        # uninstaller would lose it. The bats run KeyQuestSetup.exe over the top.
        for path in (ROOT / "modules" / "update_manager.py", ROOT / "modules" / "update_controller.py"):
            self.assertNotRegex(path.read_text(encoding="utf-8").lower(), r"unins\d*\.exe|uninstall", path.name)

    def test_installer_bat_still_restores_progress(self):
        # Source text, so the escapes are the Python literal's.
        text = (ROOT / "modules" / "update_manager.py").read_text(encoding="utf-8")
        self.assertIn(r'copy /Y \"%kqBackup%\\progress.json\" \"%kqApp%\\progress.json\"', text)
        self.assertIn("Installer succeeded. Restored saved progress.", text)


if __name__ == "__main__":
    unittest.main()
