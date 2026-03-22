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
        self.assertIn('BACKUP_DIR', content)
        self.assertIn('progress.json', content)
        self.assertIn('Get-Content -LiteralPath $_.FullName', content)
        self.assertIn('Get-Content -LiteralPath $dest', content)
        self.assertIn('Set-Content -LiteralPath $dest -Value $merged', content)
        self.assertIn('start "" "%APP_EXE%"', content)
        self.assertIn('set "TARGET_PID=1234"', content)
        self.assertIn('set "LOG_PATH=%APP_DIR%\\keyquest_error.log"', content)
        self.assertIn('call :log Starting installer %INSTALLER%.', content)
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
        self.assertIn("releaseSentences", content)
        self.assertIn('Get-Content -LiteralPath $_.FullName', content)
        self.assertIn('Get-Content -LiteralPath $dest', content)
        self.assertIn('Set-Content -LiteralPath $dest -Value $merged', content)
        self.assertIn("robocopy", content)
        self.assertIn("/XF progress.json", content)
        self.assertIn('set "TARGET_PID=5678"', content)
        self.assertIn('set "LOG_PATH=%APP_DIR%\\keyquest_error.log"', content)
        self.assertIn('call :log Portable update content prepared. Copying files into %APP_DIR%.', content)
        self.assertIn('call :log Restarting KeyQuest from %APP_EXE%.', content)
        self.assertIn('echo [Updater %DATE% %TIME%] %*', content)

    def test_is_portable_layout_detects_extracted_app_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "KeyQuest.exe").write_text("", encoding="utf-8")
            (root / "modules").mkdir()
            (root / "games").mkdir()
            (root / "Sentences").mkdir()

            self.assertTrue(update_manager.is_portable_layout(str(root)))


if __name__ == "__main__":
    unittest.main()
