"""Regression guards for the updater reliability fixes.

Each test here pins a specific failure that was found by review and confirmed in
the source.  The comments say what breaks if the assertion stops holding, so a
future edit that reintroduces the bug fails with an explanation rather than a
bare assertion error.
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


def _portable_bat(tmpdir: Path, *, with_backup: bool = True) -> str:
    zip_path = tmpdir / "update.zip"
    zip_path.write_bytes(b"stub")
    backup = tmpdir / "backup.zip"
    backup.write_bytes(b"stub")
    return update_manager.create_portable_update_launcher(
        zip_path=zip_path,
        app_dir=r"C:\App\KeyQuest",
        app_exe_path=r"C:\App\KeyQuest\KeyQuest.exe",
        current_pid=4242,
        script_path=tmpdir / "p.bat",
        backup_zip_path=backup if with_backup else None,
    ).read_text(encoding="ascii")


def _portable_fallback_bat(tmpdir: Path) -> str:
    zip_path = tmpdir / "update.zip"
    zip_path.write_bytes(b"stub")
    backup = tmpdir / "backup.zip"
    backup.write_bytes(b"stub")
    return update_manager.create_portable_fallback_bat(
        zip_path=zip_path,
        app_dir=r"C:\App\KeyQuest",
        app_exe_path=r"C:\App\KeyQuest\KeyQuest.exe",
        current_pid=4242,
        bat_path=tmpdir / "pf.bat",
        backup_zip_path=backup,
    ).read_text(encoding="ascii")


def _installer_bat(tmpdir: Path) -> str:
    installer = tmpdir / "Setup.exe"
    installer.write_bytes(b"stub")
    return update_manager.create_update_launcher(
        installer_path=installer,
        app_dir=r"C:\App\KeyQuest",
        app_exe_path=r"C:\App\KeyQuest\KeyQuest.exe",
        current_pid=4242,
        script_path=tmpdir / "i.bat",
    ).read_text(encoding="ascii")


def _installer_fallback_bat(tmpdir: Path) -> str:
    installer = tmpdir / "Setup.exe"
    installer.write_bytes(b"stub")
    return update_manager.create_installer_fallback_bat(
        installer_path=installer,
        app_dir=r"C:\App\KeyQuest",
        app_exe_path=r"C:\App\KeyQuest\KeyQuest.exe",
        bat_path=tmpdir / "if.bat",
    ).read_text(encoding="ascii")


class TestSentenceRestoreDirection(unittest.TestCase):
    """/XN skipped exactly the files the user had just edited."""

    def test_installer_restore_keeps_newer_user_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _installer_bat(Path(tmp))
        self.assertIn("/E /XO", content)
        self.assertNotIn(
            "/XN", content,
            "The .iss copies with ignoreversion, so this restore is the only thing "
            "preserving user sentence edits. /XN excludes source files NEWER than the "
            "destination, i.e. precisely the files the user just edited.",
        )

    def test_portable_sentence_merge_keeps_newer_user_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _portable_bat(Path(tmp))
        self.assertNotIn("/XN", content)
        self.assertIn("/E /XO", content)


class TestRollbackHonesty(unittest.TestCase):
    """Rollback used to log success whenever version.py merely existed."""

    def _assert_checks_tar_exit(self, content: str, label: str) -> None:
        self.assertIn(
            'set "kqTarExit=%errorlevel%"', content,
            f"{label}: rollback must capture tar's exit status",
        )
        self.assertIn(
            "if %kqTarExit% neq 0 goto restoreretry", content,
            f"{label}: a failed tar must retry, not fall through to the success log. "
            f"After a partial /MIR the app tree usually still contains a version.py, "
            f"so existence alone declared a completely failed restore 'restored'.",
        )
        self.assertIn("ROLLBACK FAILED", content, f"{label}: exhausted retries must say so")

    def test_primary_launcher_checks_tar_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_checks_tar_exit(_portable_bat(Path(tmp)), "primary")

    def test_fallback_launcher_checks_tar_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_checks_tar_exit(_portable_fallback_bat(Path(tmp)), "fallback")

    def test_missing_snapshot_is_announced_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _portable_bat(Path(tmp), with_backup=False)
        self.assertIn("ROLLBACK UNAVAILABLE", content)

    def test_backup_path_is_quoted_in_log_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _portable_bat(Path(tmp))
        for line in content.splitlines():
            if "%kqBackupZip%" in line and line.strip().startswith("echo"):
                self.assertIn(
                    '"%kqBackupZip%"', line,
                    "Unquoted, a ')' in the path closes the enclosing if-block and cmd "
                    "aborts the script at parse time, skipping the restart entirely.",
                )


class TestPortableFallbackAppliesSafely(unittest.TestCase):
    """The fallback used to mirror blind and ignore the exe copy result."""

    def test_verifies_payload_before_destructive_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _portable_fallback_bat(Path(tmp))
        exe_check = content.index('if not exist "%kqExtract%\\KeyQuest\\KeyQuest.exe"')
        mirror = content.index("/MIR")
        self.assertLess(
            exe_check, mirror,
            "The payload must be validated BEFORE /MIR overwrites the live install; "
            "otherwise a zip with no usable exe still destroys the existing tree.",
        )

    def test_exe_copy_is_retried_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _portable_fallback_bat(Path(tmp))
        self.assertIn(":copyexe", content)
        self.assertIn("if %kqWait% geq 15", content)
        self.assertIn(
            "KeyQuest.exe replacement failed after 15 retries", content,
            "A briefly locked exe (AV scan) used to leave the OLD exe running against "
            "the NEW file tree, with the script still exiting 0.",
        )


class TestInstallerFallbackKeepsInstallerOnFailure(unittest.TestCase):
    def test_installer_only_deleted_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _installer_fallback_bat(Path(tmp))
        self.assertIn("if %kqInstallExit% equ 0 (", content)
        self.assertIn(
            "kept at", content,
            "This is the last-resort path: the recovery message tells the user to run "
            "that installer by hand, so deleting it on failure removed the very file "
            "the instructions point at.",
        )


class TestPathSafetyHelpers(unittest.TestCase):
    def test_percent_is_escaped_for_batch(self) -> None:
        # % is expanded while the line is parsed, before quoting applies, so it
        # is the one hostile character quoting cannot save.
        self.assertEqual(update_manager.bat_value(r"C:\100%\App"), r"C:\100%%\App")

    def test_command_quoting_survives_ampersands(self) -> None:
        cmd = update_manager.quote_bat_command(r"C:\a&b\run.bat")
        self.assertIn('""C:\\a&b\\run.bat""', cmd)
        self.assertIn("/s", cmd)

    def test_marker_write_reports_failure(self) -> None:
        # A silent False was indistinguishable from success, so a blocked write
        # left a later swap failure with no marker and no announcement.
        self.assertFalse(
            update_manager.write_pending_update_marker(
                str(Path(tempfile.gettempdir()) / "kq-does-not-exist-xyz"), "9.9.9"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(update_manager.write_pending_update_marker(tmp, "9.9.9"))


class TestNoDelayedExpansion(unittest.TestCase):
    def test_no_template_enables_delayed_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for label, content in (
                ("portable", _portable_bat(tmpdir)),
                ("portable_fallback", _portable_fallback_bat(tmpdir)),
                ("installer", _installer_bat(tmpdir)),
                ("installer_fallback", _installer_fallback_bat(tmpdir)),
            ):
                with self.subTest(template=label):
                    self.assertNotIn(
                        "enabledelayedexpansion", content,
                        "Delayed expansion was enabled only for a wait counter, but it "
                        "silently eats any '!' in a substituted path, including the "
                        "restart path.",
                    )


@unittest.skipUnless(os.name == "nt", "generated launchers are Windows-only")
class TestRollbackRetryPathActuallyRuns(unittest.TestCase):
    """Execute the restore-retry path, which string assertions cannot cover.

    This exists because a regression slipped through every other check: the
    "ROLLBACK FAILED" echo contained parentheses while sitting inside an
    ``if ... ( )`` block.  cmd parses a parenthesized block the moment execution
    reaches the ``if``, so the unescaped ``)`` terminated the block early and the
    whole script died with ". was unexpected at this time." and exit 255 the
    first time any restore attempt failed -- no retries, no log line, and no
    restart, which is exactly the stranding the rollback exists to prevent.

    Nothing caught it: the string tests only assert "ROLLBACK FAILED" appears in
    the generated text, and neither the hostile-path runtime tests nor the
    21-step integration harness ever fails a restore.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.stub_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "where.exe"
        if not cls.stub_exe.exists():
            raise unittest.SkipTest("no stand-in executable available")

    def test_failed_restore_still_logs_and_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app_dir = base / "KeyQuest"
            (app_dir / "modules").mkdir(parents=True)
            (app_dir / "modules" / "version.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
            shutil.copy2(self.stub_exe, app_dir / "KeyQuest.exe")

            staging = base / "staging"
            staging.mkdir()

            # Payload has an exe (so extraction validation passes) but no
            # modules/version.py, so the post-mirror structure check fails and
            # execution reaches :rollback.
            payload = staging / "payload" / "KeyQuest"
            payload.mkdir(parents=True)
            shutil.copy2(self.stub_exe, payload / "KeyQuest.exe")
            zip_path = staging / "update.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for item in payload.rglob("*"):
                    if item.is_file():
                        zf.write(item, item.relative_to(payload.parent))

            # A corrupt snapshot makes every restore attempt fail, which is what
            # drives execution into the retry block.
            backup_zip = staging / "backup.zip"
            backup_zip.write_bytes(b"this is not a zip archive")

            bat = update_manager.create_portable_update_launcher(
                zip_path=zip_path,
                app_dir=str(app_dir),
                app_exe_path=str(app_dir / "KeyQuest.exe"),
                current_pid=999999,
                script_path=staging / "run_update.bat",
                backup_zip_path=backup_zip,
            )

            env = dict(os.environ)
            env["KEYQUEST_UPDATER_TEST_PYTHON"] = sys.executable
            env["KEYQUEST_UPDATER_SKIP_EXE_COPY"] = "1"
            completed = subprocess.run(
                update_manager.quote_bat_command(bat),
                env=env, capture_output=True, timeout=300,
            )

            stderr = completed.stderr.decode("utf-8", errors="replace")
            self.assertNotIn(
                "was unexpected at this time", stderr,
                "the launcher died at parse time instead of running the rollback path",
            )
            self.assertNotEqual(
                completed.returncode, 255,
                f"exit 255 means a batch parse error aborted the script; stderr: {stderr}",
            )

            log = app_dir / "keyquest_error.log"
            self.assertTrue(log.exists(), "launcher wrote no log at all")
            text = log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("Rolling back", text)
            self.assertIn(
                "ROLLBACK FAILED after 10 attempts", text,
                f"retry cap never reported; the retry block did not run.\nLog:\n{text}",
            )
            self.assertIn(
                "Restarting KeyQuest after rollback", text,
                f"the user was left with nothing running.\nLog:\n{text}",
            )


if __name__ == "__main__":
    unittest.main()
