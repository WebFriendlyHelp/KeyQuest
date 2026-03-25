import hashlib
import ssl
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest import mock

from modules import update_manager


class TestUpdateManager(unittest.TestCase):
    def test_normalize_version_handles_v_prefix(self):
        self.assertEqual(update_manager.normalize_version("v1.2.3"), "1.2.3")

    def test_is_newer_version_compares_numeric_parts(self):
        self.assertTrue(update_manager.is_newer_version("1.0", "1.0.1"))
        self.assertFalse(update_manager.is_newer_version("1.2.0", "1.2"))

    def test_select_installer_asset_prefers_exact_setup_name(self):
        release = {
            "assets": [
                {"name": "something-else.exe", "browser_download_url": "https://example.invalid/other.exe"},
                {"name": "KeyQuestSetup.exe", "browser_download_url": "https://example.invalid/KeyQuestSetup.exe"},
            ]
        }
        asset = update_manager.select_installer_asset(release)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "KeyQuestSetup.exe")

    def test_select_portable_asset_prefers_expected_zip_name(self):
        release = {
            "assets": [
                {"name": "KeyQuest-portable.zip", "browser_download_url": "https://example.invalid/portable.zip"},
                {"name": "KeyQuest-win64.zip", "browser_download_url": "https://example.invalid/KeyQuest-win64.zip"},
            ]
        }
        asset = update_manager.select_portable_asset(release)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "KeyQuest-win64.zip")

    def test_parse_release_version_uses_tag_name(self):
        release = {"tag_name": "v1.4.2"}
        self.assertEqual(update_manager.parse_release_version(release), "1.4.2")

    def test_build_ssl_context_uses_default_store_and_loads_certifi_bundle(self):
        fake_context = mock.Mock()
        fake_certifi = mock.Mock()
        fake_certifi.where.return_value = "C:\\certifi\\cacert.pem"

        with mock.patch("modules.update_manager.ssl.create_default_context", return_value=fake_context):
            with mock.patch.object(update_manager, "certifi", fake_certifi):
                context = update_manager._build_ssl_context()

        self.assertIs(context, fake_context)
        fake_context.load_verify_locations.assert_called_once_with(cafile="C:\\certifi\\cacert.pem")

    def test_fetch_latest_release_falls_back_to_powershell_on_tls_error(self):
        tls_error = URLError(
            ssl.SSLCertVerificationError(
                1,
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
            )
        )
        with mock.patch("modules.update_manager.os.name", "nt"):
            with mock.patch("modules.update_manager.urllib.request.urlopen", side_effect=tls_error):
                with mock.patch(
                    "modules.update_manager._fetch_latest_release_via_powershell",
                    return_value={"tag_name": "v9.9.9"},
                ) as fallback:
                    release = update_manager.fetch_latest_release()

        self.assertEqual(release["tag_name"], "v9.9.9")
        fallback.assert_called_once()

    def test_fetch_latest_release_tries_curl_after_powershell_failure(self):
        with mock.patch(
            "modules.update_manager._fetch_latest_release_via_powershell",
            side_effect=RuntimeError("powershell failed"),
        ) as powershell_fetch:
            with mock.patch(
                "modules.update_manager._fetch_latest_release_via_curl",
                return_value={"tag_name": "v9.9.9"},
            ) as curl_fetch:
                release = update_manager._fetch_latest_release_with_windows_fallbacks()

        self.assertEqual(release["tag_name"], "v9.9.9")
        powershell_fetch.assert_called_once()
        curl_fetch.assert_called_once()

    def test_run_powershell_hides_window_on_windows(self):
        completed = mock.Mock()
        with mock.patch("modules.update_manager.os.name", "nt"):
            with mock.patch("modules.update_manager.subprocess.STARTUPINFO") as startupinfo_cls:
                startupinfo = mock.Mock()
                startupinfo.dwFlags = 0
                startupinfo_cls.return_value = startupinfo
                with mock.patch("modules.update_manager.subprocess.run", return_value=completed) as run_mock:
                    result = update_manager._run_powershell("$true", timeout=15)

        self.assertIs(result, completed)
        startupinfo_cls.assert_called_once()
        self.assertEqual(startupinfo.wShowWindow, 0)
        run_mock.assert_called_once()
        self.assertIs(run_mock.call_args.kwargs["startupinfo"], startupinfo)
        self.assertEqual(
            run_mock.call_args.kwargs["creationflags"],
            getattr(update_manager.subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_run_command_hides_window_on_windows(self):
        completed = mock.Mock()
        with mock.patch("modules.update_manager.os.name", "nt"):
            with mock.patch("modules.update_manager.subprocess.STARTUPINFO") as startupinfo_cls:
                startupinfo = mock.Mock()
                startupinfo.dwFlags = 0
                startupinfo_cls.return_value = startupinfo
                with mock.patch("modules.update_manager.subprocess.run", return_value=completed) as run_mock:
                    result = update_manager._run_command(["curl.exe", "--version"], timeout=15)

        self.assertIs(result, completed)
        startupinfo_cls.assert_called_once()
        self.assertEqual(startupinfo.wShowWindow, 0)
        run_mock.assert_called_once()
        self.assertIs(run_mock.call_args.kwargs["startupinfo"], startupinfo)
        self.assertEqual(
            run_mock.call_args.kwargs["creationflags"],
            getattr(update_manager.subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_download_file_falls_back_to_powershell_on_tls_error(self):
        tls_error = URLError(
            ssl.SSLCertVerificationError(
                1,
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
            )
        )
        progress = mock.Mock()
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "KeyQuestSetup.exe"
            destination.write_bytes(b"fallback")
            with mock.patch("modules.update_manager.os.name", "nt"):
                with mock.patch("modules.update_manager.urllib.request.urlopen", side_effect=tls_error):
                    with mock.patch(
                        "modules.update_manager._download_file_via_powershell",
                        return_value=destination,
                    ) as fallback:
                        path = update_manager.download_file(
                            "https://example.invalid/setup.exe",
                            destination,
                            progress_callback=progress,
                        )

        self.assertEqual(path, destination)
        fallback.assert_called_once()
        progress.assert_called_once_with(8, 8)

    def test_download_file_tries_curl_after_powershell_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "KeyQuestSetup.exe"
            destination.write_bytes(b"fallback")
            with mock.patch(
                "modules.update_manager._download_file_via_powershell",
                side_effect=RuntimeError("powershell failed"),
            ) as powershell_download:
                with mock.patch(
                    "modules.update_manager._download_file_via_curl",
                    return_value=destination,
                ) as curl_download:
                    path = update_manager._download_file_with_windows_fallbacks(
                        "https://example.invalid/setup.exe",
                        destination,
                    )

        self.assertEqual(path, destination)
        powershell_download.assert_called_once()
        curl_download.assert_called_once()

    def test_create_update_launcher_contains_silent_install_and_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = Path(tmpdir) / "KeyQuestSetup_1_2_0.exe"
            script = update_manager.create_update_launcher(
                installer_path=installer,
                app_dir=r"C:\Users\Test\AppData\Local\Programs\KeyQuest",
                app_exe_path=r"C:\Program Files\KeyQuest\KeyQuest.exe",
                current_pid=1234,
                script_path=Path(tmpdir) / "update.cmd",
            )
            content = script.read_text(encoding="utf-8")

        self.assertIn("/VERYSILENT", content)
        self.assertIn("/NOCANCEL", content)
        self.assertIn('/DIR="%APP_DIR%"', content)
        self.assertIn('BACKUP_DIR', content)
        self.assertIn('progress.json', content)
        self.assertIn('Get-Content -LiteralPath $_.FullName', content)
        self.assertIn('Get-Content -LiteralPath $dest', content)
        self.assertIn('Set-Content -LiteralPath $dest -Value $merged', content)
        self.assertNotIn('{{', content)
        self.assertNotIn('}}', content)
        self.assertIn('start "" "%APP_EXE%"', content)
        self.assertIn('if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath \'%APP_EXE%\'"', content)
        self.assertIn('set "TARGET_PID=1234"', content)
        self.assertIn('set "LOG_PATH=%APP_DIR%\\keyquest_error.log"', content)
        self.assertIn("setlocal EnableExtensions EnableDelayedExpansion", content)
        self.assertIn('set "WAIT_SECONDS=0"', content)
        self.assertIn("if !WAIT_SECONDS! GEQ 15 (", content)
        self.assertIn("taskkill /PID %TARGET_PID% /F", content)
        self.assertIn("ping -n 2 127.0.0.1 >nul", content)
        self.assertIn('call :log Starting installer %INSTALLER%.', content)
        self.assertIn('call :log Sentence merge skipped because backup or target folder was missing.', content)
        self.assertIn('call :log Restarting KeyQuest from %APP_EXE%.', content)
        self.assertIn('echo [Updater %DATE% %TIME%] %*', content)

    def test_create_portable_update_launcher_contains_expand_and_robocopy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            portable_zip = Path(tmpdir) / "KeyQuest-win64_1_2_0.zip"
            script = update_manager.create_portable_update_launcher(
                zip_path=portable_zip,
                app_dir=r"C:\Portable\KeyQuest",
                app_exe_path=r"C:\Portable\KeyQuest\KeyQuest.exe",
                current_pid=5678,
                script_path=Path(tmpdir) / "portable-update.cmd",
            )
            content = script.read_text(encoding="utf-8")

        self.assertIn("Expand-Archive", content)
        self.assertIn('tar -xf "%ZIP_PATH%" -C "%EXTRACT_DIR%" >nul 2>&1', content)
        self.assertIn('if exist "%EXTRACT_DIR%\\KeyQuest" goto :extract_done', content)
        self.assertIn('call :log Expand-Archive did not produce the extracted app tree. Trying tar fallback.', content)
        self.assertIn("%EXTRACT_DIR%\\KeyQuest\\Sentences", content)
        self.assertIn('Get-Content -LiteralPath $_.FullName', content)
        self.assertIn('Get-Content -LiteralPath $dest', content)
        self.assertIn('Set-Content -LiteralPath $dest -Value $merged', content)
        self.assertNotIn('{{', content)
        self.assertNotIn('}}', content)
        self.assertIn('start "" "%APP_EXE%"', content)
        self.assertIn('if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath \'%APP_EXE%\'"', content)
        self.assertIn("robocopy", content)
        self.assertIn('set "ROBOCOPY_EXCLUDES=progress.json KeyQuest.exe"', content)
        self.assertIn("/XF %ROBOCOPY_EXCLUDES%", content)
        self.assertIn('call :copy_app_exe', content)
        self.assertIn('copy /Y "%SOURCE_EXE%" "%APP_EXE%" >nul', content)
        self.assertIn('call :log Portable KeyQuest.exe replacement succeeded.', content)
        self.assertIn('set "TARGET_PID=5678"', content)
        self.assertIn('set "LOG_PATH=%APP_DIR%\\keyquest_error.log"', content)
        self.assertIn("setlocal EnableExtensions EnableDelayedExpansion", content)
        self.assertIn('set "WAIT_SECONDS=0"', content)
        self.assertIn("if !WAIT_SECONDS! GEQ 15 (", content)
        self.assertIn("taskkill /PID %TARGET_PID% /F", content)
        self.assertIn("ping -n 2 127.0.0.1 >nul", content)
        self.assertIn('call :log Sentence merge skipped because source or extracted folder was missing.', content)
        self.assertIn('call :log Portable update content prepared. Copying files into %APP_DIR%.', content)
        self.assertIn('call :log Restarting KeyQuest from %APP_EXE%.', content)
        self.assertIn('echo [Updater %DATE% %TIME%] %*', content)
        self.assertEqual(content.count("powershell -NoProfile -ExecutionPolicy Bypass -Command ^"), 1)

    def test_is_portable_layout_detects_extracted_app_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "KeyQuest.exe").write_text("", encoding="utf-8")
            (root / "modules").mkdir()
            (root / "games").mkdir()
            (root / "Sentences").mkdir()

            self.assertTrue(update_manager.is_portable_layout(str(root)))

    def test_is_portable_layout_rejects_installed_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "KeyQuest.exe").write_text("", encoding="utf-8")
            (root / "modules").mkdir()
            (root / "games").mkdir()
            (root / "Sentences").mkdir()
            (root / "unins000.exe").write_text("", encoding="utf-8")

            self.assertTrue(update_manager.is_installed_layout(str(root)))
            self.assertFalse(update_manager.is_portable_layout(str(root)))

    def test_get_configured_release_url_uses_env_override(self):
        with mock.patch.dict(
            "os.environ",
            {update_manager.UPDATE_URL_OVERRIDE_ENV: "http://127.0.0.1:8765/release.json"},
        ):
            self.assertEqual(
                update_manager.get_configured_release_url(),
                "http://127.0.0.1:8765/release.json",
            )


class TestTypedErrors(unittest.TestCase):
    def test_fetch_latest_release_raises_update_http_error_on_http_4xx(self):
        import urllib.error
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        with mock.patch("modules.update_manager.urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(update_manager.UpdateHttpError) as ctx:
                update_manager.fetch_latest_release()
        self.assertEqual(ctx.exception.status_code, 403)

    def test_fetch_latest_release_raises_update_network_error_on_connection_failure(self):
        conn_error = URLError("Connection refused")
        with mock.patch("modules.update_manager.urllib.request.urlopen", side_effect=conn_error):
            with mock.patch("modules.update_manager.os.name", "posix"):
                with self.assertRaises(update_manager.UpdateNetworkError):
                    update_manager.fetch_latest_release()

    def test_fetch_latest_release_raises_update_invalid_response_on_bad_json(self):
        mock_response = mock.Mock()
        mock_response.__enter__ = mock.Mock(return_value=mock_response)
        mock_response.__exit__ = mock.Mock(return_value=False)
        mock_response.read.return_value = b"not valid json {"
        with mock.patch("modules.update_manager.urllib.request.urlopen", return_value=mock_response):
            with self.assertRaises(update_manager.UpdateInvalidResponseError):
                update_manager.fetch_latest_release()

    def test_windows_fallback_raises_update_network_error_when_all_fail(self):
        with mock.patch(
            "modules.update_manager._fetch_latest_release_via_powershell",
            side_effect=RuntimeError("ps failed"),
        ):
            with mock.patch(
                "modules.update_manager._fetch_latest_release_via_curl",
                side_effect=RuntimeError("curl failed"),
            ):
                with self.assertRaises(update_manager.UpdateNetworkError):
                    update_manager._fetch_latest_release_with_windows_fallbacks()

    def test_update_no_asset_error_carries_version_and_kind(self):
        err = update_manager.UpdateNoAssetError("msg", version="2.0.0", kind="installer")
        self.assertEqual(err.version, "2.0.0")
        self.assertEqual(err.kind, "installer")

    def test_update_http_error_carries_status_code(self):
        err = update_manager.UpdateHttpError("msg", status_code=404)
        self.assertEqual(err.status_code, 404)

    def test_update_error_hierarchy(self):
        for cls in (
            update_manager.UpdateNetworkError,
            update_manager.UpdateHttpError,
            update_manager.UpdateInvalidResponseError,
            update_manager.UpdateNoAssetError,
        ):
            self.assertTrue(issubclass(cls, update_manager.UpdateError))


class TestCheckForUpdate(unittest.TestCase):
    def _make_release(self, tag: str, assets: list) -> dict:
        return {"tag_name": tag, "assets": assets}

    def _installer_asset(self, url="https://example.invalid/KeyQuestSetup.exe") -> dict:
        return {"name": "KeyQuestSetup.exe", "browser_download_url": url, "size": 1234}

    def _portable_asset(self, url="https://example.invalid/KeyQuest-win64.zip") -> dict:
        return {"name": "KeyQuest-win64.zip", "browser_download_url": url, "size": 5678}

    def test_returns_up_to_date_when_no_newer_version(self):
        release = self._make_release("v1.0.0", [self._installer_asset()])
        with mock.patch("modules.update_manager.fetch_latest_release", return_value=release):
            result = update_manager.check_for_update("1.0.0", portable=False)
        self.assertIsInstance(result, update_manager.UpdateUpToDate)
        self.assertEqual(result.current_version, "1.0.0")

    def test_returns_update_available_for_installer(self):
        release = self._make_release("v2.0.0", [self._installer_asset()])
        with mock.patch("modules.update_manager.fetch_latest_release", return_value=release):
            result = update_manager.check_for_update("1.0.0", portable=False)
        self.assertIsInstance(result, update_manager.UpdateAvailable)
        self.assertEqual(result.version, "2.0.0")
        self.assertEqual(result.asset_name, "KeyQuestSetup.exe")

    def test_returns_update_available_for_portable(self):
        release = self._make_release("v2.0.0", [self._portable_asset()])
        with mock.patch("modules.update_manager.fetch_latest_release", return_value=release):
            result = update_manager.check_for_update("1.0.0", portable=True)
        self.assertIsInstance(result, update_manager.UpdateAvailable)
        self.assertEqual(result.asset_name, "KeyQuest-win64.zip")

    def test_raises_update_no_asset_error_when_asset_missing(self):
        release = self._make_release("v2.0.0", [])
        with mock.patch("modules.update_manager.fetch_latest_release", return_value=release):
            with self.assertRaises(update_manager.UpdateNoAssetError) as ctx:
                update_manager.check_for_update("1.0.0", portable=False)
        self.assertEqual(ctx.exception.version, "2.0.0")
        self.assertEqual(ctx.exception.kind, "installer")

    def test_propagates_fetch_errors(self):
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=update_manager.UpdateNetworkError("no connection"),
        ):
            with self.assertRaises(update_manager.UpdateNetworkError):
                update_manager.check_for_update("1.0.0", portable=False)

    def test_update_available_carries_full_release_and_asset(self):
        asset = self._installer_asset()
        release = self._make_release("v3.1.0", [asset])
        with mock.patch("modules.update_manager.fetch_latest_release", return_value=release):
            result = update_manager.check_for_update("1.0.0", portable=False)
        self.assertIs(result.release, release)
        self.assertIs(result.asset, asset)
        self.assertEqual(result.asset_size, 1234)


class TestSha256(unittest.TestCase):
    def test_select_sha256_asset_finds_sidecar(self):
        release = {
            "assets": [
                {"name": "KeyQuestSetup.exe", "browser_download_url": "https://example.invalid/setup.exe"},
                {"name": "KeyQuestSetup.exe.sha256", "browser_download_url": "https://example.invalid/setup.exe.sha256"},
            ]
        }
        result = update_manager.select_sha256_asset(release, "KeyQuestSetup.exe")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "KeyQuestSetup.exe.sha256")

    def test_select_sha256_asset_returns_none_when_absent(self):
        release = {
            "assets": [
                {"name": "KeyQuestSetup.exe", "browser_download_url": "https://example.invalid/setup.exe"},
            ]
        }
        self.assertIsNone(update_manager.select_sha256_asset(release, "KeyQuestSetup.exe"))

    def test_select_sha256_asset_is_case_insensitive(self):
        release = {
            "assets": [
                {"name": "KEYQUESTSETUP.EXE.SHA256", "browser_download_url": "https://example.invalid/hash"},
            ]
        }
        result = update_manager.select_sha256_asset(release, "KeyQuestSetup.exe")
        self.assertIsNotNone(result)

    def test_verify_file_sha256_passes_for_correct_hash(self):
        data = b"KeyQuest update payload"
        expected = hashlib.sha256(data).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as f:
            f.write(data)
            path = Path(f.name)
        try:
            self.assertTrue(update_manager.verify_file_sha256(path, expected))
        finally:
            path.unlink(missing_ok=True)

    def test_verify_file_sha256_fails_for_wrong_hash(self):
        data = b"KeyQuest update payload"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as f:
            f.write(data)
            path = Path(f.name)
        try:
            self.assertFalse(update_manager.verify_file_sha256(path, "deadbeef" * 8))
        finally:
            path.unlink(missing_ok=True)

    def test_verify_file_sha256_is_case_insensitive(self):
        data = b"test"
        expected = hashlib.sha256(data).hexdigest().upper()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = Path(f.name)
        try:
            self.assertTrue(update_manager.verify_file_sha256(path, expected))
        finally:
            path.unlink(missing_ok=True)

    def test_fetch_sha256_for_asset_returns_hex_from_bare_format(self):
        hex_hash = "a" * 64
        mock_path = mock.MagicMock(spec=Path)
        mock_path.read_text.return_value = hex_hash
        with mock.patch(
            "modules.update_manager.download_file",
            return_value=mock_path,
        ):
            result = update_manager.fetch_sha256_for_asset(
                {"browser_download_url": "https://example.invalid/setup.exe.sha256"}
            )
        self.assertEqual(result, hex_hash)

    def test_fetch_sha256_for_asset_parses_hash_filename_format(self):
        hex_hash = "b" * 64
        mock_path = mock.MagicMock(spec=Path)
        mock_path.read_text.return_value = f"{hex_hash}  KeyQuestSetup.exe"
        with mock.patch("modules.update_manager.download_file", return_value=mock_path):
            result = update_manager.fetch_sha256_for_asset(
                {"browser_download_url": "https://example.invalid/setup.exe.sha256"}
            )
        self.assertEqual(result, hex_hash)

    def test_fetch_sha256_for_asset_returns_none_on_missing_url(self):
        result = update_manager.fetch_sha256_for_asset({})
        self.assertIsNone(result)

    def test_fetch_sha256_for_asset_returns_none_on_download_failure(self):
        with mock.patch(
            "modules.update_manager.download_file",
            side_effect=RuntimeError("network error"),
        ):
            result = update_manager.fetch_sha256_for_asset(
                {"browser_download_url": "https://example.invalid/setup.exe.sha256"}
            )
        self.assertIsNone(result)


class TestFetchWithRetry(unittest.TestCase):
    """Tests for the _fetch_with_retry helper added around fetch_latest_release."""

    def _good_release(self):
        return {"tag_name": "v2.0.0", "assets": []}

    def test_returns_result_on_first_success(self):
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            return_value=self._good_release(),
        ) as m:
            result = update_manager._fetch_with_retry()
        self.assertEqual(m.call_count, 1)
        self.assertEqual(result["tag_name"], "v2.0.0")

    def test_retries_on_network_error_and_succeeds(self):
        """First call raises UpdateNetworkError; second succeeds."""
        good = self._good_release()
        side_effects = [update_manager.UpdateNetworkError("timeout"), good]
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=side_effects,
        ) as m:
            with mock.patch("modules.update_manager.time.sleep"):
                result = update_manager._fetch_with_retry()
        self.assertEqual(m.call_count, 2)
        self.assertEqual(result["tag_name"], "v2.0.0")

    def test_raises_after_exhausting_all_attempts(self):
        """All attempts raise UpdateNetworkError; the last error propagates."""
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=update_manager.UpdateNetworkError("dead"),
        ) as m:
            with mock.patch("modules.update_manager.time.sleep"):
                with self.assertRaises(update_manager.UpdateNetworkError):
                    update_manager._fetch_with_retry(max_attempts=3)
        self.assertEqual(m.call_count, 3)

    def test_does_not_retry_http_errors(self):
        """UpdateHttpError (e.g. 403) must not be retried — it won't resolve."""
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=update_manager.UpdateHttpError("forbidden", status_code=403),
        ) as m:
            with self.assertRaises(update_manager.UpdateHttpError):
                update_manager._fetch_with_retry()
        self.assertEqual(m.call_count, 1)

    def test_does_not_retry_invalid_response(self):
        """A malformed JSON response is not a transient error; don't retry."""
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=update_manager.UpdateInvalidResponseError("bad json"),
        ) as m:
            with self.assertRaises(update_manager.UpdateInvalidResponseError):
                update_manager._fetch_with_retry()
        self.assertEqual(m.call_count, 1)

    def test_sleep_uses_exponential_backoff(self):
        """Delays should be base_delay * 2**attempt (3 s, 6 s for 3 attempts)."""
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=update_manager.UpdateNetworkError("err"),
        ):
            with mock.patch("modules.update_manager.time.sleep") as sleep_mock:
                with self.assertRaises(update_manager.UpdateNetworkError):
                    update_manager._fetch_with_retry(max_attempts=3, base_delay=3.0)
        sleep_calls = [c.args[0] for c in sleep_mock.call_args_list]
        self.assertEqual(sleep_calls, [3.0, 6.0])

    def test_check_for_update_retries_via_fetch_with_retry(self):
        """check_for_update should benefit from the retry wrapper."""
        good = {"tag_name": "v9.9.9", "assets": [
            {"name": "KeyQuestSetup.exe", "browser_download_url": "https://x/s.exe", "size": 1}
        ]}
        side_effects = [update_manager.UpdateNetworkError("blip"), good]
        with mock.patch(
            "modules.update_manager.fetch_latest_release",
            side_effect=side_effects,
        ):
            with mock.patch("modules.update_manager.time.sleep"):
                result = update_manager.check_for_update("1.0.0", portable=False)
        self.assertIsInstance(result, update_manager.UpdateAvailable)
        self.assertEqual(result.version, "9.9.9")


if __name__ == "__main__":
    unittest.main()
