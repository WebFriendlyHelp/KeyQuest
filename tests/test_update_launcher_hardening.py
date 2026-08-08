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
import unittest.mock
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


class TestSentenceStaging(unittest.TestCase):
    """Sentence content is staged for the app to merge, never merged in batch.

    Timestamp flags cannot decide this.  ``/XN`` (the original bug) skipped
    exactly the files the user had just edited; ``/XO`` (its replacement) still
    loses an edit made in February to a build made in March, because the shipped
    file really is newer.  Only a content comparison against what previously
    shipped can tell an edited file from an untouched one, and batch cannot do
    that without awkward hashing.  So both launchers hand the incoming set to
    ``modules/sentence_merge.py``.
    """

    def _assert_stages_not_merges(self, content: str, label: str) -> None:
        self.assertIn(
            '"%kqApp%\\_sentences_incoming"', content,
            f"{label}: the release's sentence files must be staged for the app",
        )
        self.assertNotIn(
            "/XN", content,
            f"{label}: /XN skips precisely the files the user just edited",
        )
        for excluded in ("_sentences_incoming",):
            self.assertIn(
                excluded, content.split("/XD", 1)[-1],
                f"{label}: the mirror must not purge {excluded}",
            )

    def test_portable_stages_incoming_sentences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_stages_not_merges(_portable_bat(Path(tmp)), "portable")

    def test_installer_stages_incoming_sentences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _installer_bat(Path(tmp))
        self.assertIn('"%kqApp%\\_sentences_incoming"', content)
        self.assertNotIn("/XN", content)
        # Inno overwrote Sentences with the shipped set; the user's folder must
        # come back byte for byte, with no timestamp filter deciding anything.
        self.assertIn(
            'robocopy "%kqBackup%\\Sentences" "%kqApp%\\Sentences" /E /R:2', content,
            "the user's sentence folder must be restored in full, unfiltered",
        )

    def test_no_launcher_decides_sentence_content_by_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for label, content in (
                ("portable", _portable_bat(tmpdir)),
                ("installer", _installer_bat(tmpdir)),
                ("portable_fallback", _portable_fallback_bat(tmpdir)),
            ):
                with self.subTest(template=label):
                    for line in content.splitlines():
                        if "Sentences" in line and "robocopy" in line:
                            self.assertNotIn("/XO", line, f"{label}: {line.strip()}")
                            self.assertNotIn("/XN", line, f"{label}: {line.strip()}")


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


class TestFindIsPinnedToWindows(unittest.TestCase):
    """The PID wait must not use whatever ``find`` happens to be on PATH.

    Git for Windows (and Cygwin/MSYS/busybox) put a GNU ``find.exe`` ahead of
    ``C:\\Windows\\System32\\find.exe``.  GNU find treats the ``" <pid> "``
    argument as a path, fails, and returns non-zero, so the launcher's
    ``if errorlevel 1 goto afterwait`` concluded the app had already exited and
    the wait loop did nothing at all.  The updater then mirrored over a *running*
    install.  Proven in the harness log: the loop reported the process gone after
    ~0.05s, then fought a locked KeyQuest.exe for the next three seconds.  Same
    bug class as the GNU-tar-instead-of-bsdtar one, and the same fix.
    """

    def test_all_wait_loops_pin_find_to_system32(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for label, content in (
                ("portable", _portable_bat(tmpdir)),
                ("portable_fallback", _portable_fallback_bat(tmpdir)),
                ("installer", _installer_bat(tmpdir)),
            ):
                with self.subTest(template=label):
                    self.assertIn("tasklist", content, f"{label}: expected a PID wait")
                    self.assertIn('System32\\find.exe', content, f"{label}: find is not pinned")
                    self.assertIn('| "%kqFind%"', content, f"{label}: wait loop must use the pinned find")
                    self.assertNotIn(
                        '| find "', content,
                        f"{label}: a bare 'find' resolves to GNU find when Git for Windows "
                        f"is installed, which makes the wait loop a no-op",
                    )


class TestUserStateSurvivesTheMirror(unittest.TestCase):
    """Files recording the user's own choices must not be swept by /MIR.

    Nothing asserted this, so dropping one from a single template would have
    passed the suite. sentence_prefs.json records which sentence files the user
    deliberately deleted; losing it silently overrides that choice.
    """

    def test_every_mirror_excludes_the_user_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for label, content in (
                ("portable", _portable_bat(tmpdir)),
                ("portable_fallback", _portable_fallback_bat(tmpdir)),
            ):
                for line in content.splitlines():
                    if "robocopy" not in line or "/MIR" not in line and "%kqRestoreMode%" not in line:
                        continue
                    excluded = line.split("/XF", 1)[1] if "/XF" in line else ""
                    for name in ("progress.json", "pending_update.json", "sentence_prefs.json"):
                        with self.subTest(template=label, excluded=name):
                            self.assertIn(
                                name, excluded,
                                f"{label}: {name} must survive the mirror; it records the "
                                f"user's own data or choices",
                            )


class TestPathSafetyHelpers(unittest.TestCase):
    def test_percent_is_escaped_for_batch(self) -> None:
        # % is expanded while the line is parsed, before quoting applies, so it
        # is the one hostile character quoting cannot save.
        self.assertEqual(update_manager.bat_value(r"C:\100%\App"), r"C:\100%%\App")

    def test_command_quoting_survives_ampersands(self) -> None:
        # subprocess only quotes an argument containing whitespace, so an
        # unquoted "&" in the launcher path used to split the command.
        cmd = update_manager.quote_bat_command(r"C:\a&b\run.bat")
        self.assertIn('""C:\\a&b\\run.bat""', cmd)
        self.assertIn("/s", cmd)

    def test_percent_in_launcher_path_refuses_to_launch(self) -> None:
        # cmd expands %VAR% on its own command line before locating the file,
        # and there is no reliable escape there. Passing just the file name with
        # a working directory does not work either: cmd cannot resolve a quoted
        # relative command name. Refusing is the honest option, because the
        # alternative is launching whatever the expansion points at.
        with self.assertRaises(update_manager.UpdateError):
            update_manager.quote_bat_command(r"C:\%TEMP%\run.bat")

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


@unittest.skipUnless(os.name == "nt", "generated launchers are Windows-only")
class TestRollbackRestoresExactly(unittest.TestCase):
    """A successful rollback must not leave files the new release introduced.

    Rollback used to extract the snapshot on top of the mirrored directory.
    Extraction restores old files but cannot remove new ones, so a rollback
    logged as successful still started the old exe against a tree containing
    modules only the new version shipped.  It now extracts to a staging dir and
    mirrors that back.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.stub_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "where.exe"
        if not cls.stub_exe.exists():
            raise unittest.SkipTest("no stand-in executable available")

    def test_new_only_files_are_removed_by_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app_dir = base / "KeyQuest"
            (app_dir / "modules").mkdir(parents=True)
            (app_dir / "modules" / "version.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
            (app_dir / "original.txt").write_text("original", encoding="utf-8")
            shutil.copy2(self.stub_exe, app_dir / "KeyQuest.exe")

            backup_zip = update_manager.create_app_backup_zip(str(app_dir), "1.0.0")
            self.assertIsNotNone(backup_zip, "could not build the snapshot this test needs")

            staging = base / "staging"
            staging.mkdir()
            # Payload ships a brand-new file and NO modules tree, so the mirror
            # succeeds, the post-mirror structure check fails, and rollback runs
            # with a genuinely valid snapshot.
            payload = staging / "payload" / "KeyQuest"
            payload.mkdir(parents=True)
            (payload / "new_only.dll").write_text("shipped only by the new version", encoding="utf-8")
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
                current_pid=999999,
                script_path=staging / "run_update.bat",
                backup_zip_path=backup_zip,
            )

            env = dict(os.environ)
            env["KEYQUEST_UPDATER_TEST_PYTHON"] = sys.executable
            env["KEYQUEST_UPDATER_SKIP_EXE_COPY"] = "1"
            subprocess.run(
                update_manager.quote_bat_command(bat),
                env=env, capture_output=True, timeout=300,
            )

            log = app_dir / "keyquest_error.log"
            detail = log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no log)"
            self.assertIn("Backup restored", detail, f"rollback did not report success.\nLog:\n{detail}")
            self.assertTrue(
                (app_dir / "modules" / "version.py").exists(),
                f"the snapshot was not restored.\nLog:\n{detail}",
            )
            self.assertIn("1.0.0", (app_dir / "modules" / "version.py").read_text(encoding="utf-8"))
            self.assertTrue((app_dir / "original.txt").exists(), "pre-existing file lost")
            self.assertFalse(
                (app_dir / "new_only.dll").exists(),
                "a file introduced only by the new release survived rollback, so the "
                f"restored install is a mixed old/new tree.\nLog:\n{detail}",
            )


@unittest.skipUnless(os.name == "nt", "generated launchers are Windows-only")
class TestIncompleteSnapshotNeverDeletes(unittest.TestCase):
    """An incomplete snapshot must not become a deletion manifest.

    Making rollback exact (mirror instead of overlay) created this hazard:
    ``create_app_backup_zip`` silently skips a file it cannot read, so mirroring
    that snapshot back would delete the app's copy with no old copy to restore.
    That is strictly worse than the mixed tree the overlay produced.  The
    snapshot therefore carries a completeness marker, and the launcher mirrors
    only when it is present.
    """

    def test_complete_snapshot_is_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "KeyQuest"
            (app / "modules").mkdir(parents=True)
            (app / "modules" / "version.py").write_text("x = 1\n", encoding="utf-8")
            backup = update_manager.create_app_backup_zip(str(app), "1.0.0")
            self.assertIsNotNone(backup)
            with zipfile.ZipFile(backup) as zf:
                self.assertIn(update_manager.SNAPSHOT_COMPLETE_MARKER, zf.namelist())

    def test_snapshot_with_a_skipped_file_is_not_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "KeyQuest"
            (app / "modules").mkdir(parents=True)
            (app / "modules" / "version.py").write_text("x = 1\n", encoding="utf-8")
            (app / "locked.dll").write_text("cannot be read\n", encoding="utf-8")

            real_write = zipfile.ZipFile.write

            def fail_on_locked(self, filename, arcname=None, *args, **kwargs):
                if "locked.dll" in str(filename):
                    raise OSError(13, "Permission denied")
                return real_write(self, filename, arcname, *args, **kwargs)

            with unittest.mock.patch.object(zipfile.ZipFile, "write", fail_on_locked):
                backup = update_manager.create_app_backup_zip(str(app), "1.0.0")

            self.assertIsNotNone(backup, "a partial snapshot is still better than none")
            with zipfile.ZipFile(backup) as zf:
                names = zf.namelist()
            self.assertNotIn("locked.dll", names, "test setup did not actually skip the file")
            self.assertNotIn(
                update_manager.SNAPSHOT_COMPLETE_MARKER, names,
                "an incomplete snapshot must NOT be marked complete, or rollback will "
                "mirror it and delete the file it failed to capture",
            )

    def test_launcher_only_mirrors_a_complete_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for label, content in (
                ("primary", _portable_bat(Path(tmp))),
                ("fallback", _portable_fallback_bat(Path(tmp))),
            ):
                with self.subTest(template=label):
                    self.assertIn('set "kqRestoreMode=/E"', content)
                    self.assertIn(
                        f'if exist "%kqRestore%\\{update_manager.SNAPSHOT_COMPLETE_MARKER}" '
                        'set "kqRestoreMode=/MIR"',
                        content,
                    )
                    self.assertNotIn(
                        '"%kqRestore%" "%kqApp%" /MIR', content,
                        "the restore must not hard-code /MIR; it has to depend on the "
                        "completeness marker",
                    )
                    # Membership, not adjacency: the exclusion list legitimately
                    # grows (sentence_prefs.json joined it), and pinning the
                    # order just breaks on unrelated changes.
                    restore_line = next(
                        line for line in content.splitlines()
                        if "%kqRestore%" in line and "robocopy" in line
                    )
                    excluded = restore_line.split("/XF", 1)[1]
                    self.assertIn(
                        update_manager.SNAPSHOT_COMPLETE_MARKER, excluded,
                        "the marker itself must be excluded from the restore copy",
                    )


if __name__ == "__main__":
    unittest.main()


class TestNoBatVariableIsUsedWithoutBeingSet(unittest.TestCase):
    r"""Every %var% a generated bat reads must be set, or it expands to nothing.

    This is not hypothetical. The installer fallback gained a sentence backup,
    and the generator was given a __BACKUP_DIR__ value, but the template never
    got its `set "kqBackup=..."` line. So %kqBackup% expanded EMPTY: the backup
    copied to "\Sentences" at the drive root, the restore condition never
    matched, and the data-loss protection the template claims to add did nothing
    whatsoever. Nothing caught it, because an unset variable is not a syntax
    error, and the string tests only checked the backup lines were present.
    """

    # Set by the environment or by cmd itself, not by us.
    _EXTERNAL = {
        "SystemRoot", "date", "time", "errorlevel", "TEMP", "TMP",
        "KEYQUEST_UPDATER_TEST_PYTHON", "KEYQUEST_UPDATER_SKIP_EXE_COPY",
    }

    def _unset_variables(self, content: str) -> set:
        import re

        assigned = {m.group(1) for m in re.finditer(r'set\s+"([A-Za-z_]\w*)=', content)}
        used = {m.group(1) for m in re.finditer(r"%([A-Za-z_]\w*)%", content)}
        return used - assigned - self._EXTERNAL

    def test_every_template_sets_what_it_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for label, content in (
                ("portable", _portable_bat(tmpdir)),
                ("portable_fallback", _portable_fallback_bat(tmpdir)),
                ("installer", _installer_bat(tmpdir)),
                ("installer_fallback", _installer_fallback_bat(tmpdir)),
            ):
                with self.subTest(template=label):
                    missing = self._unset_variables(content)
                    self.assertEqual(
                        missing, set(),
                        f"{label}: reads {sorted(missing)} without setting it. An unset "
                        f"variable expands to nothing, so paths silently become wrong "
                        f"instead of failing loudly.",
                    )

    def test_the_installer_fallback_backup_path_is_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = _installer_fallback_bat(Path(tmp))
        self.assertIn('set "kqBackup=', content)
        backup_line = next(
            line for line in content.splitlines() if line.startswith('set "kqBackup=')
        )
        self.assertNotIn(
            'set "kqBackup="', backup_line,
            "an empty backup path sends the user's sentence files to the drive root",
        )
