"""GitHub release updater support for KeyQuest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


GITHUB_OWNER = "WebFriendlyHelp"
GITHUB_REPO = "KeyQuest"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
INSTALLER_DOWNLOAD_URL = f"{GITHUB_REPO_URL}/releases/latest/download/KeyQuestSetup.exe"
UPDATE_URL_OVERRIDE_ENV = "KEYQUEST_UPDATE_RELEASE_URL"
UPDATER_TEST_PYTHON_ENV = "KEYQUEST_UPDATER_TEST_PYTHON"
UPDATER_TEST_SKIP_EXE_COPY_ENV = "KEYQUEST_UPDATER_SKIP_EXE_COPY"
DEFAULT_TIMEOUT_SECONDS = 15
INSTALLER_NAME = "KeyQuestSetup.exe"
PORTABLE_ZIP_NAME = "KeyQuest-win64.zip"

try:
    import certifi
except Exception:
    certifi = None


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class UpdateError(Exception):
    """Base class for all updater errors."""


class UpdateNetworkError(UpdateError):
    """Connection-level failure: DNS, TLS, timeout, etc."""


class UpdateHttpError(UpdateError):
    """Non-success HTTP status code from GitHub."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpdateInvalidResponseError(UpdateError):
    """Response arrived but could not be parsed as expected."""


class UpdateNoAssetError(UpdateError):
    """A newer release was found but no matching download asset was attached."""

    def __init__(self, message: str, version: str = "", kind: str = "") -> None:
        super().__init__(message)
        self.version = version
        self.kind = kind


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class UpdateAvailable:
    """A newer release is available and ready to download."""
    version: str
    download_url: str
    asset_name: str
    asset_size: int
    asset: dict
    release: dict


@dataclass
class UpdateUpToDate:
    """The installed version is current."""
    current_version: str


def can_self_update() -> bool:
    """Return True when the current process can update an installed app."""
    return os.name == "nt" and getattr(sys, "frozen", False)


def get_configured_release_url() -> str:
    """Return the update metadata URL, honoring a local test override."""
    override = os.environ.get(UPDATE_URL_OVERRIDE_ENV, "").strip()
    return override or LATEST_RELEASE_API_URL


def is_installed_layout(app_dir: str) -> bool:
    """Return True when app_dir appears to be an installer-based layout."""
    exe_dir = Path(app_dir)
    if not exe_dir.exists():
        return False
    if (exe_dir / ".keyquest-installed").exists():
        return True
    return any(exe_dir.glob("unins*.exe"))


def is_portable_layout(app_dir: str) -> bool:
    """Return True when the running frozen app appears to be a portable build."""
    exe_dir = Path(app_dir)
    return (
        exe_dir.exists()
        and not is_installed_layout(app_dir)
        and (exe_dir / "KeyQuest.exe").exists()
        and (exe_dir / "modules").exists()
        and (exe_dir / "games").exists()
        and (exe_dir / "Sentences").exists()
    )


def _extract_version_parts(raw: str) -> tuple[int, ...]:
    tokens = re.findall(r"\d+", raw or "")
    if not tokens:
        return (0,)
    return tuple(int(token) for token in tokens)


def normalize_version(raw: str) -> str:
    """Normalize a raw version/tag string to dotted numeric form."""
    parts = _extract_version_parts(raw)
    if not parts:
        return "0"
    return ".".join(str(part) for part in parts)


def is_newer_version(current_version: str, candidate_version: str) -> bool:
    """Return True when candidate_version is newer than current_version."""
    current = _extract_version_parts(current_version)
    candidate = _extract_version_parts(candidate_version)
    width = max(len(current), len(candidate))
    current += (0,) * (width - len(current))
    candidate += (0,) * (width - len(candidate))
    return candidate > current


def parse_release_version(release: dict) -> str:
    """Return the version string to compare from a GitHub release payload."""
    raw = str(release.get("tag_name") or release.get("name") or "").strip()
    return normalize_version(raw)


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context using the OS trust store plus certifi when available."""
    context = ssl.create_default_context()
    if certifi is not None:
        try:
            context.load_verify_locations(cafile=certifi.where())
        except Exception:
            pass
    return context


def _is_tls_verification_error(error: BaseException) -> bool:
    """Return True when the exception looks like a certificate-chain verification failure."""
    message = str(error).lower()
    if "certificate verify failed" in message:
        return True
    if "unable to get local issuer certificate" in message:
        return True
    if isinstance(error, ssl.SSLCertVerificationError):
        return True
    reason = getattr(error, "reason", None)
    return isinstance(reason, ssl.SSLCertVerificationError)


def _run_powershell(script: str, timeout: int) -> subprocess.CompletedProcess:
    """Run a PowerShell script and return the completed process."""
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a helper command without flashing a window on Windows."""
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _fetch_latest_release_via_powershell(
    url: str = LATEST_RELEASE_API_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch release metadata with PowerShell as a Windows-native fallback."""
    script = (
        "$ProgressPreference='SilentlyContinue'; "
        "$headers=@{Accept='application/vnd.github+json'; 'User-Agent'='KeyQuest-Updater'}; "
        f"$response=Invoke-RestMethod -Uri '{url}' -Headers $headers -TimeoutSec {int(timeout)}; "
        "$response | ConvertTo-Json -Depth 100 -Compress"
    )
    result = _run_powershell(script, timeout=max(timeout + 5, 10))
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "PowerShell release fetch failed.")
    return json.loads((result.stdout or "").strip())


def _fetch_latest_release_via_curl(
    url: str = LATEST_RELEASE_API_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch release metadata with curl.exe as a Windows-native fallback."""
    result = _run_command(
        [
            "curl.exe",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
            "--connect-timeout",
            str(int(timeout)),
            "--max-time",
            str(int(timeout) + 5),
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "User-Agent: KeyQuest-Updater",
            url,
        ],
        timeout=max(timeout + 10, 15),
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "curl release fetch failed.")
    return json.loads((result.stdout or "").strip())


def _download_file_via_powershell(
    url: str,
    destination: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    """Download a file with PowerShell as a Windows-native fallback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$ProgressPreference='SilentlyContinue'; "
        f"Invoke-WebRequest -Uri '{url}' -Headers @{{'User-Agent'='KeyQuest-Updater'}} "
        f"-OutFile '{destination}' -TimeoutSec {int(timeout)}"
    )
    result = _run_powershell(script, timeout=max(timeout + 10, 20))
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "PowerShell download failed.")
    return destination


def _download_file_via_curl(
    url: str,
    destination: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    """Download a file with curl.exe as a Windows-native fallback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run_command(
        [
            "curl.exe",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
            "--connect-timeout",
            str(int(timeout)),
            "--max-time",
            str(int(timeout) + 15),
            "-H",
            "User-Agent: KeyQuest-Updater",
            "--output",
            str(destination),
            url,
        ],
        timeout=max(timeout + 20, 25),
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "curl download failed.")
    return destination


def _fetch_latest_release_with_windows_fallbacks(
    url: str = LATEST_RELEASE_API_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Try multiple Windows-native helpers before giving up."""
    errors: list[str] = []
    for helper in (_fetch_latest_release_via_powershell, _fetch_latest_release_via_curl):
        try:
            return helper(url=url, timeout=timeout)
        except Exception as error:
            errors.append(str(error).strip() or helper.__name__)
    raise UpdateNetworkError("Windows update fallback failed. " + " | ".join(errors))


def _download_file_with_windows_fallbacks(
    url: str,
    destination: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    """Try multiple Windows-native download helpers before giving up."""
    errors: list[str] = []
    for helper in (_download_file_via_powershell, _download_file_via_curl):
        try:
            return helper(url, destination, timeout=timeout)
        except Exception as error:
            errors.append(str(error).strip() or helper.__name__)
    raise RuntimeError("Windows download fallback failed. " + " | ".join(errors))


def select_installer_asset(release: dict) -> dict | None:
    """Return the preferred installer asset from a GitHub release."""
    assets = release.get("assets", [])
    exact_match = None
    fallback = None

    for asset in assets:
        name = str(asset.get("name", ""))
        lowered = name.lower()
        if name == INSTALLER_NAME:
            exact_match = asset
            break
        if lowered.endswith(".exe") and "setup" in lowered and fallback is None:
            fallback = asset

    return exact_match or fallback


def select_portable_asset(release: dict) -> dict | None:
    """Return the preferred portable ZIP asset from a GitHub release."""
    assets = release.get("assets", [])
    exact_match = None
    fallback = None

    for asset in assets:
        name = str(asset.get("name", ""))
        lowered = name.lower()
        if name == PORTABLE_ZIP_NAME:
            exact_match = asset
            break
        if lowered.endswith(".zip") and "keyquest" in lowered and fallback is None:
            fallback = asset

    return exact_match or fallback


def fetch_latest_release(url: str = LATEST_RELEASE_API_URL, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Fetch the latest GitHub release metadata.

    Raises UpdateHttpError, UpdateNetworkError, or UpdateInvalidResponseError on failure.
    """
    resolved_url = url or get_configured_release_url()
    request = urllib.request.Request(
        resolved_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "KeyQuest-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_build_ssl_context()) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise UpdateHttpError(f"GitHub returned HTTP {error.code}", status_code=error.code) from error
    except Exception as error:
        if os.name == "nt" and _is_tls_verification_error(error):
            return _fetch_latest_release_with_windows_fallbacks(url=resolved_url, timeout=timeout)
        raise UpdateNetworkError(str(error) or "Network request failed") from error
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as error:
        raise UpdateInvalidResponseError(f"Failed to parse GitHub release JSON: {error}") from error


def get_updates_dir() -> Path:
    """Return the staging directory used for downloaded installers and launcher scripts."""
    base = Path(tempfile.gettempdir()) / "KeyQuestUpdater"
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_pending_update_marker(app_dir: str, expected_version: str) -> None:
    """Write a marker so the next launch can verify the update applied."""
    marker = Path(app_dir) / "pending_update.json"
    try:
        marker.write_text(
            json.dumps({"expected_version": expected_version, "timestamp": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass


def check_pending_update_marker(app_dir: str, current_version: str) -> str | None:
    """Check whether a pending update actually applied.

    Returns ``"success"`` if the current version meets or exceeds the expected
    version, ``"failed"`` if it does not, or ``None`` if no marker was found.
    Always removes the marker file.
    """
    marker = Path(app_dir) / "pending_update.json"
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        expected = str(data.get("expected_version", ""))
        marker.unlink(missing_ok=True)
        if not expected:
            return None
        current_parts = _extract_version_parts(current_version)
        expected_parts = _extract_version_parts(expected)
        if current_parts >= expected_parts:
            return "success"
        return "failed"
    except (OSError, json.JSONDecodeError, ValueError):
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def cleanup_stale_update_files(max_age_days: int = 3) -> None:
    """Remove staged installers, zips, scripts, and leftover dirs from the update staging area."""
    try:
        updates_dir = Path(tempfile.gettempdir()) / "KeyQuestUpdater"
        if not updates_dir.exists():
            return
        cutoff = time.time() - max_age_days * 86400
        for item in updates_dir.iterdir():
            try:
                if item.is_file():
                    if item.suffix.lower() in (".exe", ".zip", ".bat", ".sha256") and item.stat().st_mtime < cutoff:
                        item.unlink(missing_ok=True)
                elif item.is_dir() and item.name in (
                    "installer_backup",
                    "portable_extract",
                    "portable_fallback_extract",
                ):
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


def download_file(url: str, destination: Path, progress_callback=None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Path:
    """Download a file with optional byte progress reporting."""
    request = urllib.request.Request(url, headers={"User-Agent": "KeyQuest-Updater"})
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=_build_ssl_context(),
        ) as response, open(destination, "wb") as handle:
            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else 0
            downloaded = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_bytes)
        if total_bytes > 0 and downloaded != total_bytes:
            raise RuntimeError(
                f"Download truncated: received {downloaded} bytes but expected {total_bytes}. "
                "The connection may have dropped. Please try again."
            )
        return destination
    except Exception as error:
        if os.name == "nt" and _is_tls_verification_error(error):
            downloaded_path = _download_file_with_windows_fallbacks(url, destination, timeout=timeout)
            if progress_callback:
                total_bytes = downloaded_path.stat().st_size if downloaded_path.exists() else 0
                progress_callback(total_bytes, total_bytes)
            return downloaded_path
        raise


def build_installer_filename(version: str) -> str:
    """Return a stable installer filename for a staged update."""
    safe_version = normalize_version(version).replace(".", "_")
    return f"KeyQuestSetup_{safe_version}.exe"


def build_portable_zip_filename(version: str) -> str:
    """Return a stable portable ZIP filename for a staged update."""
    safe_version = normalize_version(version).replace(".", "_")
    return f"KeyQuest-win64_{safe_version}.zip"


_INSTALLER_BAT_TEMPLATE = (
    "@echo off\r\n"
    "setlocal enabledelayedexpansion\r\n"
    "set \"kqPid=__TARGET_PID__\"\r\n"
    "set \"kqInstaller=__INSTALLER__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqBackup=__BACKUP_DIR__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Installer updater started. >> \"%kqLog%\"\r\n"
    "echo [Updater %date% %time%] Waiting for process %kqPid% to exit. >> \"%kqLog%\"\r\n"
    "\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | find \" %kqPid% \" >NUL\r\n"
    "if not errorlevel 1 (\r\n"
    "    set /a kqWaitSec+=1\r\n"
    "    if !kqWaitSec! geq 30 (\r\n"
    "        echo [Updater] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "        taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "        timeout /t 1 /nobreak >NUL\r\n"
    "        goto afterwait\r\n"
    "    )\r\n"
    "    timeout /t 1 /nobreak >NUL\r\n"
    "    goto waitloop\r\n"
    ")\r\n"
    ":afterwait\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Process %kqPid% exited. Backing up user data. >> \"%kqLog%\"\r\n"
    "if exist \"%kqBackup%\" rmdir /s /q \"%kqBackup%\"\r\n"
    "mkdir \"%kqBackup%\"\r\n"
    "if exist \"%kqApp%\\progress.json\" (\r\n"
    "    copy /Y \"%kqApp%\\progress.json\" \"%kqBackup%\\progress.json\" >NUL\r\n"
    ")\r\n"
    "if exist \"%kqApp%\\Sentences\" (\r\n"
    "    robocopy \"%kqApp%\\Sentences\" \"%kqBackup%\\Sentences\" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Running installer. >> \"%kqLog%\"\r\n"
    "\"%kqInstaller%\" /CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS \"/DIR=%kqApp%\"\r\n"
    "set \"kqInstallExit=%errorlevel%\"\r\n"
    "echo [Updater %date% %time%] Installer exited with code %kqInstallExit%. >> \"%kqLog%\"\r\n"
    "if %kqInstallExit% neq 0 (\r\n"
    "    echo [Updater %date% %time%] Installer failed. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b %kqInstallExit%\r\n"
    ")\r\n"
    "\r\n"
    "if not exist \"%kqApp%\\modules\\version.py\" (\r\n"
    "    echo [Updater %date% %time%] Installer did not produce expected app structure. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 3\r\n"
    ")\r\n"
    "\r\n"
    "if exist \"%kqBackup%\\progress.json\" (\r\n"
    "    copy /Y \"%kqBackup%\\progress.json\" \"%kqApp%\\progress.json\" >NUL\r\n"
    ")\r\n"
    "if exist \"%kqBackup%\\Sentences\" (\r\n"
    "    if exist \"%kqApp%\\Sentences\" (\r\n"
    "        robocopy \"%kqBackup%\\Sentences\" \"%kqApp%\\Sentences\" /E /XN /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Installer succeeded. Restored saved progress. >> \"%kqLog%\"\r\n"
    "if exist \"%kqBackup%\" rmdir /s /q \"%kqBackup%\"\r\n"
    "timeout /t 2 /nobreak >NUL\r\n"
    "echo [Updater %date% %time%] Restarting KeyQuest from %kqExe%. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
    "\r\n"
    "if exist \"%kqInstaller%\" del /F \"%kqInstaller%\" >NUL 2>&1\r\n"
    "echo [Updater %date% %time%] Installer update launcher finished. >> \"%kqLog%\"\r\n"
    "exit /b 0\r\n"
)


_PORTABLE_BAT_TEMPLATE = (
    "@echo off\r\n"
    "setlocal enabledelayedexpansion\r\n"
    "set \"kqPid=__TARGET_PID__\"\r\n"
    "set \"kqZip=__ZIP_PATH__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqExtract=__EXTRACT_DIR__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Portable updater started. >> \"%kqLog%\"\r\n"
    "echo [Updater %date% %time%] Waiting for process %kqPid% to exit. >> \"%kqLog%\"\r\n"
    "\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | find \" %kqPid% \" >NUL\r\n"
    "if not errorlevel 1 (\r\n"
    "    set /a kqWaitSec+=1\r\n"
    "    if !kqWaitSec! geq 30 (\r\n"
    "        echo [Updater] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "        taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "        timeout /t 1 /nobreak >NUL\r\n"
    "        goto afterwait\r\n"
    "    )\r\n"
    "    timeout /t 1 /nobreak >NUL\r\n"
    "    goto waitloop\r\n"
    ")\r\n"
    ":afterwait\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Process %kqPid% exited. Extracting update. >> \"%kqLog%\"\r\n"
    "if exist \"%kqExtract%\" rmdir /s /q \"%kqExtract%\"\r\n"
    "mkdir \"%kqExtract%\"\r\n"
    "\r\n"
    "if defined KEYQUEST_UPDATER_TEST_PYTHON (\r\n"
    "    echo [Updater %date% %time%] Using Python zip extraction override. >> \"%kqLog%\"\r\n"
    "    \"%KEYQUEST_UPDATER_TEST_PYTHON%\" -c \"import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])\" \"%kqZip%\" \"%kqExtract%\"\r\n"
    ")\r\n"
    "if not exist \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" (\r\n"
    "    echo [Updater %date% %time%] Trying tar extraction. >> \"%kqLog%\"\r\n"
    "    tar -xf \"%kqZip%\" -C \"%kqExtract%\"\r\n"
    "    if errorlevel 1 (\r\n"
    "        echo [Updater %date% %time%] tar extraction failed. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "        if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "        exit /b 1\r\n"
    "    )\r\n"
    ")\r\n"
    "if not exist \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" (\r\n"
    "    echo [Updater %date% %time%] Extraction failed: expected app tree not found. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 2\r\n"
    ")\r\n"
    "\r\n"
    "if exist \"%kqApp%\\Sentences\" (\r\n"
    "    if exist \"%kqExtract%\\KeyQuest\\Sentences\" (\r\n"
    "        robocopy \"%kqApp%\\Sentences\" \"%kqExtract%\\KeyQuest\\Sentences\" /E /XN /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Copying files into app directory. >> \"%kqLog%\"\r\n"
    "robocopy \"%kqExtract%\\KeyQuest\" \"%kqApp%\" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF progress.json KeyQuest.exe keyquest_error.log /XD Sentences updates\r\n"
    "set \"kqRoboExit=%errorlevel%\"\r\n"
    "echo [Updater %date% %time%] Robocopy finished with code %kqRoboExit%. >> \"%kqLog%\"\r\n"
    "if %kqRoboExit% geq 8 (\r\n"
    "    echo [Updater %date% %time%] Robocopy failed. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b %kqRoboExit%\r\n"
    ")\r\n"
    "\r\n"
    "if not exist \"%kqApp%\\modules\\version.py\" (\r\n"
    "    echo [Updater %date% %time%] Update did not produce expected app structure. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 3\r\n"
    ")\r\n"
    "\r\n"
    "if defined KEYQUEST_UPDATER_SKIP_EXE_COPY goto skipexe\r\n"
    "echo [Updater %date% %time%] Replacing KeyQuest.exe. >> \"%kqLog%\"\r\n"
    "set \"kqWait=0\"\r\n"
    ":copyexe\r\n"
    "copy /Y \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" \"%kqApp%\\KeyQuest.exe\" >NUL 2>&1\r\n"
    "if not errorlevel 1 goto exedone\r\n"
    "set /a kqWait+=1\r\n"
    "if %kqWait% geq 15 (\r\n"
    "    echo [Updater %date% %time%] KeyQuest.exe replacement failed after 15 retries. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 32\r\n"
    ")\r\n"
    "echo [Updater %date% %time%] KeyQuest.exe locked, retrying. >> \"%kqLog%\"\r\n"
    "timeout /t 1 /nobreak >NUL\r\n"
    "goto copyexe\r\n"
    ":exedone\r\n"
    "echo [Updater %date% %time%] KeyQuest.exe replacement succeeded. >> \"%kqLog%\"\r\n"
    ":skipexe\r\n"
    "\r\n"
    "if exist \"%kqExtract%\" rmdir /s /q \"%kqExtract%\"\r\n"
    "timeout /t 1 /nobreak >NUL\r\n"
    "echo [Updater %date% %time%] Restarting KeyQuest from %kqExe%. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
    "\r\n"
    "if exist \"%kqZip%\" del /F \"%kqZip%\" >NUL 2>&1\r\n"
    "echo [Updater %date% %time%] Portable update launcher finished. >> \"%kqLog%\"\r\n"
    "exit /b 0\r\n"
)


def create_update_launcher(
    installer_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    script_path: Path | None = None,
) -> Path:
    """Create a detached .bat launcher that waits, installs, then restarts KeyQuest.

    Uses only bat built-ins, robocopy, and the Inno Setup installer — no PowerShell
    dependency.  Returns the path to the .bat file.
    """
    bat_path = script_path or (installer_path.parent / "run_keyquest_update.bat")
    if bat_path.suffix.lower() != ".bat":
        bat_path = bat_path.with_suffix(".bat")
    backup_dir = installer_path.parent / "installer_backup"
    bat_text = (
        _INSTALLER_BAT_TEMPLATE
        .replace("__TARGET_PID__", str(int(current_pid)))
        .replace("__INSTALLER__", str(installer_path))
        .replace("__APP_DIR__", str(app_dir))
        .replace("__APP_EXE__", str(app_exe_path))
        .replace("__BACKUP_DIR__", str(backup_dir))
    )
    bat_path.write_text(bat_text, encoding="utf-8")
    return bat_path


def create_portable_update_launcher(
    zip_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    script_path: Path | None = None,
) -> Path:
    """Create a detached .bat launcher that replaces a portable build in place.

    Uses only bat built-ins, tar, robocopy, and optional Python override for
    extraction in test environments — no PowerShell dependency.
    Returns the path to the .bat file.
    """
    bat_path = script_path or (zip_path.parent / "run_keyquest_portable_update.bat")
    if bat_path.suffix.lower() != ".bat":
        bat_path = bat_path.with_suffix(".bat")
    extract_dir = zip_path.parent / "portable_extract"
    bat_text = (
        _PORTABLE_BAT_TEMPLATE
        .replace("__TARGET_PID__", str(int(current_pid)))
        .replace("__ZIP_PATH__", str(zip_path))
        .replace("__APP_DIR__", str(app_dir))
        .replace("__APP_EXE__", str(app_exe_path))
        .replace("__EXTRACT_DIR__", str(extract_dir))
    )
    bat_path.write_text(bat_text, encoding="utf-8")
    return bat_path


_PORTABLE_FALLBACK_BAT_TEMPLATE = (
    "@echo off\r\n"
    "setlocal enabledelayedexpansion\r\n"
    "set \"kqPid=__TARGET_PID__\"\r\n"
    "set \"kqZip=__ZIP_PATH__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqExtract=__EXTRACT_DIR__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Portable fallback updater started. >> \"%kqLog%\"\r\n"
    "\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | find \" %kqPid% \" >NUL\r\n"
    "if not errorlevel 1 (\r\n"
    "    set /a kqWaitSec+=1\r\n"
    "    if !kqWaitSec! geq 30 (\r\n"
    "        echo [Fallback] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "        taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "        timeout /t 1 /nobreak >NUL\r\n"
    "        goto afterwait\r\n"
    "    )\r\n"
    "    timeout /t 1 /nobreak >NUL\r\n"
    "    goto waitloop\r\n"
    ")\r\n"
    ":afterwait\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Extracting update zip. >> \"%kqLog%\"\r\n"
    "if not exist \"%kqExtract%\" mkdir \"%kqExtract%\"\r\n"
    "tar -xf \"%kqZip%\" -C \"%kqExtract%\"\r\n"
    "if errorlevel 1 (\r\n"
    "    echo [Fallback %date% %time%] tar extraction failed. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 1\r\n"
    ")\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Copying files into app directory. >> \"%kqLog%\"\r\n"
    "robocopy \"%kqExtract%\\KeyQuest\" \"%kqApp%\" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP"
    " /XF progress.json KeyQuest.exe keyquest_error.log /XD Sentences updates\r\n"
    "set \"kqRoboExit=%errorlevel%\"\r\n"
    "if %kqRoboExit% geq 8 (\r\n"
    "    echo [Fallback %date% %time%] Robocopy failed with code %kqRoboExit%. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b %kqRoboExit%\r\n"
    ")\r\n"
    "copy /Y \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" \"%kqApp%\\KeyQuest.exe\" >NUL 2>&1\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Starting KeyQuest. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
)


def create_portable_fallback_bat(
    zip_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    bat_path: Path | None = None,
) -> Path:
    """Write a pure .bat fallback for portable updates that uses tar and robocopy.

    Unlike the main launcher this has no PowerShell dependency, making it
    suitable as a second-chance path when the primary PowerShell launcher fails.
    Requires Windows 10 v1803+ (tar built-in) and robocopy (Vista+).
    """
    bat_path = bat_path or (zip_path.parent / "run_keyquest_portable_fallback.bat")
    extract_dir = zip_path.parent / "portable_fallback_extract"
    bat_text = (
        _PORTABLE_FALLBACK_BAT_TEMPLATE
        .replace("__TARGET_PID__", str(int(current_pid)))
        .replace("__ZIP_PATH__", str(zip_path))
        .replace("__APP_DIR__", str(app_dir))
        .replace("__APP_EXE__", str(app_exe_path))
        .replace("__EXTRACT_DIR__", str(extract_dir))
    )
    bat_path.write_text(bat_text, encoding="utf-8")
    return bat_path


# ---------------------------------------------------------------------------
# High-level check
# ---------------------------------------------------------------------------

def _fetch_with_retry(
    url: str = LATEST_RELEASE_API_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = 3,
    base_delay: float = 3.0,
) -> dict:
    """Call fetch_latest_release with simple exponential backoff on transient errors.

    Only UpdateNetworkError triggers a retry; HTTP errors and parse errors are
    raised immediately because retrying them won't help.
    """
    resolved_url = url or get_configured_release_url()
    last_error: UpdateNetworkError | None = None
    for attempt in range(max_attempts):
        try:
            return fetch_latest_release(url=resolved_url, timeout=timeout)
        except UpdateNetworkError as error:
            last_error = error
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_error  # type: ignore[misc]


def check_for_update(
    current_version: str,
    portable: bool,
    url: str = LATEST_RELEASE_API_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> UpdateAvailable | UpdateUpToDate:
    """Check GitHub for a newer release.

    Returns UpdateAvailable or UpdateUpToDate.
    Raises an UpdateError subclass on failure.
    """
    release = _fetch_with_retry(url=url or get_configured_release_url(), timeout=timeout)
    latest_version = parse_release_version(release)
    if not latest_version or not is_newer_version(current_version, latest_version):
        return UpdateUpToDate(current_version=current_version)

    asset = select_portable_asset(release) if portable else select_installer_asset(release)
    if not asset:
        kind = "portable zip" if portable else "installer"
        raise UpdateNoAssetError(
            f"Version {latest_version} is available but no {kind} asset was attached to the release.",
            version=latest_version,
            kind=kind,
        )

    return UpdateAvailable(
        version=latest_version,
        download_url=str(asset.get("browser_download_url") or ""),
        asset_name=str(asset.get("name") or ""),
        asset_size=int(asset.get("size") or 0),
        asset=asset,
        release=release,
    )


# ---------------------------------------------------------------------------
# SHA-256 verification
# ---------------------------------------------------------------------------

def select_sha256_asset(release: dict, base_asset_name: str) -> dict | None:
    """Return the .sha256 sidecar asset for base_asset_name if present in the release."""
    expected = base_asset_name + ".sha256"
    for asset in release.get("assets", []):
        if str(asset.get("name", "")).lower() == expected.lower():
            return asset
    return None


def fetch_sha256_for_asset(
    sha256_asset: dict,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Download a .sha256 sidecar and return the hex digest string, or None on failure.

    Supports both bare hex and "hexdigest  filename" formats.
    """
    url = str(sha256_asset.get("browser_download_url") or "")
    if not url:
        return None
    try:
        dest = Path(tempfile.gettempdir()) / "keyquest_update.sha256"
        downloaded = download_file(url, dest, timeout=timeout)
        raw = downloaded.read_text(encoding="utf-8").strip()
        return raw.split()[0] if raw else None
    except Exception:
        return None


def verify_file_sha256(file_path: Path, expected_hex: str) -> bool:
    """Return True when file_path's SHA-256 matches expected_hex."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_hex.strip().lower()
