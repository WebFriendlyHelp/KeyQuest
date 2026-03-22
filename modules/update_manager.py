"""GitHub release updater support for KeyQuest."""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


GITHUB_OWNER = "WebFriendlyHelp"
GITHUB_REPO = "KeyQuest"
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
DEFAULT_TIMEOUT_SECONDS = 15
INSTALLER_NAME = "KeyQuestSetup.exe"
PORTABLE_ZIP_NAME = "KeyQuest-win64.zip"

try:
    import certifi
except Exception:
    certifi = None


def can_self_update() -> bool:
    """Return True when the current process can update an installed app."""
    return os.name == "nt" and getattr(sys, "frozen", False)


def is_portable_layout(app_dir: str) -> bool:
    """Return True when the running frozen app appears to be a portable build."""
    exe_dir = Path(app_dir)
    return (
        exe_dir.exists()
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
    raise RuntimeError("Windows update fallback failed. " + " | ".join(errors))


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
    """Fetch the latest GitHub release metadata."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "KeyQuest-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_build_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        if os.name == "nt" and _is_tls_verification_error(error):
            return _fetch_latest_release_with_windows_fallbacks(url=url, timeout=timeout)
        raise


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
        '  "if ((Test-Path $sourceSentences) -and (Test-Path $targetSentences)) {{ " ^\n'
        '  "  Get-ChildItem -LiteralPath $sourceSentences -File | ForEach-Object {{ " ^\n'
        '  "    $dest = Join-Path $targetSentences $_.Name; " ^\n'
        '  "    if (Test-Path $dest) {{ " ^\n'
        '  "      $existing = Get-Content -LiteralPath $_.FullName; " ^\n'
        '  "      $incoming = Get-Content -LiteralPath $dest; " ^\n'
        '  "      $merged = New-Object System.Collections.Generic.List[string]; " ^\n'
        '  "      foreach ($line in $existing) {{ if (-not $merged.Contains($line)) {{ [void]$merged.Add($line) }} }} " ^\n'
        '  "      foreach ($line in $incoming) {{ if (-not $merged.Contains($line)) {{ [void]$merged.Add($line) }} }} " ^\n'
        '  "      Set-Content -LiteralPath $dest -Value $merged -Encoding UTF8; " ^\n'
        '  "    }} else {{ " ^\n'
        '  "      Copy-Item -LiteralPath $_.FullName -Destination $dest -Force; " ^\n'
        '  "    }} " ^\n'
        '  "  }} " ^\n'
        '  "}}"'
    )


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
    sentence_merge_command = _sentence_merge_powershell(
        "'%BACKUP_DIR%\\Sentences'",
        "'%APP_DIR%\\Sentences'",
    )

    script_text = f"""@echo off
setlocal EnableExtensions
set "TARGET_PID={int(current_pid)}"
set "INSTALLER={installer_path}"
set "APP_DIR={app_dir}"
set "APP_EXE={app_exe_path}"
set "BACKUP_DIR={backup_dir}"
set "LOG_PATH=%APP_DIR%\keyquest_error.log"

call :log Updater launcher started for version package %INSTALLER%.
call :log Waiting for KeyQuest process %TARGET_PID% to exit before running the installer.

:wait_for_exit
tasklist /FI "PID eq %TARGET_PID%" | find "%TARGET_PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto :wait_for_exit
)

call :log KeyQuest process %TARGET_PID% exited. Preparing backup files before install.
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
mkdir "%BACKUP_DIR%" >nul 2>&1
if exist "%APP_DIR%\\progress.json" copy /Y "%APP_DIR%\\progress.json" "%BACKUP_DIR%\\progress.json" >nul
if exist "%APP_DIR%\\Sentences" robocopy "%APP_DIR%\\Sentences" "%BACKUP_DIR%\\Sentences" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul

call :log Starting installer %INSTALLER%.
start "" /wait "%INSTALLER%" /CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS
set "INSTALL_EXIT=%ERRORLEVEL%"
call :log Installer exited with code %INSTALL_EXIT%.
if not "%INSTALL_EXIT%"=="0" exit /b %INSTALL_EXIT%

if exist "%BACKUP_DIR%\\progress.json" copy /Y "%BACKUP_DIR%\\progress.json" "%APP_DIR%\\progress.json" >nul
{sentence_merge_command}
if errorlevel 1 exit /b %errorlevel%

call :log Installer succeeded. Restored saved progress and sentence files.
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
timeout /t 2 /nobreak >nul
call :log Restarting KeyQuest from %APP_EXE%.
start "" "%APP_EXE%"
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
    sentence_merge_command = _sentence_merge_powershell(
        "'%APP_DIR%\\Sentences'",
        "$releaseSentences",
    )

    script_text = f"""@echo off
setlocal EnableExtensions
set "TARGET_PID={int(current_pid)}"
set "ZIP_PATH={zip_path}"
set "APP_DIR={app_dir}"
set "APP_EXE={app_exe_path}"
set "EXTRACT_DIR={extract_dir}"
set "LOG_PATH=%APP_DIR%\keyquest_error.log"

call :log Portable update launcher started for package %ZIP_PATH%.
call :log Waiting for KeyQuest process %TARGET_PID% to exit before applying the portable update.

:wait_for_exit
tasklist /FI "PID eq %TARGET_PID%" | find "%TARGET_PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto :wait_for_exit
)

call :log KeyQuest process %TARGET_PID% exited. Expanding portable update package.
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP_PATH%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$releaseRoot = Join-Path '%EXTRACT_DIR%' 'KeyQuest'; " ^
  "$releaseSentences = Join-Path $releaseRoot 'Sentences'; " ^
{sentence_merge_command}
if errorlevel 1 exit /b %errorlevel%

call :log Portable update content prepared. Copying files into %APP_DIR%.
robocopy "%EXTRACT_DIR%\\KeyQuest" "%APP_DIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF progress.json
set "ROBOCODE=%ERRORLEVEL%"
call :log Robocopy finished with code %ROBOCODE%.
if %ROBOCODE% GEQ 8 exit /b %ROBOCODE%

if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
timeout /t 1 /nobreak >nul
call :log Restarting KeyQuest from %APP_EXE%.
start "" "%APP_EXE%"
call :log Portable update launcher finished.
exit /b 0

:log
>> "%LOG_PATH%" echo [Updater %DATE% %TIME%] %*
exit /b 0
"""
    script_path.write_text(script_text, encoding="utf-8")
    return script_path
