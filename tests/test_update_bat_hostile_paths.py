"""Generated .bat launchers must survive awkward but legal Windows paths.

No test previously executed a generated launcher from anywhere other than a
clean ASCII path with no spaces, which is exactly the blind spot the path bugs
lived in.  The realistic trigger is a non-ASCII Windows user name: the app dir,
the staging dir, the exe and the log path all run through it, and cmd.exe parses
.bat files in the console OEM code page rather than UTF-8, so one such character
used to turn every path in the script into mojibake, including the restart line
the no-stranding guarantee depends on.

These tests generate launchers for hostile paths, assert the resulting script is
still pure ASCII with everything substituted, and then actually run the portable
launcher end to end to prove the file operations land in the right place.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from modules import update_manager


# Legal on NTFS, and each one breaks batch a different way if mishandled.
HOSTILE_NAMES = [
    "space dir",
    "bang!dir",
    "amp&dir",
    "paren(x)dir",
    "caret^dir",
    "pct%dir",
    "Jos\u00e9",          # Latin-1, the common non-ASCII user name case
    "\u4e2d\u6587",        # outside any single-byte OEM code page
    "\u0418\u0432\u0430\u043d",
]

PLACEHOLDERS = ("__APP_DIR__", "__APP_EXE__", "__ZIP_PATH__", "__INSTALLER__",
                "__EXTRACT_DIR__", "__RESTORE_DIR__", "__BACKUP_DIR__", "__BACKUP_ZIP__", "__TARGET_PID__")


def _dead_pid() -> int:
    """A PID that is almost certainly not running, so the wait loop exits at once."""
    return 999999


@unittest.skipUnless(os.name == "nt", "generated launchers are Windows-only")
class TestGeneratedBatIsAsciiForHostilePaths(unittest.TestCase):
    """Every generator must emit a pure-ASCII, fully substituted script."""

    def _assert_bat_is_clean(self, bat_path: Path, label: str) -> None:
        raw = bat_path.read_bytes()
        self.assertTrue(
            raw.isascii(),
            f"{label}: .bat is not pure ASCII; cmd reads batch files in the OEM "
            f"code page, so non-ASCII here corrupts every path in the script",
        )
        text = raw.decode("ascii")
        for placeholder in PLACEHOLDERS:
            self.assertNotIn(placeholder, text, f"{label}: unsubstituted {placeholder}")
        self.assertNotIn(
            "enabledelayedexpansion", text,
            f"{label}: delayed expansion silently eats any '!' in a substituted path",
        )
        self.assertEqual(
            raw.count(b"\r\r\n"), 0,
            f"{label}: doubled CR; the template already carries CRLF so the writer "
            f"must not translate newlines again",
        )
        self.assertGreater(raw.count(b"\r\n"), 10, f"{label}: expected CRLF line endings")

    def test_all_generators_survive_hostile_app_dirs(self) -> None:
        for name in HOSTILE_NAMES:
            with self.subTest(directory=name):
                with tempfile.TemporaryDirectory() as tmp:
                    app_dir = Path(tmp) / name / "KeyQuest"
                    app_dir.mkdir(parents=True)
                    exe = app_dir / "KeyQuest.exe"
                    exe.write_bytes(b"stub")
                    staging = Path(tmp) / name / "staging"
                    staging.mkdir(parents=True)
                    zip_path = staging / "update.zip"
                    zip_path.write_bytes(b"stub")
                    backup_zip = staging / "backup.zip"
                    backup_zip.write_bytes(b"stub")
                    installer = staging / "Setup.exe"
                    installer.write_bytes(b"stub")

                    self._assert_bat_is_clean(
                        update_manager.create_portable_update_launcher(
                            zip_path=zip_path, app_dir=str(app_dir),
                            app_exe_path=str(exe), current_pid=_dead_pid(),
                            script_path=staging / "p.bat", backup_zip_path=backup_zip,
                        ), f"portable/{name}")
                    self._assert_bat_is_clean(
                        update_manager.create_portable_fallback_bat(
                            zip_path=zip_path, app_dir=str(app_dir),
                            app_exe_path=str(exe), current_pid=_dead_pid(),
                            bat_path=staging / "pf.bat", backup_zip_path=backup_zip,
                        ), f"portable_fallback/{name}")
                    self._assert_bat_is_clean(
                        update_manager.create_update_launcher(
                            installer_path=installer, app_dir=str(app_dir),
                            app_exe_path=str(exe), current_pid=_dead_pid(),
                            script_path=staging / "i.bat",
                        ), f"installer/{name}")
                    self._assert_bat_is_clean(
                        update_manager.create_installer_fallback_bat(
                            installer_path=installer, app_dir=str(app_dir),
                            app_exe_path=str(exe), bat_path=staging / "if.bat",
                        ), f"installer_fallback/{name}")


@unittest.skipUnless(os.name == "nt", "generated launchers are Windows-only")
class TestPortableLauncherRunsFromHostilePath(unittest.TestCase):
    """Actually execute the portable launcher from an awkward directory."""

    @classmethod
    def setUpClass(cls) -> None:
        # A small, real executable to stand in for KeyQuest.exe, so the
        # launcher's restart line has something valid to start.  A stub file
        # with an .exe suffix would raise a blocking "not a valid Win32
        # application" dialog and hang the test.
        cls.stub_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "where.exe"
        if not cls.stub_exe.exists():
            raise unittest.SkipTest("no stand-in executable available")

    def _run_case(self, dir_name: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / dir_name
            app_dir = base / "KeyQuest"
            (app_dir / "modules").mkdir(parents=True)
            (app_dir / "modules" / "version.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
            (app_dir / "carried_over.txt").write_text("keep", encoding="utf-8")
            shutil.copy2(self.stub_exe, app_dir / "KeyQuest.exe")

            staging = base / "staging"
            staging.mkdir(parents=True)
            payload = staging / "payload" / "KeyQuest"
            (payload / "modules").mkdir(parents=True)
            (payload / "modules" / "version.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
            (payload / "brand_new.txt").write_text("new", encoding="utf-8")
            shutil.copy2(self.stub_exe, payload / "KeyQuest.exe")

            zip_path = staging / "update.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for item in payload.rglob("*"):
                    if item.is_file():
                        zf.write(item, item.relative_to(payload.parent))

            bat = update_manager.create_portable_update_launcher(
                zip_path=zip_path,
                app_dir=str(app_dir),
                app_exe_path=str(app_dir / "KeyQuest.exe"),
                current_pid=_dead_pid(),
                script_path=staging / "run_update.bat",
            )

            env = dict(os.environ)
            # Extract with this interpreter rather than depending on bsdtar, and
            # skip the exe swap: the point here is that the *paths* resolve.
            env["KEYQUEST_UPDATER_TEST_PYTHON"] = sys.executable
            env["KEYQUEST_UPDATER_SKIP_EXE_COPY"] = "1"

            completed = subprocess.run(
                update_manager.quote_bat_command(bat),
                env=env, capture_output=True, timeout=180,
            )

            version_text = (app_dir / "modules" / "version.py").read_text(encoding="utf-8")
            log = app_dir / "keyquest_error.log"
            detail = log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no log written)"
            self.assertIn(
                '2.0.0', version_text,
                f"update did not apply under {dir_name!r} (exit {completed.returncode}).\nLog:\n{detail}",
            )
            self.assertTrue(
                (app_dir / "brand_new.txt").exists(),
                f"new file missing under {dir_name!r}.\nLog:\n{detail}",
            )
            self.assertFalse(
                (app_dir / "carried_over.txt").exists(),
                f"/MIR should have removed a file absent from the payload under {dir_name!r}",
            )

    def test_runs_from_directory_with_spaces_and_specials(self) -> None:
        self._run_case("a dir & (x)")

    def test_runs_from_non_ascii_directory(self) -> None:
        self._run_case("Jos\u00e9 \u4e2d\u6587")


if __name__ == "__main__":
    unittest.main()
