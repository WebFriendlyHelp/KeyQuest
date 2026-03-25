"""GitHub release updater support for KeyQuest."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
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


def _sentence_merge_powershell(source_sentences: str, target_sentences: str) -> str:
    """Return a PowerShell one-liner that merges sentence files by unique lines."""
    return (
        'powershell -NoProfile -ExecutionPolicy Bypass -Command ^\n'
        f'  "$sourceSentences = {source_sentences}; " ^\n'
        f'  "$targetSentences = {target_sentences}; " ^\n'
        '  "if ((Test-Path $sourceSentences) -and (Test-Path $targetSentences)) { " ^\n'
        '  "  Get-ChildItem -LiteralPath $sourceSentences -File | ForEach-Object { " ^\n'
        '  "    $dest = Join-Path $targetSentences $_.Name; " ^\n'
        '  "    if (Test-Path $dest) { " ^\n'
        '  "      $existing = Get-Content -LiteralPath $_.FullName; " ^\n'
        '  "      $incoming = Get-Content -LiteralPath $dest; " ^\n'
        '  "      $merged = New-Object System.Collections.Generic.List[string]; " ^\n'
        '  "      foreach ($line in $existing) { if (-not $merged.Contains($line)) { [void]$merged.Add($line) } } " ^\n'
        '  "      foreach ($line in $incoming) { if (-not $merged.Contains($line)) { [void]$merged.Add($line) } } " ^\n'
        '  "      Set-Content -LiteralPath $dest -Value $merged -Encoding UTF8; " ^\n'
        '  "    } else { " ^\n'
        '  "      Copy-Item -LiteralPath $_.FullName -Destination $dest -Force; " ^\n'
        '  "    } " ^\n'
        '  "  } " ^\n'
        '  "}"'
    )


def _sentence_merge_command(source_sentences: str, target_sentences: str, log_message: str) -> str:
    """Return a batch block that merges sentence files only when both folders exist."""
    powershell_command = _sentence_merge_powershell(source_sentences, target_sentences)
    return (
        f'if exist {source_sentences} if exist {target_sentences} (\n'
        f"{powershell_command}\n"
        "if errorlevel 1 exit /b %errorlevel%\n"
        ") else (\n"
        f'call :log {log_message}\n'
        ")\n"
    )


def _portable_extract_command(extracted_app_dir: str) -> str:
    """Return a batch block that expands a zip and validates the extracted app tree."""
    return (
        f'if defined {UPDATER_TEST_PYTHON_ENV} (\n'
        f'    call :log Trying Python zip extraction override from %{UPDATER_TEST_PYTHON_ENV}%.\n'
        f'    "%{UPDATER_TEST_PYTHON_ENV}%" -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "%ZIP_PATH%" "%EXTRACT_DIR%"\n'
        f"    if exist {extracted_app_dir} goto :extract_done\n"
        '    call :log Python zip extraction override did not produce the extracted app tree. Falling back.\n'
        ")\n"
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath \'%ZIP_PATH%\' -DestinationPath \'%EXTRACT_DIR%\' -Force"\n'
        f"if errorlevel 1 if not exist {extracted_app_dir} (\n"
        '    call :log PowerShell Expand-Archive failed. Trying tar fallback.\n'
        '    tar -xf "%ZIP_PATH%" -C "%EXTRACT_DIR%" >nul 2>&1\n'
        "    if errorlevel 1 exit /b %errorlevel%\n"
        ")\n"
        f"if not exist {extracted_app_dir} (\n"
        '    call :log Expand-Archive did not produce the extracted app tree. Trying tar fallback.\n'
        '    tar -xf "%ZIP_PATH%" -C "%EXTRACT_DIR%" >nul 2>&1\n'
        "    if errorlevel 1 exit /b %errorlevel%\n"
        ")\n"
        ":extract_done\n"
    )


def _sleep_command(seconds: int) -> str:
    """Return a batch-friendly sleep command that works in detached helpers."""
    return f"ping -n {max(int(seconds), 1) + 1} 127.0.0.1 >nul"


def create_update_launcher(
    installer_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    script_path: Path | None = None,
) -> Path:
    """Create a detached launcher script that waits, installs, then restarts KeyQuest."""
    script_path = script_path or (installer_path.parent / "run_keyquest_update.cmd")
    backup_dir = installer_path.parent / "installer_backup"
    sentence_merge_command = _sentence_merge_command(
        "'%BACKUP_DIR%\\Sentences'",
        "'%APP_DIR%\\Sentences'",
        "Sentence merge skipped because backup or target folder was missing.",
    )

    script_text = rf"""@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TARGET_PID={int(current_pid)}"
set "INSTALLER={installer_path}"
set "APP_DIR={app_dir}"
set "APP_EXE={app_exe_path}"
set "BACKUP_DIR={backup_dir}"
set "LOG_PATH=%APP_DIR%\keyquest_error.log"
set "WAIT_SECONDS=0"

call :log Updater launcher started for version package %INSTALLER%.
call :log Waiting for KeyQuest process %TARGET_PID% to exit before running the installer.

:wait_for_exit
tasklist /FI "PID eq %TARGET_PID%" | find "%TARGET_PID%" >nul
if not errorlevel 1 (
    if !WAIT_SECONDS! GEQ 15 (
        call :log KeyQuest process %TARGET_PID% did not exit after 15 seconds. Forcing it closed.
        taskkill /PID %TARGET_PID% /F >nul 2>&1
        {_sleep_command(1)}
    ) else (
        set /a WAIT_SECONDS+=1
    )
    {_sleep_command(1)}
    goto :wait_for_exit
)

call :log KeyQuest process %TARGET_PID% exited. Preparing backup files before install.
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
mkdir "%BACKUP_DIR%" >nul 2>&1
if exist "%APP_DIR%\\progress.json" copy /Y "%APP_DIR%\\progress.json" "%BACKUP_DIR%\\progress.json" >nul
if exist "%APP_DIR%\\Sentences" robocopy "%APP_DIR%\\Sentences" "%BACKUP_DIR%\\Sentences" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul

call :log Starting installer %INSTALLER%.
start "" /wait "%INSTALLER%" /CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /DIR="%APP_DIR%"
set "INSTALL_EXIT=%ERRORLEVEL%"
call :log Installer exited with code %INSTALL_EXIT%.
if not "%INSTALL_EXIT%"=="0" exit /b %INSTALL_EXIT%

if exist "%BACKUP_DIR%\\progress.json" copy /Y "%BACKUP_DIR%\\progress.json" "%APP_DIR%\\progress.json" >nul
{sentence_merge_command}

call :log Installer succeeded. Restored saved progress and sentence files.
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
{_sleep_command(2)}
call :log Restarting KeyQuest from %APP_EXE%.
start "" "%APP_EXE%"
if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath '%APP_EXE%'"
call :log Update launcher finished.
exit /b 0

:log
>> "%LOG_PATH%" echo [Updater %DATE% %TIME%] %*
exit /b 0
"""
    script_path.write_text(script_text, encoding="utf-8")
    return script_path


def create_portable_update_launcher(
    zip_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    script_path: Path | None = None,
) -> Path:
    """Create a detached launcher script that replaces a portable build in place."""
    script_path = script_path or (zip_path.parent / "run_keyquest_portable_update.cmd")
    extract_dir = zip_path.parent / "portable_extract"
    sentence_merge_command = _sentence_merge_command(
        "'%APP_DIR%\\Sentences'",
        "'%EXTRACT_DIR%\\KeyQuest\\Sentences'",
        "Sentence merge skipped because source or extracted folder was missing.",
    )
    extract_command = _portable_extract_command('"%EXTRACT_DIR%\\KeyQuest"')

    script_text = rf"""@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TARGET_PID={int(current_pid)}"
set "ZIP_PATH={zip_path}"
set "APP_DIR={app_dir}"
set "APP_EXE={app_exe_path}"
set "EXTRACT_DIR={extract_dir}"
set "SOURCE_EXE=%EXTRACT_DIR%\KeyQuest\KeyQuest.exe"
set "LOG_PATH=%APP_DIR%\keyquest_error.log"
set "WAIT_SECONDS=0"
set "ROBOCOPY_EXCLUDES=progress.json KeyQuest.exe"

call :log Portable update launcher started for package %ZIP_PATH%.
call :log Waiting for KeyQuest process %TARGET_PID% to exit before applying the portable update.

:wait_for_exit
tasklist /FI "PID eq %TARGET_PID%" | find "%TARGET_PID%" >nul
if not errorlevel 1 (
    if !WAIT_SECONDS! GEQ 15 (
        call :log KeyQuest process %TARGET_PID% did not exit after 15 seconds. Forcing it closed.
        taskkill /PID %TARGET_PID% /F >nul 2>&1
        {_sleep_command(1)}
    ) else (
        set /a WAIT_SECONDS+=1
    )
    {_sleep_command(1)}
    goto :wait_for_exit
)

call :log KeyQuest process %TARGET_PID% exited. Expanding portable update package.
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
mkdir "%EXTRACT_DIR%" >nul 2>&1
{extract_command}

{sentence_merge_command}

call :log Portable update content prepared. Copying files into %APP_DIR%.
robocopy "%EXTRACT_DIR%\\KeyQuest" "%APP_DIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF %ROBOCOPY_EXCLUDES%
set "ROBOCODE=%ERRORLEVEL%"
call :log Robocopy finished with code %ROBOCODE%.
if %ROBOCODE% GEQ 8 exit /b %ROBOCODE%

if defined {UPDATER_TEST_SKIP_EXE_COPY_ENV} (
    call :log Skipping portable KeyQuest.exe replacement because the harness override is enabled.
) else (
    call :copy_app_exe
    if errorlevel 1 exit /b !errorlevel!
)

if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
{_sleep_command(1)}
call :log Restarting KeyQuest from %APP_EXE%.
start "" "%APP_EXE%"
if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath '%APP_EXE%'"
call :log Portable update launcher finished.
exit /b 0

:copy_app_exe
if not exist "%SOURCE_EXE%" (
    call :log Portable update source exe was missing after extraction.
    exit /b 2
)
set "EXE_WAIT_SECONDS=0"
:copy_app_exe_retry
copy /Y "%SOURCE_EXE%" "%APP_EXE%" >nul
if not errorlevel 1 (
    call :log Portable KeyQuest.exe replacement succeeded.
    exit /b 0
)
if !EXE_WAIT_SECONDS! GEQ 15 (
    call :log Portable KeyQuest.exe replacement failed after 15 seconds of retries.
    exit /b 32
)
set /a EXE_WAIT_SECONDS+=1
call :log Portable KeyQuest.exe replacement is still locked. Retrying.
{_sleep_command(1)}
goto :copy_app_exe_retry

:log
>> "%LOG_PATH%" echo [Updater %DATE% %TIME%] %*
exit /b 0
"""
    script_path.write_text(script_text, encoding="utf-8")
    return script_path

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
