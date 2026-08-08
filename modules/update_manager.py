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
import zipfile
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

# Folder under the app directory where pre-update rollback snapshots are kept.
BACKUP_DIR_NAME = "Backups"
# Written into a rollback snapshot only when every file was captured. The
# launcher mirrors (deletes extras) only when this marker is present, and
# overlays otherwise, so an incomplete snapshot can never delete a file it
# has no copy of.
SNAPSHOT_COMPLETE_MARKER = ".kq_snapshot_complete"
# How many backup ZIPs to retain before the oldest are pruned.
MAX_KEPT_BACKUPS = 2

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


def write_pending_update_marker(app_dir: str, expected_version: str) -> bool:
    """Write a marker so the next launch can verify the update applied.

    Returns ``True`` on success.  A silent ``False`` used to be indistinguishable
    from success, which meant a blocked write (permissions, disk full, security
    software) left a later swap failure with no marker at all, so the next launch
    reported neither success nor failure.  Callers log the failure instead.
    """
    marker = Path(app_dir) / "pending_update.json"
    try:
        marker.write_text(
            json.dumps({"expected_version": expected_version, "timestamp": time.time()}),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


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
                    "portable_restore",
                    "portable_fallback_restore",
                ):
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


def _prune_old_backups(backups_dir: Path, keep: int = MAX_KEPT_BACKUPS) -> None:
    """Keep only the newest *keep* backup ZIPs in *backups_dir*."""
    try:
        backups = sorted(
            backups_dir.glob("KeyQuest-backup-*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for stale in backups[max(keep, 0):]:
        try:
            stale.unlink()
        except OSError:
            pass


def create_app_backup_zip(
    app_dir: str,
    current_version: str,
    max_kept: int = MAX_KEPT_BACKUPS,
) -> Path | None:
    """Snapshot the current portable app directory into a rollback ZIP.

    The archive is written to ``<app_dir>/Backups/KeyQuest-backup-<version>.zip``
    with no compression (speed over size — it is a transient rollback artifact)
    and stores paths relative to the app directory so it can be restored with
    ``tar -xf backup.zip -C <app_dir>``.

    Transient/user-data folders (``Backups`` itself and ``updates``) are skipped.
    This is best-effort: any failure returns ``None`` rather than raising, so a
    backup problem can never block an otherwise-working update.
    """
    try:
        app_path = Path(app_dir)
        if not app_path.exists():
            return None
        backups_dir = app_path / BACKUP_DIR_NAME
        backups_dir.mkdir(parents=True, exist_ok=True)
        safe_version = normalize_version(current_version).replace(".", "_")
        backup_path = backups_dir / f"KeyQuest-backup-{safe_version}.zip"
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass
        excluded_top = {BACKUP_DIR_NAME.lower(), "updates"}
        skipped = 0
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_STORED) as archive:
            for root, dirs, files in os.walk(app_path):
                rel_root = Path(root).relative_to(app_path)
                top = rel_root.parts[0].lower() if rel_root.parts else ""
                if top in excluded_top:
                    dirs[:] = []
                    continue
                for name in files:
                    file_path = Path(root) / name
                    arcname = (rel_root / name).as_posix()
                    try:
                        archive.write(file_path, arcname)
                    except OSError:
                        # A locked or vanished file is non-fatal for a best-effort
                        # snapshot, but it stops the snapshot being an exact record
                        # of the install -- see the marker below.
                        skipped += 1
            if not skipped:
                # Rollback mirrors this snapshot back over the app, which deletes
                # anything the snapshot does not contain.  That is what makes
                # rollback exact, and it is only safe when the snapshot is
                # complete: a file skipped above would otherwise be deleted from
                # the app with no old copy to restore, which is worse than the
                # mixed tree the old overlay restore produced.  The launcher
                # mirrors only when it finds this marker, and overlays otherwise.
                archive.writestr(SNAPSHOT_COMPLETE_MARKER, "")
        _prune_old_backups(backups_dir, keep=max_kept)
        return backup_path
    except Exception:
        return None


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


# ---------------------------------------------------------------------------
# Making arbitrary Windows paths safe to embed in a generated .bat
# ---------------------------------------------------------------------------

# Characters batch either expands or treats as syntax when they appear in a
# substituted path.  ``%`` is expanded while the line is parsed, ``!`` again
# under delayed expansion, and ``&``/``(``/``)``/``^`` can split or corrupt the
# surrounding command wherever the value is not quoted (an ``echo`` of a path,
# for example) or the surrounding block.
# ``%`` is the only one that cannot be handled by quoting alone: it is expanded
# while the line is parsed, before any quoting applies.  It is escaped instead
# (see :func:`bat_value`).  ``!`` is safe now that no template enables delayed
# expansion, and ``&``/``(``/``)``/``^`` are safe because every substituted value
# lands inside a quoted ``set "kqX=..."`` and every later use is quoted too.
_BATCH_HOSTILE_CHARS = frozenset("%")


def _is_batch_safe(text: str) -> bool:
    """True when *text* can be substituted into a .bat without being mangled.

    Non-ASCII fails because cmd.exe parses .bat files in the console OEM code
    page, not UTF-8.  A non-ASCII Windows user name is the realistic trigger:
    the app dir, staging dir, exe path and log path all run through it, so one
    such character turns *every* path in the script into mojibake, including the
    restart line the no-stranding guarantee depends on.
    """
    return text.isascii() and not any(ch in _BATCH_HOSTILE_CHARS for ch in text)


def _oem_encoding() -> str | None:
    """Return the console OEM code page as a Python codec name, if resolvable."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:
        return None


def _short_path(text: str) -> str | None:
    """Return the Windows 8.3 short path for *text*, or ``None`` if unavailable.

    Short paths are pure ASCII and contain none of the hostile characters, so
    converting is the most reliable way to make an awkward path safe to embed.
    Requires the path to exist and 8.3 name creation to be enabled on the
    volume; returns ``None`` when either is untrue.
    """
    if os.name != "nt" or not text:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        get_short = ctypes.windll.kernel32.GetShortPathNameW
        get_short.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_short.restype = wintypes.DWORD
        needed = get_short(text, None, 0)
        if not needed:
            return None
        buffer = ctypes.create_unicode_buffer(needed)
        if not get_short(text, buffer, needed):
            return None
        return buffer.value or None
    except Exception:
        return None


def batch_safe_path(path: str | Path) -> str:
    """Return a form of *path* safe to substitute into a .bat template.

    Returns the path unchanged when it is already safe, which is the normal
    case.  Otherwise tries the 8.3 short path, then the "shorten the parent,
    keep the ASCII leaf" variant for directories the launcher has not created
    yet (the extract and backup dirs).  Falls back to the original string when
    nothing better is available, so this can never make a path *worse* than
    leaving it alone.
    """
    text = str(path)
    if _is_batch_safe(text):
        return text

    short = _short_path(text)
    if short and _is_batch_safe(short):
        return short

    parent, leaf = os.path.split(text)
    if parent and leaf and _is_batch_safe(leaf):
        short_parent = _short_path(parent)
        if short_parent and _is_batch_safe(short_parent):
            return os.path.join(short_parent, leaf)

    return text


def bat_value(path: str | Path) -> str:
    """Return *path* ready to substitute into a quoted ``set "kqX=..."`` line.

    Shortens the path when that helps (non-ASCII, mainly), then escapes ``%`` as
    ``%%`` so batch's parse-time expansion yields the literal character back.
    Expansion is single pass, so ``%kqX%`` later gives the real path.
    """
    return batch_safe_path(path).replace("%", "%%")


def quote_bat_command(bat_path: str | Path) -> str:
    """Return a ``cmd`` command line that runs *bat_path* safely.

    ``subprocess`` only quotes an argument that contains whitespace, so a
    launcher path holding ``&`` or ``()`` was handed to cmd unquoted and split
    into pieces.  ``/s`` tells cmd to strip the outer quote pair and take the
    rest literally, which is the documented way to pass an awkward path.

    cmd also expands ``%VAR%`` on its own command line, before it locates the
    file, and there is no reliable way to escape ``%`` there -- passing only the
    file name with a working directory does not work either, because cmd cannot
    resolve a quoted relative command name (verified: it reports
    ``'"run me.bat"' is not recognized``).  So the path is shortened where that
    helps, and if a ``%`` still survives we refuse rather than launch whatever
    the expansion happens to point at.
    """
    text = batch_safe_path(bat_path)
    if "%" in text:
        raise UpdateError(
            "The update helper could not be started because its folder path "
            "contains a percent sign, which Windows would interpret as a "
            "variable. Please install the update manually from the KeyQuest "
            "releases page."
        )
    return f'cmd /s /c ""{text}""'


def fill_bat_template(template: str, mapping: dict[str, str]) -> str:
    """Substitute every placeholder in one pass.

    Chained ``.replace()`` calls let an already-substituted value be rewritten by
    a later replacement, if that value happens to contain a later placeholder
    token.  Reproduced with an installer under a directory named ``__APP_DIR__``:
    the result was ``C:\\...\\__APP_DIR__\\Setup.exe`` rewritten to
    ``C:\\...\\C:\\RealApp\\Setup.exe``.  A single pass cannot do that, because
    substituted text is never rescanned.
    """
    pattern = re.compile("|".join(re.escape(key) for key in mapping))
    return pattern.sub(lambda match: mapping[match.group(0)], template)


def _write_bat(bat_path: Path, bat_text: str) -> Path:
    """Write generated batch text in an encoding cmd.exe will actually read.

    The templates already carry explicit CRLF, so ``newline=""`` is required:
    without it Python translates the ``\\n`` again and every line ends ``\\r\\r\\n``.

    ASCII is valid in every OEM code page and :func:`batch_safe_path` normally
    keeps the text ASCII, so that is the usual path.  If something non-ASCII
    survived (8.3 names disabled on the volume, say), fall back to the OEM code
    page so cmd reads what we wrote, and only then to UTF-8.
    """
    if bat_text.isascii():
        bat_path.write_text(bat_text, encoding="ascii", newline="")
        return bat_path

    # Non-ASCII survived path shortening, which happens when 8.3 name creation
    # is disabled on the volume.  The OEM code page is the only encoding cmd
    # will read correctly, so if the text does not fit in it there is no way to
    # emit a script cmd can execute.
    oem = _oem_encoding()
    if oem:
        try:
            bat_path.write_text(bat_text, encoding=oem, newline="")
            return bat_path
        except (UnicodeEncodeError, LookupError):
            pass

    # Fail loudly rather than writing UTF-8 that cmd will read as OEM and turn
    # into mojibake.  A corrupted script strands the user with no app running;
    # raising here routes through the controller's recovery path and tells them
    # to update manually, which is a bad outcome but an honest and recoverable
    # one.  Realistic trigger: 8.3 disabled plus a CJK or Cyrillic user name.
    raise UpdateError(
        "This Windows user or install path contains characters that cannot be "
        "written into an update script on this system (short 8.3 path names are "
        "unavailable and the path does not fit the console code page). "
        "Please download and install the update manually."
    )


_INSTALLER_BAT_TEMPLATE = (
    "@echo off\r\n"
    # Explicitly DISABLED, not merely "not enabled".  Delayed expansion can be
    # turned on globally via the Command Processor registry setting, and a plain
    # "setlocal" inherits it -- at which case a path containing a matched pair
    # like !TEMP! is expanded while the line is parsed.  Verified with cmd /v:on.
    "setlocal disabledelayedexpansion\r\n"
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
    # Pin find.exe to the Windows one, exactly as kqTar pins bsdtar and for the
    # same reason.  With Git for Windows (or Cygwin/MSYS/busybox) installed, its
    # usr\bin\find.exe comes FIRST on PATH.  GNU find treats " <pid> " as a path,
    # fails, and returns non-zero, so "if errorlevel 1 goto afterwait" concluded
    # the app had already exited and the wait loop became a no-op.  The updater
    # then mirrored over a RUNNING install: exe locked, retries, and on a slow
    # exit a rollback.  The 30-second taskkill never fired either, because the
    # loop never looped.
    "set \"kqFind=find\"\r\n"
    "if exist \"%SystemRoot%\\Sysnative\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\Sysnative\\find.exe\"\r\n"
    ") else if exist \"%SystemRoot%\\System32\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\System32\\find.exe\"\r\n"
    ")\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | \"%kqFind%\" \" %kqPid% \" >NUL\r\n"
    # The counter is compared on its own line rather than inside the if-block so
    # that plain %VAR% expansion is correct on every pass (goto re-parses the
    # line).  Doing it in-block is what previously required delayed expansion,
    # which silently ate any "!" in a substituted path.
    "if errorlevel 1 goto afterwait\r\n"
    "set /a kqWaitSec+=1\r\n"
    "if %kqWaitSec% geq 30 (\r\n"
    "    echo [Updater] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "    taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "    ping -n 2 127.0.0.1 >NUL\r\n"
    "    goto afterwait\r\n"
    ")\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto waitloop\r\n"
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
    # /XO, not /XN.  Source is the user's pre-update backup, destination is what
    # the installer just laid down.  /XO excludes source files OLDER than the
    # destination, so a file the user edited recently wins and an untouched
    # default does not clobber a newer shipped one.  This was /XN, which is the
    # exact inverse: it skipped precisely the files the user had just edited.
    # The .iss copies with "ignoreversion", so this restore is the only thing
    # preserving user sentence edits across an installer update.
    "        robocopy \"%kqBackup%\\Sentences\" \"%kqApp%\\Sentences\" /E /XO /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Installer succeeded. Restored saved progress. >> \"%kqLog%\"\r\n"
    "if exist \"%kqBackup%\" rmdir /s /q \"%kqBackup%\"\r\n"
    "ping -n 3 127.0.0.1 >NUL\r\n"
    "echo [Updater %date% %time%] Restarting KeyQuest from %kqExe%. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
    "\r\n"
    "if exist \"%kqInstaller%\" del /F \"%kqInstaller%\" >NUL 2>&1\r\n"
    "echo [Updater %date% %time%] Installer update launcher finished. >> \"%kqLog%\"\r\n"
    "exit /b 0\r\n"
)


_PORTABLE_BAT_TEMPLATE = (
    "@echo off\r\n"
    # Explicitly DISABLED, not merely "not enabled".  Delayed expansion can be
    # turned on globally via the Command Processor registry setting, and a plain
    # "setlocal" inherits it -- at which case a path containing a matched pair
    # like !TEMP! is expanded while the line is parsed.  Verified with cmd /v:on.
    "setlocal disabledelayedexpansion\r\n"
    "set \"kqPid=__TARGET_PID__\"\r\n"
    "set \"kqZip=__ZIP_PATH__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqExtract=__EXTRACT_DIR__\"\r\n"
    "set \"kqRestore=__RESTORE_DIR__\"\r\n"
    "set \"kqBackupZip=__BACKUP_ZIP__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "set \"kqFailCode=0\"\r\n"
    "set \"kqRollbackOk=0\"\r\n"
    "set \"kqTar=tar\"\r\n"
    "if exist \"%SystemRoot%\\Sysnative\\tar.exe\" (\r\n"
    "    set \"kqTar=%SystemRoot%\\Sysnative\\tar.exe\"\r\n"
    ") else if exist \"%SystemRoot%\\System32\\tar.exe\" (\r\n"
    "    set \"kqTar=%SystemRoot%\\System32\\tar.exe\"\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Portable updater started. >> \"%kqLog%\"\r\n"
    "echo [Updater %date% %time%] Waiting for process %kqPid% to exit. >> \"%kqLog%\"\r\n"
    "\r\n"
    # Pin find.exe to the Windows one, exactly as kqTar pins bsdtar and for the
    # same reason.  With Git for Windows (or Cygwin/MSYS/busybox) installed, its
    # usr\bin\find.exe comes FIRST on PATH.  GNU find treats " <pid> " as a path,
    # fails, and returns non-zero, so "if errorlevel 1 goto afterwait" concluded
    # the app had already exited and the wait loop became a no-op.  The updater
    # then mirrored over a RUNNING install: exe locked, retries, and on a slow
    # exit a rollback.  The 30-second taskkill never fired either, because the
    # loop never looped.
    "set \"kqFind=find\"\r\n"
    "if exist \"%SystemRoot%\\Sysnative\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\Sysnative\\find.exe\"\r\n"
    ") else if exist \"%SystemRoot%\\System32\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\System32\\find.exe\"\r\n"
    ")\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | \"%kqFind%\" \" %kqPid% \" >NUL\r\n"
    # The counter is compared on its own line rather than inside the if-block so
    # that plain %VAR% expansion is correct on every pass (goto re-parses the
    # line).  Doing it in-block is what previously required delayed expansion,
    # which silently ate any "!" in a substituted path.
    "if errorlevel 1 goto afterwait\r\n"
    "set /a kqWaitSec+=1\r\n"
    "if %kqWaitSec% geq 30 (\r\n"
    "    echo [Updater] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "    taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "    ping -n 2 127.0.0.1 >NUL\r\n"
    "    goto afterwait\r\n"
    ")\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto waitloop\r\n"
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
    "    \"%kqTar%\" -xf \"%kqZip%\" -C \"%kqExtract%\"\r\n"
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
    # /XO for the same reason as the installer restore: keep the user's newer
    # edits, do not overwrite a newer shipped default.  (The mirror below also
    # carries /XD Sentences, so the app's own folder is never touched either.)
    "        robocopy \"%kqApp%\\Sentences\" \"%kqExtract%\\KeyQuest\\Sentences\" /E /XO /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >NUL\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "echo [Updater %date% %time%] Copying files into app directory. >> \"%kqLog%\"\r\n"
    "robocopy \"%kqExtract%\\KeyQuest\" \"%kqApp%\" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF progress.json KeyQuest.exe keyquest_error.log pending_update.json /XD Sentences updates Backups\r\n"
    "set \"kqRoboExit=%errorlevel%\"\r\n"
    "echo [Updater %date% %time%] Robocopy finished with code %kqRoboExit%. >> \"%kqLog%\"\r\n"
    "if %kqRoboExit% geq 8 (\r\n"
    "    echo [Updater %date% %time%] Robocopy failed. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=%kqRoboExit%\"\r\n"
    "    goto rollback\r\n"
    ")\r\n"
    "\r\n"
    "if not exist \"%kqApp%\\modules\\version.py\" (\r\n"
    "    echo [Updater %date% %time%] Update did not produce expected app structure. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=3\"\r\n"
    "    goto rollback\r\n"
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
    "    echo [Updater %date% %time%] KeyQuest.exe replacement failed after 15 retries. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=32\"\r\n"
    "    goto rollback\r\n"
    ")\r\n"
    "echo [Updater %date% %time%] KeyQuest.exe locked, retrying. >> \"%kqLog%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto copyexe\r\n"
    ":exedone\r\n"
    "echo [Updater %date% %time%] KeyQuest.exe replacement succeeded. >> \"%kqLog%\"\r\n"
    ":skipexe\r\n"
    "\r\n"
    "if exist \"%kqExtract%\" rmdir /s /q \"%kqExtract%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "echo [Updater %date% %time%] Restarting KeyQuest from %kqExe%. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
    "\r\n"
    "if exist \"%kqZip%\" del /F \"%kqZip%\" >NUL 2>&1\r\n"
    "echo [Updater %date% %time%] Portable update launcher finished. >> \"%kqLog%\"\r\n"
    "exit /b 0\r\n"
    "\r\n"
    ":rollback\r\n"
    "echo [Updater %date% %time%] Update failed (code %kqFailCode%). Restoring previous version. >> \"%kqLog%\"\r\n"
    "if not defined kqBackupZip (\r\n"
    "    echo [Updater %date% %time%] ROLLBACK UNAVAILABLE: no snapshot was taken. Restarting current files. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    # Paths are quoted in every echo below.  Unquoted, a ")" in the path closes
    # the enclosing if-block and cmd aborts the script at parse time, skipping
    # the restart; "&" would run part of the path as a command.
    "if not exist \"%kqBackupZip%\" (\r\n"
    "    echo [Updater %date% %time%] ROLLBACK UNAVAILABLE: no snapshot at \"%kqBackupZip%\". Restarting current files. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    "echo [Updater %date% %time%] Restoring backup from \"%kqBackupZip%\". >> \"%kqLog%\"\r\n"
    "set \"kqRestoreTry=0\"\r\n"
    "set \"kqTarExit=0\"\r\n"
    ":restoreloop\r\n"
    # Extract to a staging dir and MIRROR it back, rather than extracting on top
    # of the app.  Overlaying restores old files but cannot remove files that
    # only the new release introduced, so a "successful" rollback still left a
    # mixed old/new tree running under the old exe.
    "if exist \"%kqRestore%\" rmdir /s /q \"%kqRestore%\"\r\n"
    "mkdir \"%kqRestore%\"\r\n"
    "\"%kqTar%\" -xf \"%kqBackupZip%\" -C \"%kqRestore%\" >> \"%kqLog%\" 2>&1\r\n"
    # Both conditions are required.  Checking only for version.py declared
    # success whenever a partially mirrored tree happened to contain one, which
    # it usually does, so a completely failed restore was logged as "restored".
    "set \"kqTarExit=%errorlevel%\"\r\n"
    "if %kqTarExit% neq 0 goto restoreretry\r\n"
    "if not exist \"%kqRestore%\\modules\\version.py\" goto restoreretry\r\n"
    # Mirror, do not overlay.  Extracting on top of the app restores old files
    # but cannot remove files that only the new release introduced, so a
    # "successful" rollback still started the old exe against a mixed tree.
    # Mirror only when the snapshot is a COMPLETE record of the old install.
    # /MIR deletes whatever the snapshot does not contain, which is what makes
    # rollback exact -- but against an incomplete snapshot it would delete a
    # file it has no copy of, which is worse than the mixed tree the old overlay
    # restore left behind.  create_app_backup_zip writes the marker only when it
    # captured every file.  Plain top-level lines, no if-blocks: a parenthesised
    # construct in this routine has already broken it once.
    "set \"kqRestoreMode=/E\"\r\n"
    "if exist \"%kqRestore%\\.kq_snapshot_complete\" set \"kqRestoreMode=/MIR\"\r\n"
    "echo [Updater %date% %time%] Restore mode %kqRestoreMode% (/MIR = snapshot complete). >> \"%kqLog%\"\r\n"
    "robocopy \"%kqRestore%\" \"%kqApp%\" %kqRestoreMode% /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF progress.json KeyQuest.exe keyquest_error.log pending_update.json .kq_snapshot_complete /XD Sentences updates Backups >> \"%kqLog%\" 2>&1\r\n"
    "set \"kqRoboBack=%errorlevel%\"\r\n"
    "if %kqRoboBack% geq 8 goto restoreretry\r\n"
    "if not exist \"%kqApp%\\modules\\version.py\" goto restoreretry\r\n"
    "echo [Updater %date% %time%] Backup restored. >> \"%kqLog%\"\r\n"
    "set \"kqRollbackOk=1\"\r\n"
    "goto rollbackrestart\r\n"
    ":restoreretry\r\n"
    "set /a kqRestoreTry+=1\r\n"
    "if %kqRestoreTry% geq 10 (\r\n"
    "    echo [Updater %date% %time%] ROLLBACK FAILED after 10 attempts, last tar exit %kqTarExit%. Install may be inconsistent. Restarting anyway. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    "echo [Updater %date% %time%] Backup restore attempt %kqRestoreTry% failed (tar exit %kqTarExit%), retrying. >> \"%kqLog%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto restoreloop\r\n"
    ":rollbackrestart\r\n"
    "if exist \"%kqRestore%\" rmdir /s /q \"%kqRestore%\"\r\n"
    "if exist \"%kqExtract%\" rmdir /s /q \"%kqExtract%\"\r\n"
    # Top level, no parentheses, no enclosing block.  Deliberately the dullest
    # possible construct: a fancier in-block echo with parens is exactly what
    # broke this path once already.
    "echo [Updater %date% %time%] Rollback verified: %kqRollbackOk% where 1 means the snapshot was restored. >> \"%kqLog%\"\r\n"
    "echo [Updater %date% %time%] Restarting KeyQuest after rollback. >> \"%kqLog%\"\r\n"
    "if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "exit /b %kqFailCode%\r\n"
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
    bat_text = fill_bat_template(
        _INSTALLER_BAT_TEMPLATE, {
            "__TARGET_PID__": str(int(current_pid)),
            "__INSTALLER__": bat_value(installer_path),
            "__APP_DIR__": bat_value(app_dir),
            "__APP_EXE__": bat_value(app_exe_path),
            "__BACKUP_DIR__": bat_value(backup_dir),
        }
    )
    return _write_bat(bat_path, bat_text)


def create_portable_update_launcher(
    zip_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    script_path: Path | None = None,
    backup_zip_path: Path | None = None,
) -> Path:
    """Create a detached .bat launcher that replaces a portable build in place.

    Uses only bat built-ins, tar, robocopy, and optional Python override for
    extraction in test environments — no PowerShell dependency.

    When *backup_zip_path* points to a pre-update snapshot (see
    :func:`create_app_backup_zip`), any failure after the destructive mirror
    step rolls the install back by extracting that snapshot before restarting.
    Returns the path to the .bat file.
    """
    bat_path = script_path or (zip_path.parent / "run_keyquest_portable_update.bat")
    if bat_path.suffix.lower() != ".bat":
        bat_path = bat_path.with_suffix(".bat")
    extract_dir = zip_path.parent / "portable_extract"
    restore_dir = zip_path.parent / "portable_restore"
    bat_text = fill_bat_template(
        _PORTABLE_BAT_TEMPLATE, {
            "__TARGET_PID__": str(int(current_pid)),
            "__ZIP_PATH__": bat_value(zip_path),
            "__APP_DIR__": bat_value(app_dir),
            "__APP_EXE__": bat_value(app_exe_path),
            "__EXTRACT_DIR__": bat_value(extract_dir),
            "__RESTORE_DIR__": bat_value(restore_dir),
            "__BACKUP_ZIP__": bat_value(backup_zip_path) if backup_zip_path else "",
        }
    )
    return _write_bat(bat_path, bat_text)


_PORTABLE_FALLBACK_BAT_TEMPLATE = (
    "@echo off\r\n"
    # Explicitly DISABLED, not merely "not enabled".  Delayed expansion can be
    # turned on globally via the Command Processor registry setting, and a plain
    # "setlocal" inherits it -- at which case a path containing a matched pair
    # like !TEMP! is expanded while the line is parsed.  Verified with cmd /v:on.
    "setlocal disabledelayedexpansion\r\n"
    "set \"kqPid=__TARGET_PID__\"\r\n"
    "set \"kqZip=__ZIP_PATH__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqExtract=__EXTRACT_DIR__\"\r\n"
    "set \"kqRestore=__RESTORE_DIR__\"\r\n"
    "set \"kqBackupZip=__BACKUP_ZIP__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "set \"kqFailCode=0\"\r\n"
    "set \"kqRollbackOk=0\"\r\n"
    "set \"kqTar=tar\"\r\n"
    "if exist \"%SystemRoot%\\Sysnative\\tar.exe\" (\r\n"
    "    set \"kqTar=%SystemRoot%\\Sysnative\\tar.exe\"\r\n"
    ") else if exist \"%SystemRoot%\\System32\\tar.exe\" (\r\n"
    "    set \"kqTar=%SystemRoot%\\System32\\tar.exe\"\r\n"
    ")\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Portable fallback updater started. >> \"%kqLog%\"\r\n"
    "\r\n"
    # Pin find.exe to the Windows one, exactly as kqTar pins bsdtar and for the
    # same reason.  With Git for Windows (or Cygwin/MSYS/busybox) installed, its
    # usr\bin\find.exe comes FIRST on PATH.  GNU find treats " <pid> " as a path,
    # fails, and returns non-zero, so "if errorlevel 1 goto afterwait" concluded
    # the app had already exited and the wait loop became a no-op.  The updater
    # then mirrored over a RUNNING install: exe locked, retries, and on a slow
    # exit a rollback.  The 30-second taskkill never fired either, because the
    # loop never looped.
    "set \"kqFind=find\"\r\n"
    "if exist \"%SystemRoot%\\Sysnative\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\Sysnative\\find.exe\"\r\n"
    ") else if exist \"%SystemRoot%\\System32\\find.exe\" (\r\n"
    "    set \"kqFind=%SystemRoot%\\System32\\find.exe\"\r\n"
    ")\r\n"
    "set \"kqWaitSec=0\"\r\n"
    ":waitloop\r\n"
    "tasklist /FI \"PID eq %kqPid%\" 2>NUL | \"%kqFind%\" \" %kqPid% \" >NUL\r\n"
    "if errorlevel 1 goto afterwait\r\n"
    "set /a kqWaitSec+=1\r\n"
    "if %kqWaitSec% geq 30 (\r\n"
    "    echo [Fallback] Process %kqPid% still running after 30s, forcing close. >> \"%kqLog%\"\r\n"
    "    taskkill /F /PID %kqPid% >NUL 2>&1\r\n"
    "    ping -n 2 127.0.0.1 >NUL\r\n"
    "    goto afterwait\r\n"
    ")\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto waitloop\r\n"
    ":afterwait\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Extracting update zip. >> \"%kqLog%\"\r\n"
    "if not exist \"%kqExtract%\" mkdir \"%kqExtract%\"\r\n"
    "\"%kqTar%\" -xf \"%kqZip%\" -C \"%kqExtract%\"\r\n"
    "if errorlevel 1 (\r\n"
    "    echo [Fallback %date% %time%] tar extraction failed. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 1\r\n"
    ")\r\n"
    # Verify the payload BEFORE the destructive mirror.  Without this a zip that
    # extracted a KeyQuest folder but no usable exe still ran /MIR over the live
    # install, and the old exe was then started against a new file tree.  The
    # primary launcher has always checked this; the fallback did not.
    "if not exist \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" (\r\n"
    "    echo [Fallback %date% %time%] Extraction produced no KeyQuest.exe. Nothing applied. Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "    exit /b 2\r\n"
    ")\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Copying files into app directory. >> \"%kqLog%\"\r\n"
    "robocopy \"%kqExtract%\\KeyQuest\" \"%kqApp%\" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP"
    " /XF progress.json KeyQuest.exe keyquest_error.log pending_update.json /XD Sentences updates Backups\r\n"
    "set \"kqRoboExit=%errorlevel%\"\r\n"
    "if %kqRoboExit% geq 8 (\r\n"
    "    echo [Fallback %date% %time%] Robocopy failed with code %kqRoboExit%. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=%kqRoboExit%\"\r\n"
    "    goto rollback\r\n"
    ")\r\n"
    # The primary launcher has always verified the applied tree after the
    # mirror; the fallback only checked the payload beforehand.  A zip whose
    # KeyQuest folder holds an exe but no modules tree therefore mirrored
    # cleanly, deleted the live modules, and started the broken result.
    "if not exist \"%kqApp%\\modules\\version.py\" (\r\n"
    "    echo [Fallback %date% %time%] Update did not produce expected app structure. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=3\"\r\n"
    "    goto rollback\r\n"
    ")\r\n"
    # Retry-and-roll-back on a locked exe, matching the primary launcher.  This
    # copy used to be fire-and-forget: a briefly locked exe (an AV scan is the
    # classic cause) left the OLD exe running against the NEW file tree, and the
    # script still exited 0.
    "if defined KEYQUEST_UPDATER_SKIP_EXE_COPY goto skipexe\r\n"
    "set \"kqWait=0\"\r\n"
    ":copyexe\r\n"
    "copy /Y \"%kqExtract%\\KeyQuest\\KeyQuest.exe\" \"%kqApp%\\KeyQuest.exe\" >NUL 2>&1\r\n"
    "if not errorlevel 1 goto exedone\r\n"
    "set /a kqWait+=1\r\n"
    "if %kqWait% geq 15 (\r\n"
    "    echo [Fallback %date% %time%] KeyQuest.exe replacement failed after 15 retries. Rolling back. >> \"%kqLog%\"\r\n"
    "    set \"kqFailCode=32\"\r\n"
    "    goto rollback\r\n"
    ")\r\n"
    "echo [Fallback %date% %time%] KeyQuest.exe locked, retrying. >> \"%kqLog%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto copyexe\r\n"
    ":exedone\r\n"
    "echo [Fallback %date% %time%] KeyQuest.exe replacement succeeded. >> \"%kqLog%\"\r\n"
    ":skipexe\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Starting KeyQuest. >> \"%kqLog%\"\r\n"
    "start \"\" \"%kqExe%\"\r\n"
    "exit /b 0\r\n"
    "\r\n"
    ":rollback\r\n"
    "echo [Fallback %date% %time%] Update failed (code %kqFailCode%). Restoring previous version. >> \"%kqLog%\"\r\n"
    "if not defined kqBackupZip (\r\n"
    "    echo [Fallback %date% %time%] ROLLBACK UNAVAILABLE: no snapshot was taken. Restarting current files. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    "if not exist \"%kqBackupZip%\" (\r\n"
    "    echo [Fallback %date% %time%] ROLLBACK UNAVAILABLE: no snapshot at \"%kqBackupZip%\". Restarting current files. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    "echo [Fallback %date% %time%] Restoring backup from \"%kqBackupZip%\". >> \"%kqLog%\"\r\n"
    "set \"kqRestoreTry=0\"\r\n"
    "set \"kqTarExit=0\"\r\n"
    ":restoreloop\r\n"
    # Extract to a staging dir and MIRROR it back, rather than extracting on top
    # of the app.  Overlaying restores old files but cannot remove files that
    # only the new release introduced, so a "successful" rollback still left a
    # mixed old/new tree running under the old exe.
    "if exist \"%kqRestore%\" rmdir /s /q \"%kqRestore%\"\r\n"
    "mkdir \"%kqRestore%\"\r\n"
    "\"%kqTar%\" -xf \"%kqBackupZip%\" -C \"%kqRestore%\" >> \"%kqLog%\" 2>&1\r\n"
    "set \"kqTarExit=%errorlevel%\"\r\n"
    "if %kqTarExit% neq 0 goto restoreretry\r\n"
    "if not exist \"%kqRestore%\\modules\\version.py\" goto restoreretry\r\n"
    # Mirror only when the snapshot is a COMPLETE record of the old install.
    # /MIR deletes whatever the snapshot does not contain, which is what makes
    # rollback exact -- but against an incomplete snapshot it would delete a
    # file it has no copy of, which is worse than the mixed tree the old overlay
    # restore left behind.  create_app_backup_zip writes the marker only when it
    # captured every file.  Plain top-level lines, no if-blocks: a parenthesised
    # construct in this routine has already broken it once.
    "set \"kqRestoreMode=/E\"\r\n"
    "if exist \"%kqRestore%\\.kq_snapshot_complete\" set \"kqRestoreMode=/MIR\"\r\n"
    "echo [Updater %date% %time%] Restore mode %kqRestoreMode% (/MIR = snapshot complete). >> \"%kqLog%\"\r\n"
    "robocopy \"%kqRestore%\" \"%kqApp%\" %kqRestoreMode% /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XF progress.json KeyQuest.exe keyquest_error.log pending_update.json .kq_snapshot_complete /XD Sentences updates Backups >> \"%kqLog%\" 2>&1\r\n"
    "set \"kqRoboBack=%errorlevel%\"\r\n"
    "if %kqRoboBack% geq 8 goto restoreretry\r\n"
    "if not exist \"%kqApp%\\modules\\version.py\" goto restoreretry\r\n"
    "echo [Fallback %date% %time%] Backup restored. >> \"%kqLog%\"\r\n"
    "set \"kqRollbackOk=1\"\r\n"
    "goto rollbackrestart\r\n"
    ":restoreretry\r\n"
    "set /a kqRestoreTry+=1\r\n"
    "if %kqRestoreTry% geq 10 (\r\n"
    "    echo [Fallback %date% %time%] ROLLBACK FAILED after 10 attempts, last tar exit %kqTarExit%. Install may be inconsistent. Restarting anyway. >> \"%kqLog%\"\r\n"
    "    goto rollbackrestart\r\n"
    ")\r\n"
    "echo [Fallback %date% %time%] Backup restore attempt %kqRestoreTry% failed (tar exit %kqTarExit%), retrying. >> \"%kqLog%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "goto restoreloop\r\n"
    ":rollbackrestart\r\n"
    "if exist \"%kqRestore%\" rmdir /s /q \"%kqRestore%\"\r\n"
    "echo [Fallback %date% %time%] Rollback verified: %kqRollbackOk% where 1 means the snapshot was restored. >> \"%kqLog%\"\r\n"
    "echo [Fallback %date% %time%] Restarting KeyQuest after rollback. >> \"%kqLog%\"\r\n"
    "if exist \"%kqExe%\" start \"\" \"%kqExe%\"\r\n"
    "exit /b %kqFailCode%\r\n"
)


def create_portable_fallback_bat(
    zip_path: Path,
    app_dir: str,
    app_exe_path: str,
    current_pid: int,
    bat_path: Path | None = None,
    backup_zip_path: Path | None = None,
) -> Path:
    """Write a pure .bat fallback for portable updates that uses tar and robocopy.

    Unlike the main launcher this has no PowerShell dependency, making it
    suitable as a second-chance path when the primary PowerShell launcher fails.
    Requires Windows 10 v1803+ (tar built-in) and robocopy (Vista+).

    When *backup_zip_path* points to a pre-update snapshot, a failed mirror is
    rolled back from that snapshot before restarting.
    """
    bat_path = bat_path or (zip_path.parent / "run_keyquest_portable_fallback.bat")
    extract_dir = zip_path.parent / "portable_fallback_extract"
    restore_dir = zip_path.parent / "portable_fallback_restore"
    bat_text = fill_bat_template(
        _PORTABLE_FALLBACK_BAT_TEMPLATE, {
            "__TARGET_PID__": str(int(current_pid)),
            "__ZIP_PATH__": bat_value(zip_path),
            "__APP_DIR__": bat_value(app_dir),
            "__APP_EXE__": bat_value(app_exe_path),
            "__EXTRACT_DIR__": bat_value(extract_dir),
            "__RESTORE_DIR__": bat_value(restore_dir),
            "__BACKUP_ZIP__": bat_value(backup_zip_path) if backup_zip_path else "",
        }
    )
    return _write_bat(bat_path, bat_text)


_INSTALLER_FALLBACK_BAT_TEMPLATE = (
    "@echo off\r\n"
    # Explicitly DISABLED, not merely "not enabled".  Delayed expansion can be
    # turned on globally via the Command Processor registry setting, and a plain
    # "setlocal" inherits it -- at which case a path containing a matched pair
    # like !TEMP! is expanded while the line is parsed.  Verified with cmd /v:on.
    "setlocal disabledelayedexpansion\r\n"
    "set \"kqInstaller=__INSTALLER__\"\r\n"
    "set \"kqApp=__APP_DIR__\"\r\n"
    "set \"kqExe=__APP_EXE__\"\r\n"
    "set \"kqLog=__APP_DIR__\\keyquest_error.log\"\r\n"
    "\r\n"
    "echo [Fallback %date% %time%] Silent installer fallback started. >> \"%kqLog%\"\r\n"
    # No PID wait / no find here: the installer's own /CLOSEAPPLICATIONS closes a
    # still-running KeyQuest, so this path has zero console-filter dependency.
    "ping -n 4 127.0.0.1 >NUL\r\n"
    "echo [Fallback %date% %time%] Running installer silently. >> \"%kqLog%\"\r\n"
    "\"%kqInstaller%\" /CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS \"/DIR=%kqApp%\"\r\n"
    "set \"kqInstallExit=%errorlevel%\"\r\n"
    "echo [Fallback %date% %time%] Installer exited with code %kqInstallExit%. >> \"%kqLog%\"\r\n"
    "ping -n 2 127.0.0.1 >NUL\r\n"
    "if exist \"%kqExe%\" (\r\n"
    "    echo [Fallback %date% %time%] Restarting KeyQuest. >> \"%kqLog%\"\r\n"
    "    start \"\" \"%kqExe%\"\r\n"
    ")\r\n"
    # Only delete the installer when it actually succeeded.  This is the
    # last-resort path: the file was deliberately staged where the user can
    # reach it, and the post-restart "did not apply" message tells them to run
    # it by hand.  Deleting it on failure removed the very file that message
    # points at.
    "if %kqInstallExit% equ 0 (\r\n"
    "    if exist \"%kqInstaller%\" del /F \"%kqInstaller%\" >NUL 2>&1\r\n"
    ") else (\r\n"
    "    echo [Fallback %date% %time%] Installer kept at \"%kqInstaller%\" for manual retry. >> \"%kqLog%\"\r\n"
    ")\r\n"
    "echo [Fallback %date% %time%] Silent installer fallback finished. >> \"%kqLog%\"\r\n"
    "exit /b %kqInstallExit%\r\n"
)


def create_installer_fallback_bat(
    installer_path: Path,
    app_dir: str,
    app_exe_path: str,
    bat_path: Path | None = None,
) -> Path:
    """Write a silent, windowless ``.bat`` that runs the Inno installer and relaunches.

    Used as the last-resort installer apply path when the primary launcher could
    not be started. Unlike the old direct-exe fallback (which popped a visible
    installer wizard and never relaunched the app), this runs the installer
    ``/VERYSILENT`` and restarts KeyQuest itself, with no visible window when
    spawned via ``bat_launcher_creationflags()``. It deliberately uses no
    ``tasklist | find`` PID wait — the installer's ``/CLOSEAPPLICATIONS`` handles a
    still-running app — so it has no console-filter dependency at all.
    """
    bat_path = bat_path or (installer_path.parent / "run_keyquest_installer_fallback.bat")
    if bat_path.suffix.lower() != ".bat":
        bat_path = bat_path.with_suffix(".bat")
    bat_text = fill_bat_template(
        _INSTALLER_FALLBACK_BAT_TEMPLATE, {
            "__INSTALLER__": bat_value(installer_path),
            "__APP_DIR__": bat_value(app_dir),
            "__APP_EXE__": bat_value(app_exe_path),
        }
    )
    return _write_bat(bat_path, bat_text)


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
