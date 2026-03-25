"""App-level update orchestration extracted from KeyQuestApp."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from modules import update_manager
from modules.app_paths import get_app_dir
from modules.version import __version__


if TYPE_CHECKING:
    from modules.keyquest_app import KeyQuestApp


UPDATE_PERIODIC_INTERVAL_S = 4 * 3600
UPDATE_IDLE_INSTALL_S = 30 * 60


class AppUpdateController:
    """Own the background update workflow for the running app."""

    def __init__(self, app: "KeyQuestApp") -> None:
        self.app = app
        self._update_lock = threading.Lock()
        self._update_check_thread = None
        self._update_check_result = None
        self._update_download_thread = None
        self._update_download_result = None
        self._pending_update_release = None
        self._pending_update_manual = False
        self._update_status = "Ready to check for updates."
        self._update_downloaded_bytes = 0
        self._update_total_bytes = 0
        self._update_error_message = ""
        self._last_user_activity: float = time.monotonic()
        self._update_periodic_last_check: float = time.monotonic()
        self._self_update_supported = update_manager.can_self_update()
        self._portable_update_mode = (
            self._self_update_supported and update_manager.is_portable_layout(get_app_dir())
        )

    @property
    def self_update_supported(self) -> bool:
        return self._self_update_supported

    @property
    def portable_update_mode(self) -> bool:
        return self._portable_update_mode

    @property
    def update_status(self) -> str:
        return self._update_status

    @property
    def update_downloaded_bytes(self) -> int:
        return self._update_downloaded_bytes

    @property
    def update_total_bytes(self) -> int:
        return self._update_total_bytes

    def mark_user_activity(self) -> None:
        self._last_user_activity = time.monotonic()

    def start_startup_update_check_if_enabled(self) -> None:
        """Start a background update check when installed and enabled."""
        if not self._self_update_supported:
            return
        if not self.app.state.settings.auto_update_check:
            return
        self.start_update_check(manual=False)

    def start_update_check(self, manual: bool) -> None:
        """Start a GitHub release check in the background."""
        if not self._self_update_supported:
            if manual:
                self.app.speech.say(
                    "Automatic updating is only available in the installed Windows app.",
                    priority=True,
                )
            return

        if self.app.state.mode == "UPDATING":
            if manual:
                self.app.speech.say(self._update_status, priority=True)
            return

        if self._update_check_thread and self._update_check_thread.is_alive():
            if manual:
                self.app.speech.say("Already checking for updates.", priority=True)
            return

        self._update_error_message = ""
        self._update_status = "Checking GitHub for updates."
        self.app._record_update_event(
            f"Starting update check from version {__version__}. "
            f"Manual check: {'yes' if manual else 'no'}."
        )
        self._update_check_thread = threading.Thread(
            target=self._check_for_updates_worker,
            args=(manual,),
            daemon=True,
        )
        self._update_periodic_last_check = time.monotonic()
        self._update_check_thread.start()
        if manual:
            self.app.speech.say("Checking for updates.", priority=True)

    def _check_for_updates_worker(self, manual: bool) -> None:
        """Worker that queries the latest GitHub release."""
        try:
            outcome = update_manager.check_for_update(
                current_version=__version__,
                portable=self._portable_update_mode,
                url=update_manager.get_configured_release_url(),
            )
            if isinstance(outcome, update_manager.UpdateUpToDate):
                result = {"status": "up_to_date", "manual": manual}
            else:
                result = {
                    "status": "update_available",
                    "manual": manual,
                    "version": outcome.version,
                    "release": outcome.release,
                    "asset": outcome.asset,
                    "asset_kind": "portable zip" if self._portable_update_mode else "installer",
                }
        except update_manager.UpdateNoAssetError as e:
            result = {
                "status": "missing_asset",
                "manual": manual,
                "version": e.version,
                "asset_kind": e.kind or ("portable zip" if self._portable_update_mode else "installer"),
            }
        except update_manager.UpdateHttpError as e:
            message = f"GitHub returned HTTP {e.status_code}." if e.status_code else str(e)
            result = {"status": "error", "manual": manual, "message": message, "traceback": traceback.format_exc()}
        except update_manager.UpdateInvalidResponseError as e:
            result = {
                "status": "error",
                "manual": manual,
                "message": f"Unexpected response from GitHub: {e}",
                "traceback": traceback.format_exc(),
            }
        except update_manager.UpdateNetworkError as e:
            message = str(e)
            if "certificate verify failed" in message.lower():
                message = (
                    "Secure connection to GitHub could not be verified. "
                    "Check your Windows date and time, antivirus web filtering, or network certificate settings."
                )
            result = {"status": "error", "manual": manual, "message": message, "traceback": traceback.format_exc()}
        except Exception as e:
            result = {
                "status": "error",
                "manual": manual,
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

        with self._update_lock:
            self._update_check_result = result

    def _begin_pending_update_if_ready(self) -> None:
        """Start a deferred update once the user is at the main menu and idle long enough."""
        if self.app.state.mode != "MENU":
            return
        if not self._pending_update_release:
            return
        if time.monotonic() - self._last_user_activity < UPDATE_IDLE_INSTALL_S:
            return

        payload = self._pending_update_release
        self._pending_update_release = None
        self.app._record_update_event(
            f"User idle {UPDATE_IDLE_INSTALL_S // 60} min. "
            f"Resuming deferred update for version {payload.get('version', 'unknown')}."
        )
        self._begin_update_download(payload)

    def begin_pending_update_if_ready(self) -> None:
        """Public entry point used when the app returns to the main menu."""
        self._begin_pending_update_if_ready()

    def _begin_update_download(self, payload: dict) -> None:
        """Start downloading a discovered installer update."""
        if self.app.state.mode == "UPDATING":
            return

        version = payload["version"]
        asset = payload["asset"]
        download_url = str(asset.get("browser_download_url") or "")
        self.app.state.mode = "UPDATING"
        self._update_downloaded_bytes = 0
        self._update_total_bytes = int(asset.get("size", 0) or 0)
        self._update_status = (
            f"Update available: KeyQuest {version}. Downloading and installing now. "
            "Keyboard and mouse input are disabled in KeyQuest during the update."
        )
        self.app.speech.say(
            f"Update available. Downloading and installing KeyQuest version {version} now. "
            "KeyQuest input is disabled during the update.",
            priority=True,
            protect_seconds=3.5,
        )
        self.app._record_update_event(
            f"Starting update download for version {version}. "
            f"Asset: {asset.get('name', 'unknown')}. URL: {download_url or 'missing'}."
        )

        self._update_download_thread = threading.Thread(
            target=self._download_update_worker,
            args=(payload,),
            daemon=True,
        )
        self._update_download_thread.start()

    def _download_update_worker(self, payload: dict) -> None:
        """Worker that downloads the update installer."""
        try:
            version = payload["version"]
            asset = payload["asset"]
            release = payload.get("release", {})
            asset_name = str(asset.get("name") or "")
            download_url = asset.get("browser_download_url")
            if not download_url:
                raise RuntimeError("Release installer did not include a download URL.")

            destination = (
                update_manager.get_updates_dir() / update_manager.build_portable_zip_filename(version)
                if self._portable_update_mode
                else update_manager.get_updates_dir() / update_manager.build_installer_filename(version)
            )

            def _progress(downloaded: int, total: int) -> None:
                with self._update_lock:
                    self._update_downloaded_bytes = downloaded
                    self._update_total_bytes = total
                    if total > 0:
                        percent = int((downloaded / total) * 100)
                        self._update_status = f"Downloading update: {percent}% complete."
                    else:
                        self._update_status = f"Downloading update: {downloaded // 1024} KB received."

            installer_path = update_manager.download_file(
                download_url,
                destination,
                progress_callback=_progress,
            )

            sha256_asset = update_manager.select_sha256_asset(release, asset_name)
            if sha256_asset:
                self.app._record_update_event("Verifying download integrity via SHA-256.")
                expected_hash = update_manager.fetch_sha256_for_asset(sha256_asset)
                if expected_hash:
                    if not update_manager.verify_file_sha256(installer_path, expected_hash):
                        raise RuntimeError(
                            "Downloaded file did not match the expected SHA-256 hash. "
                            "The file may be corrupted. Please try again."
                        )
                    self.app._record_update_event("SHA-256 verification passed.")
                else:
                    self.app._record_update_event(
                        "SHA-256 sidecar asset found but could not be fetched. Skipping hash check."
                    )
            else:
                self.app._record_update_event("No SHA-256 sidecar asset in this release. Skipping hash check.")

            result = {"status": "downloaded", "version": version, "download_path": str(installer_path)}
        except Exception as e:
            result = {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

        with self._update_lock:
            self._update_download_result = result

    def poll_update_work(self) -> None:
        """Process any completed update background work on the main thread."""
        check_result = None
        download_result = None
        with self._update_lock:
            if self._update_check_result is not None:
                check_result = self._update_check_result
                self._update_check_result = None
            if self._update_download_result is not None:
                download_result = self._update_download_result
                self._update_download_result = None

        if check_result is not None:
            self._handle_update_check_result(check_result)
        if download_result is not None:
            self._handle_update_download_result(download_result)

        now = time.monotonic()
        if (
            self._self_update_supported
            and self.app.state.mode != "UPDATING"
            and not (self._update_check_thread and self._update_check_thread.is_alive())
            and not (self._update_download_thread and self._update_download_thread.is_alive())
            and now - self._update_periodic_last_check >= UPDATE_PERIODIC_INTERVAL_S
        ):
            self.start_update_check(manual=False)

        if self._pending_update_release:
            self._begin_pending_update_if_ready()

    def maybe_check_from_main_menu(self, recheck_min_s: int) -> None:
        """Kick off a background re-check after returning to the main menu."""
        if (
            self._self_update_supported
            and time.monotonic() - self._update_periodic_last_check >= recheck_min_s
            and not (self._update_check_thread and self._update_check_thread.is_alive())
            and self.app.state.mode != "UPDATING"
        ):
            self.start_update_check(manual=False)

    def _handle_update_check_result(self, result: dict) -> None:
        """Handle update-check completion."""
        status = result.get("status")
        manual = bool(result.get("manual"))

        if status == "up_to_date":
            self._update_status = "KeyQuest is up to date."
            self.app._record_update_event(
                f"Update check completed. No newer release was found than {__version__}."
            )
            if manual:
                self.app.speech.say("KeyQuest is up to date.", priority=True)
            return

        if status == "missing_asset":
            asset_kind = result.get("asset_kind", "update file")
            self._update_status = f"An update was found, but no {asset_kind} asset was attached to the release."
            self.app._record_update_event(
                f"Update check found version {result.get('version', 'unknown')}, "
                f"but no {asset_kind} asset was attached to the release."
            )
            if manual:
                self.app.speech.say(
                    f"An update was found, but the release does not include the expected {asset_kind} yet.",
                    priority=True,
                )
            return

        if status == "error":
            self._update_error_message = result.get("message", "Unknown update error.")
            self._update_status = "Update check failed."
            self.app.state.mode = "MENU"
            if manual:
                self.app.speech.say(f"Update check failed. {self._update_error_message}", priority=True)
            else:
                self.app.speech.say("Update check failed.", priority=True)
            self.app._offer_update_failure_recovery(
                self._update_error_message,
                tb_str=result.get("traceback", ""),
            )
            return

        if status != "update_available":
            return

        self.app._record_update_event(
            f"Update available: current version {__version__}, new version {result.get('version', 'unknown')}."
        )
        idle_s = time.monotonic() - self._last_user_activity
        if self.app.state.mode == "MENU" and idle_s >= UPDATE_IDLE_INSTALL_S:
            self._begin_update_download(result)
            return

        self.app._record_update_event(
            f"Update to version {result.get('version', 'unknown')} deferred "
            f"(mode={self.app.state.mode}, idle={int(idle_s)}s). "
            "Will install when at main menu and idle."
        )
        self._pending_update_release = result
        self._pending_update_manual = manual

    def _handle_update_download_result(self, result: dict) -> None:
        """Handle update download completion."""
        status = result.get("status")
        if status == "error":
            self._update_error_message = result.get("message", "Unknown update download error.")
            self._update_status = "Update download failed."
            self.app.state.mode = "MENU"
            self.app.speech.say(f"Update download failed. {self._update_error_message}", priority=True)
            self.app._offer_update_failure_recovery(
                self._update_error_message,
                tb_str=result.get("traceback", ""),
            )
            self.app.main_menu.announce_current()
            return

        if status == "downloaded":
            self.app._record_update_event(
                f"Update download finished for version {result.get('version', 'unknown')}. "
                f"Staged file: {result.get('download_path', '')}"
            )
            self._launch_downloaded_update(result["download_path"], result["version"])

    def _launch_downloaded_update(self, download_path: str, version: str) -> None:
        """Launch the correct update handoff and then exit the app."""
        app_exe_path = (
            sys.executable if getattr(sys, "frozen", False) else os.path.join(get_app_dir(), "KeyQuest.exe")
        )
        if self._portable_update_mode:
            launcher_path = update_manager.create_portable_update_launcher(
                zip_path=Path(download_path),
                app_dir=get_app_dir(),
                app_exe_path=app_exe_path,
                current_pid=os.getpid(),
            )
        else:
            launcher_path = update_manager.create_update_launcher(
                installer_path=Path(download_path),
                app_dir=get_app_dir(),
                app_exe_path=app_exe_path,
                current_pid=os.getpid(),
            )

        self.app._record_update_event(
            f"Prepared update launcher for version {version}. "
            f"Downloaded file: {download_path}. Launcher: {launcher_path}."
        )

        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            subprocess.Popen(
                ["cmd", "/c", str(launcher_path)],
                creationflags=creationflags,
                close_fds=True,
                startupinfo=startupinfo,
            )
        except Exception as e:
            self.app.state.mode = "MENU"
            self._update_status = "Unable to launch the updater."
            self.app.speech.say(f"Unable to launch the update helper. {e}", priority=True)
            self.app._record_update_error(
                f"Unable to launch the update helper for version {version}. {e}",
                tb_str=traceback.format_exc(),
            )
            self.app.main_menu.announce_current()
            return

        action_text = "Installing" if not self._portable_update_mode else "Applying portable update for"
        fallback_note = (
            f"If KeyQuest does not restart automatically, "
            f"download the latest installer from {update_manager.INSTALLER_DOWNLOAD_URL}"
        )
        self._update_status = (
            f"{action_text} KeyQuest {version}. KeyQuest will restart automatically. "
            f"If it does not restart, download the installer from the GitHub releases page."
        )
        self.app._record_update_event(
            f"Update helper launched for version {version}. "
            "KeyQuest will now exit and wait for the launcher to install and restart the app."
        )
        self.app.save_progress()
        self.app.speech.say(
            f"{action_text} KeyQuest version {version}. KeyQuest will restart automatically. "
            "If KeyQuest does not restart, please download the latest installer from the website.",
            priority=True,
            protect_seconds=3.5,
        )
        pygame.time.wait(750)
        pygame.quit()
        sys.exit(0)
