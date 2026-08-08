"""Repeatable local end-to-end updater integration test for installer and portable paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import sentence_merge, update_manager  # noqa: E402


ARTIFACT_ROOT = ROOT / "tests" / "logs" / "local_updater"
# Deliberately OUTSIDE ARTIFACT_ROOT, which is wiped at the start of every run.
# The two PyInstaller builds dominate the runtime, and a harness nobody runs
# because it is slow protects nothing.
BUILD_CACHE_ROOT = ROOT / "tests" / "logs" / "updater_build_cache"
BUILD_ROOT = ARTIFACT_ROOT / "build"
FIXTURE_DIST = BUILD_ROOT / "fixture_app_dist"
FIXTURE_WORK = BUILD_ROOT / "fixture_app_work"
INSTALLER_DIST = BUILD_ROOT / "installer_dist"
INSTALLER_WORK = BUILD_ROOT / "installer_work"
FEED_ROOT = ARTIFACT_ROOT / "feed"
APP_DIR = ARTIFACT_ROOT / "installed_app"
PORTABLE_APP_DIR = ARTIFACT_ROOT / "portable_app"
NEW_PAYLOAD_ROOT = ARTIFACT_ROOT / "new_payload"
DOWNLOADS_DIR = ARTIFACT_ROOT / "downloads"
REPORT_PATH = ARTIFACT_ROOT / "REPORT.md"
RESULT_JSON_PATH = ARTIFACT_ROOT / "result.json"
STRICT_REPORT_PATH = ARTIFACT_ROOT / "REPORT_strict_portable.md"
STRICT_RESULT_JSON_PATH = ARTIFACT_ROOT / "result_strict_portable.json"
OLD_BOOT_PATH = APP_DIR / "old_boot.json"
NEW_BOOT_PATH = APP_DIR / "updater_boot.json"
PORTABLE_OLD_BOOT_PATH = PORTABLE_APP_DIR / "old_boot.json"
PORTABLE_NEW_BOOT_PATH = PORTABLE_APP_DIR / "updater_boot.json"
INSTALLER_TRACE_PATH = APP_DIR / "fake_installer_trace.json"
# Fallback and rollback paths get their own app dirs so each phase starts from a
# clean, known-good install rather than inheriting whatever the previous phase
# left behind.
FALLBACK_APP_DIR = ARTIFACT_ROOT / "portable_fallback_app"
ROLLBACK_APP_DIR = ARTIFACT_ROOT / "portable_rollback_app"
INSTALLER_FALLBACK_APP_DIR = ARTIFACT_ROOT / "installer_fallback_app"

USER_PROGRESS = '{"lessons_done": 42, "do_not_lose_me": true}'
USER_SENTENCE = "A sentence the user edited themselves.\n"
# Must match what _seed_fixture_tree writes into a payload tree.
SHIPPED_SENTENCE = "The quick brown fox.\n"
OLD_BUILD_ID = "oldbuild001"
NEW_BUILD_ID = "newbuild002"
OLD_VERSION = "1.8.9"
NEW_VERSION = "1.9.1"
RELEASE_TAG = f"v{NEW_VERSION}"
INSTALLER_NAME = update_manager.INSTALLER_NAME
PORTABLE_NAME = update_manager.PORTABLE_ZIP_NAME


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str = ""


def _clean_dir(path: Path) -> None:
    def _onerror(func, failed_path, exc_info):
        try:
            os.chmod(failed_path, stat.S_IWRITE)
            func(failed_path)
        except FileNotFoundError:
            return

    if path.exists():
        shutil.rmtree(path, onerror=_onerror)
    path.mkdir(parents=True, exist_ok=True)


def _detect_home_dir() -> Path:
    for candidate in (
        os.environ.get("USERPROFILE"),
        os.environ.get("HOME"),
        os.environ.get("HOMEDRIVE", "") + os.environ.get("HOMEPATH", ""),
    ):
        if candidate:
            return Path(candidate)
    return ROOT


def _prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    home_dir = _detect_home_dir()
    home_drive = home_dir.drive or "C:"
    env.setdefault("USERPROFILE", str(home_dir))
    env.setdefault("HOME", str(home_dir))
    env.setdefault("HOMEDRIVE", home_drive)
    env.setdefault("HOMEPATH", str(home_dir).replace(home_drive, "", 1))
    env.setdefault("LOCALAPPDATA", str(home_dir / "AppData" / "Local"))
    return env


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _wait_for_path(path: Path, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def _wait_for_boot_version(path: Path, version: str, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.2)
                continue
            if str(payload.get("version")) == version:
                return True
        time.sleep(0.2)
    return False


def _build_cache_key(script_path: Path, name: str) -> str:
    """Cache identity: the script bytes, the exe name, and the interpreter."""
    digest = hashlib.sha256()
    digest.update(script_path.read_bytes())
    digest.update(name.encode("utf-8"))
    digest.update(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}".encode())
    return digest.hexdigest()[:16]


def _build_pyinstaller_exe(
    script_path: Path, dist_dir: Path, work_dir: Path, name: str, *, use_cache: bool = True
) -> Path:
    cache_key = _build_cache_key(script_path, name)
    cached = BUILD_CACHE_ROOT / cache_key / f"{name}.exe"
    target = dist_dir / f"{name}.exe"
    if use_cache and cached.exists():
        dist_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, target)
        return target

    env = _prepare_env()
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir = work_dir / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "py",
            "-3.11",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            name,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--exclude-module",
            "pkg_resources",
            "--exclude-module",
            "setuptools",
            "--exclude-module",
            "jaraco",
            str(script_path),
        ],
        env=env,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PyInstaller failed for {name}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    exe_path = dist_dir / f"{name}.exe"
    if not exe_path.exists():
        raise RuntimeError(f"Expected built executable not found: {exe_path}")
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_path, cached)
    except OSError:
        pass  # caching is an optimisation, never a requirement
    return exe_path


def _write_fixture_variant(build_id: str) -> Path:
    """Write a copy of the fixture script carrying a distinct ``BUILD_ID``.

    The harness used to build ONE fixture exe and copy it into both the old tree
    and the update payload, while every version assertion read the adjacent
    ``modules/version.py``.  That meant deleting the exe-replacement step
    entirely would still pass, because nothing ever compared the executables.
    Two variants make "was the exe actually replaced?" an answerable question.
    """
    source = (ROOT / "tests" / "updater_fixture_app.py").read_text(encoding="utf-8")
    updated = source.replace('BUILD_ID = "dev"', f'BUILD_ID = "{build_id}"', 1)
    if updated == source:
        raise RuntimeError("Could not stamp BUILD_ID into the fixture script.")
    target = BUILD_ROOT / f"fixture_app_{build_id}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    return target


def _write_version_file(app_root: Path, version: str) -> None:
    modules_dir = app_root / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    (modules_dir / "version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")


def _seed_fixture_tree(app_root: Path, fixture_exe: Path, version: str, *, include_sentences: bool = True) -> None:
    app_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_exe, app_root / "KeyQuest.exe")
    _write_version_file(app_root, version)
    (app_root / "games").mkdir(exist_ok=True)
    if include_sentences:
        (app_root / "Sentences").mkdir(exist_ok=True)
        (app_root / "Sentences" / "English.txt").write_text("The quick brown fox.\n", encoding="utf-8")


def _build_fake_installer_script(script_path: Path, payload_root: Path) -> None:
    payload_keyquest = payload_root / "KeyQuest"
    script_path.write_text(
        textwrap.dedent(
            f"""
            from __future__ import annotations

            import json
            import os
            import shutil
            import sys
            import time
            from pathlib import Path


            PAYLOAD_ROOT = Path(r"{payload_keyquest}")


            def parse_dir_arg(argv: list[str]) -> Path | None:
                for arg in argv:
                    if arg.lower().startswith("/dir="):
                        value = arg.split("=", 1)[1].strip().strip('"')
                        if value:
                            return Path(value)
                return None


            def read_version(app_dir: Path) -> str:
                namespace: dict[str, str] = {{}}
                exec((app_dir / "modules" / "version.py").read_text(encoding="utf-8"), namespace)
                return str(namespace.get("__version__", "0.0.0"))


            def copy_payload(source_root: Path, target_root: Path) -> None:
                for source in source_root.rglob("*"):
                    relative = source.relative_to(source_root)
                    destination = target_root / relative
                    if source.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(source, destination)
                    except PermissionError:
                        if source.name.lower() == "keyquest.exe" and destination.exists():
                            continue
                        raise


            def main() -> int:
                target_dir = parse_dir_arg(sys.argv[1:])
                if target_dir is None:
                    raise SystemExit("Missing /DIR= target")
                target_dir.mkdir(parents=True, exist_ok=True)
                copy_payload(PAYLOAD_ROOT, target_dir)
                trace_path = target_dir / "fake_installer_trace.json"
                trace_path.write_text(
                    json.dumps(
                        {{
                            "argv": sys.argv[1:],
                            "payload_root": str(PAYLOAD_ROOT),
                            "target_dir": str(target_dir),
                            "installed_version": read_version(target_dir),
                            "timestamp": time.time(),
                        }},
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _prepare_feed(installer_exe: Path, portable_zip: Path) -> Path:
    FEED_ROOT.mkdir(parents=True, exist_ok=True)
    installer_target = FEED_ROOT / INSTALLER_NAME
    portable_target = FEED_ROOT / PORTABLE_NAME
    shutil.copy2(installer_exe, installer_target)
    shutil.copy2(portable_zip, portable_target)

    installer_sha = _sha256(installer_target)
    portable_sha = _sha256(portable_target)
    (FEED_ROOT / f"{INSTALLER_NAME}.sha256").write_text(
        f"{installer_sha}  {INSTALLER_NAME}\n",
        encoding="utf-8",
    )
    (FEED_ROOT / f"{PORTABLE_NAME}.sha256").write_text(
        f"{portable_sha}  {PORTABLE_NAME}\n",
        encoding="utf-8",
    )

    release = {
        "tag_name": RELEASE_TAG,
        "name": f"KeyQuest {NEW_VERSION} Local Test",
        "body": "Local updater integration test feed.",
        "assets": [
            {
                "name": INSTALLER_NAME,
                "browser_download_url": installer_target.resolve().as_uri(),
                "size": installer_target.stat().st_size,
            },
            {
                "name": f"{INSTALLER_NAME}.sha256",
                "browser_download_url": (FEED_ROOT / f"{INSTALLER_NAME}.sha256").resolve().as_uri(),
                "size": (FEED_ROOT / f"{INSTALLER_NAME}.sha256").stat().st_size,
            },
            {
                "name": PORTABLE_NAME,
                "browser_download_url": portable_target.resolve().as_uri(),
                "size": portable_target.stat().st_size,
            },
            {
                "name": f"{PORTABLE_NAME}.sha256",
                "browser_download_url": (FEED_ROOT / f"{PORTABLE_NAME}.sha256").resolve().as_uri(),
                "size": (FEED_ROOT / f"{PORTABLE_NAME}.sha256").stat().st_size,
            },
        ],
    }
    release_path = FEED_ROOT / "release.json"
    release_path.write_text(json.dumps(release, indent=2, sort_keys=True), encoding="utf-8")
    return release_path


def _write_report(
    steps: list[StepResult],
    summary: str,
    error_text: str = "",
    *,
    strict_portable: bool = False,
) -> None:
    report_path = STRICT_REPORT_PATH if strict_portable else REPORT_PATH
    result_json_path = STRICT_RESULT_JSON_PATH if strict_portable else RESULT_JSON_PATH
    passed = sum(1 for step in steps if step.passed)
    total = len(steps)
    lines = [
        "# Local Updater Integration Report",
        "",
        f"Summary: {summary}",
        "",
        f"Passed: {passed}/{total}",
        "",
        "## Steps",
        "",
    ]
    for step in steps:
        status = "PASS" if step.passed else "FAIL"
        lines.append(f"- {status}: {step.name}")
        if step.detail:
            lines.append(f"  Detail: {step.detail}")
    if error_text:
        lines.extend(
            [
                "",
                "## Error",
                "",
                "```text",
                error_text.rstrip(),
                "```",
            ]
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result_json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "passed": passed,
                "total": total,
                "steps": [asdict(step) for step in steps],
                "error": error_text,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    # Strict is the DEFAULT. A run that skips the exe copy should never be the
    # thing anyone reports as updater assurance, and the old default did exactly
    # that while reading its version from a text file beside the exe.
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            "Diagnostic mode: re-enable the test-only portable overrides (Python zip "
            "extraction, skip the exe replacement). Faster, but proves less. Not for "
            "release verification."
        ),
    )
    parser.add_argument(
        "--strict-portable",
        action="store_true",
        help="Accepted for compatibility; strict is now the default and this is a no-op.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Ignore the cached fixture builds and rebuild them from scratch.",
    )
    return parser.parse_args()


def _sweep_mei_temp_dirs(since: float, attempts: int = 3) -> int:
    """Remove leftover PyInstaller onefile ``_MEI`` temp dirs created during this run.

    The onefile fixture exes built here extract to ``%TEMP%/_MEI<pid>`` and are
    force-killed mid-update, so they never delete their own temp dirs. Only
    directories modified at/after ``since`` are removed, so a concurrently running
    onefile app's live temp dir (older than this run) is never touched. A
    just-killed fixture may briefly hold a lock, so removal is retried a few times.
    Returns the number of directories removed.
    """
    removed = 0
    temp_root = Path(tempfile.gettempdir())
    cutoff = since - 2.0  # small slack for filesystem timestamp granularity
    for attempt in range(attempts):
        try:
            candidates = [p for p in temp_root.glob("_MEI*") if p.is_dir()]
        except OSError:
            return removed
        pending: list[Path] = []
        for path in candidates:
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            shutil.rmtree(path, ignore_errors=True)
            if path.exists():
                pending.append(path)
            else:
                removed += 1
        if not pending or attempt == attempts - 1:
            break
        time.sleep(0.5)
    return removed


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        args = _parse_args()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--fast", action="store_true")
        parser.add_argument("--strict-portable", action="store_true")
        parser.add_argument("--rebuild", action="store_true")
        args = parser.parse_args(argv)
    strict = not getattr(args, "fast", False)
    use_cache = not getattr(args, "rebuild", False)
    steps: list[StepResult] = []
    old_process: subprocess.Popen[str] | None = None
    launcher_process: subprocess.Popen[str] | None = None
    error_text = ""
    run_start = time.time()
    try:
        _clean_dir(ARTIFACT_ROOT)
        BUILD_ROOT.mkdir(parents=True, exist_ok=True)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        if strict:
            os.environ.pop(update_manager.UPDATER_TEST_PYTHON_ENV, None)
            os.environ.pop(update_manager.UPDATER_TEST_SKIP_EXE_COPY_ENV, None)
            steps.append(
                StepResult(
                    "portable strict mode enabled",
                    True,
                    "Portable test-only overrides disabled.",
                )
            )
        else:
            os.environ[update_manager.UPDATER_TEST_PYTHON_ENV] = sys.executable
            os.environ[update_manager.UPDATER_TEST_SKIP_EXE_COPY_ENV] = "1"

        # Two genuinely different binaries, so "was the exe replaced?" can be
        # answered by comparing hashes rather than inferred from a version file
        # sitting next to it.
        fixture_exe = _build_pyinstaller_exe(
            _write_fixture_variant(OLD_BUILD_ID),
            FIXTURE_DIST / "old",
            FIXTURE_WORK / "old",
            "KeyQuest",
            use_cache=use_cache,
        )
        new_fixture_exe = _build_pyinstaller_exe(
            _write_fixture_variant(NEW_BUILD_ID),
            FIXTURE_DIST / "new",
            FIXTURE_WORK / "new",
            "KeyQuest",
            use_cache=use_cache,
        )
        old_exe_sha = _sha256(fixture_exe)
        new_exe_sha = _sha256(new_fixture_exe)
        steps.append(
            StepResult(
                "build two distinguishable fixture apps",
                fixture_exe.exists() and new_fixture_exe.exists() and old_exe_sha != new_exe_sha,
                f"old={old_exe_sha[:12]}, new={new_exe_sha[:12]}",
            )
        )

        _seed_fixture_tree(APP_DIR, fixture_exe, OLD_VERSION)
        (APP_DIR / "unins000.exe").write_text("installer marker\n", encoding="utf-8")
        steps.append(
            StepResult(
                "seed old installed app",
                (APP_DIR / "KeyQuest.exe").exists() and (APP_DIR / "modules" / "version.py").exists(),
                str(APP_DIR),
            )
        )

        _seed_fixture_tree(PORTABLE_APP_DIR, fixture_exe, OLD_VERSION)
        # Real user data, so the run can assert it survived rather than assuming.
        # The historical incident here was silent user data loss.
        (PORTABLE_APP_DIR / "progress.json").write_text(USER_PROGRESS, encoding="utf-8")
        (PORTABLE_APP_DIR / "Sentences" / "English.txt").write_text(USER_SENTENCE, encoding="utf-8")
        update_manager.write_pending_update_marker(str(PORTABLE_APP_DIR), NEW_VERSION)
        steps.append(
            StepResult(
                "seed old portable app",
                (PORTABLE_APP_DIR / "KeyQuest.exe").exists() and (PORTABLE_APP_DIR / "modules" / "version.py").exists(),
                str(PORTABLE_APP_DIR),
            )
        )

        payload_keyquest = NEW_PAYLOAD_ROOT / "KeyQuest"
        _seed_fixture_tree(payload_keyquest, new_fixture_exe, NEW_VERSION, include_sentences=True)
        (payload_keyquest / "unins000.exe").write_text("installer marker\n", encoding="utf-8")
        portable_zip = ARTIFACT_ROOT / PORTABLE_NAME
        with zipfile.ZipFile(portable_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in payload_keyquest.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(NEW_PAYLOAD_ROOT))
        steps.append(StepResult("build new payload tree and portable zip", portable_zip.exists(), str(portable_zip)))

        installer_script = BUILD_ROOT / "fake_installer.py"
        _build_fake_installer_script(installer_script, NEW_PAYLOAD_ROOT)
        installer_exe = _build_pyinstaller_exe(
            installer_script,
            INSTALLER_DIST,
            INSTALLER_WORK,
            "KeyQuestSetup",
            use_cache=use_cache,
        )
        steps.append(StepResult("build fake installer exe", installer_exe.exists(), str(installer_exe)))

        release_path = _prepare_feed(installer_exe, portable_zip)
        release_url = release_path.resolve().as_uri()
        steps.append(StepResult("prepare local file feed", release_path.exists(), release_url))
        if strict:
            steps.append(
                StepResult(
                    "disable portable python extractor override",
                    update_manager.UPDATER_TEST_PYTHON_ENV not in os.environ,
                    "unset",
                )
            )
            steps.append(
                StepResult(
                    "disable portable exe-copy skip override",
                    update_manager.UPDATER_TEST_SKIP_EXE_COPY_ENV not in os.environ,
                    "unset",
                )
            )
        else:
            steps.append(StepResult("set portable python extractor override", True, sys.executable))
            steps.append(StepResult("set portable exe-copy skip override", True, "1"))

        layout_ok = update_manager.is_installed_layout(str(APP_DIR)) and not update_manager.is_portable_layout(str(APP_DIR))
        steps.append(
            StepResult(
                "detect installed layout as non-portable",
                layout_ok,
                f"installed={update_manager.is_installed_layout(str(APP_DIR))}, portable={update_manager.is_portable_layout(str(APP_DIR))}",
            )
        )
        portable_layout_ok = update_manager.is_portable_layout(str(PORTABLE_APP_DIR)) and not update_manager.is_installed_layout(str(PORTABLE_APP_DIR))
        steps.append(
            StepResult(
                "detect portable layout correctly",
                portable_layout_ok,
                f"installed={update_manager.is_installed_layout(str(PORTABLE_APP_DIR))}, portable={update_manager.is_portable_layout(str(PORTABLE_APP_DIR))}",
            )
        )

        outcome = update_manager.check_for_update(
            current_version=OLD_VERSION,
            portable=False,
            url=release_url,
            timeout=10,
        )
        update_ok = isinstance(outcome, update_manager.UpdateAvailable) and outcome.asset_name == INSTALLER_NAME
        steps.append(
            StepResult(
                "detect installer update from local feed",
                update_ok,
                getattr(outcome, "asset_name", type(outcome).__name__),
            )
        )
        if not isinstance(outcome, update_manager.UpdateAvailable):
            raise RuntimeError(f"Expected UpdateAvailable, got {type(outcome).__name__}")

        download_path = DOWNLOADS_DIR / update_manager.build_installer_filename(outcome.version)
        downloaded = update_manager.download_file(outcome.download_url, download_path, timeout=20)
        # The primary launcher deletes the installer once it succeeds, so keep a
        # copy for the installer-fallback phase further down.
        installer_for_fallback = DOWNLOADS_DIR / "KeyQuestSetup_fallback_copy.exe"
        shutil.copy2(downloaded, installer_for_fallback)
        sha_asset = update_manager.select_sha256_asset(outcome.release, outcome.asset_name)
        expected_hash = update_manager.fetch_sha256_for_asset(sha_asset or {}, timeout=20) if sha_asset else None
        hash_ok = bool(expected_hash) and update_manager.verify_file_sha256(downloaded, expected_hash or "")
        steps.append(
            StepResult(
                "download installer and verify sha256",
                downloaded.exists() and hash_ok,
                f"downloaded={downloaded.exists()}, sha_ok={hash_ok}",
            )
        )

        old_process = subprocess.Popen(
            [str(APP_DIR / "KeyQuest.exe"), "--hold-seconds", "3", "--boot-file", OLD_BOOT_PATH.name],
            cwd=str(APP_DIR),
            close_fds=True,
        )
        old_boot_ok = _wait_for_path(OLD_BOOT_PATH, 10)
        steps.append(StepResult("launch old installed build", old_boot_ok, f"pid={old_process.pid}"))
        if not old_boot_ok:
            raise RuntimeError("Old build did not create its boot marker.")

        launcher_path = update_manager.create_update_launcher(
            installer_path=downloaded,
            app_dir=str(APP_DIR),
            app_exe_path=str(APP_DIR / "KeyQuest.exe"),
            current_pid=old_process.pid,
            script_path=DOWNLOADS_DIR / "run_keyquest_update.bat",
        )
        launcher_process = subprocess.Popen(
            ["cmd", "/c", str(launcher_path)],
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        launcher_return = launcher_process.wait(timeout=90)
        # Popen.wait returns an int or raises, so the old 'is not None' check was
        # always true. It is the assertion that should have caught the unpinned
        # find making the wait loop a no-op, and it caught nothing.
        old_exit_code = old_process.wait(timeout=20)
        old_exit_ok = old_exit_code == 0
        steps.append(
            StepResult(
                "run update launcher and stop old process",
                old_exit_ok and launcher_return in (0, 1),
                f"launcher_exit={launcher_return}, old_exit={old_exit_code}",
            )
        )

        installer_trace_ok = _wait_for_path(INSTALLER_TRACE_PATH, 15)
        steps.append(
            StepResult(
                "apply installer payload",
                installer_trace_ok and (APP_DIR / "modules" / "version.py").exists(),
                str(INSTALLER_TRACE_PATH),
            )
        )
        if not installer_trace_ok:
            raise RuntimeError("Installer trace file was not created.")

        new_boot_ok = _wait_for_boot_version(NEW_BOOT_PATH, NEW_VERSION, 30)
        version_result = _run([str(APP_DIR / "KeyQuest.exe"), "--version"], cwd=APP_DIR, timeout=15)
        final_version = (version_result.stdout or "").strip()
        steps.append(
            StepResult(
                "relaunch into new version",
                new_boot_ok and final_version == NEW_VERSION,
                f"boot_ok={new_boot_ok}, version={final_version!r}",
            )
        )

        portable_outcome = update_manager.check_for_update(
            current_version=OLD_VERSION,
            portable=True,
            url=release_url,
            timeout=10,
        )
        portable_update_ok = isinstance(portable_outcome, update_manager.UpdateAvailable) and portable_outcome.asset_name == PORTABLE_NAME
        steps.append(
            StepResult(
                "detect portable update from local feed",
                portable_update_ok,
                getattr(portable_outcome, "asset_name", type(portable_outcome).__name__),
            )
        )
        if not isinstance(portable_outcome, update_manager.UpdateAvailable):
            raise RuntimeError(f"Expected portable UpdateAvailable, got {type(portable_outcome).__name__}")

        portable_download_path = DOWNLOADS_DIR / update_manager.build_portable_zip_filename(portable_outcome.version)
        downloaded_portable = update_manager.download_file(portable_outcome.download_url, portable_download_path, timeout=20)
        # Same reason: the portable launcher deletes the zip after applying it.
        portable_for_fallback = DOWNLOADS_DIR / "KeyQuest-win64_fallback_copy.zip"
        shutil.copy2(downloaded_portable, portable_for_fallback)
        portable_sha_asset = update_manager.select_sha256_asset(portable_outcome.release, portable_outcome.asset_name)
        portable_expected_hash = (
            update_manager.fetch_sha256_for_asset(portable_sha_asset or {}, timeout=20) if portable_sha_asset else None
        )
        portable_hash_ok = bool(portable_expected_hash) and update_manager.verify_file_sha256(
            downloaded_portable,
            portable_expected_hash or "",
        )
        steps.append(
            StepResult(
                "download portable zip and verify sha256",
                downloaded_portable.exists() and portable_hash_ok,
                f"downloaded={downloaded_portable.exists()}, sha_ok={portable_hash_ok}",
            )
        )

        old_process = subprocess.Popen(
            [str(PORTABLE_APP_DIR / "KeyQuest.exe"), "--hold-seconds", "3", "--boot-file", PORTABLE_OLD_BOOT_PATH.name],
            cwd=str(PORTABLE_APP_DIR),
            close_fds=True,
        )
        portable_old_boot_ok = _wait_for_path(PORTABLE_OLD_BOOT_PATH, 10)
        steps.append(StepResult("launch old portable build", portable_old_boot_ok, f"pid={old_process.pid}"))
        if not portable_old_boot_ok:
            raise RuntimeError("Old portable build did not create its boot marker.")

        launcher_path = update_manager.create_portable_update_launcher(
            zip_path=downloaded_portable,
            app_dir=str(PORTABLE_APP_DIR),
            app_exe_path=str(PORTABLE_APP_DIR / "KeyQuest.exe"),
            current_pid=old_process.pid,
            script_path=DOWNLOADS_DIR / "run_keyquest_portable_update.bat",
        )
        launcher_process = subprocess.Popen(
            ["cmd", "/c", str(launcher_path)],
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        launcher_return = launcher_process.wait(timeout=90)
        # Popen.wait returns an int or raises, so the old 'is not None' check was
        # always true. It is the assertion that should have caught the unpinned
        # find making the wait loop a no-op, and it caught nothing.
        old_exit_code = old_process.wait(timeout=20)
        old_exit_ok = old_exit_code == 0
        steps.append(
            StepResult(
                "run portable update launcher and stop old process",
                old_exit_ok and launcher_return in (0, 1),
                f"launcher_exit={launcher_return}, old_exit={old_exit_code}",
            )
        )

        portable_new_boot_ok = _wait_for_boot_version(PORTABLE_NEW_BOOT_PATH, NEW_VERSION, 30)
        portable_version_result = _run([str(PORTABLE_APP_DIR / "KeyQuest.exe"), "--version"], cwd=PORTABLE_APP_DIR, timeout=15)
        portable_final_version = (portable_version_result.stdout or "").strip()
        steps.append(
            StepResult(
                "relaunch portable app into new version",
                portable_new_boot_ok and portable_final_version == NEW_VERSION,
                f"boot_ok={portable_new_boot_ok}, version={portable_final_version!r}",
            )
        )

        # ------------------------------------------------------------------
        # Fallback layer 2: the portable direct-apply bat.
        #
        # Until now nothing exercised the fallback layers end to end, which is
        # where several reliability fixes live (the post-mirror structure check
        # and the exe retry, both added after review).  Same fixture exe, same
        # real process stop-and-restart as the happy path above.
        # ------------------------------------------------------------------
        _clean_dir(FALLBACK_APP_DIR)
        _seed_fixture_tree(FALLBACK_APP_DIR, fixture_exe, OLD_VERSION)
        fallback_new_boot = FALLBACK_APP_DIR / "updater_boot.json"
        fallback_old_boot = FALLBACK_APP_DIR / "old_boot.json"

        old_process = subprocess.Popen(
            [str(FALLBACK_APP_DIR / "KeyQuest.exe"), "--hold-seconds", "3", "--boot-file", fallback_old_boot.name],
            cwd=str(FALLBACK_APP_DIR),
            close_fds=True,
        )
        fallback_boot_ok = _wait_for_path(fallback_old_boot, 10)
        steps.append(StepResult("launch old build for portable fallback", fallback_boot_ok, f"pid={old_process.pid}"))
        if not fallback_boot_ok:
            raise RuntimeError("Old build did not start for the portable fallback phase.")

        (FALLBACK_APP_DIR / "Sentences" / "English.txt").write_text(USER_SENTENCE, encoding="utf-8")
        fallback_backup = update_manager.create_app_backup_zip(str(FALLBACK_APP_DIR), OLD_VERSION)
        fallback_bat = update_manager.create_portable_fallback_bat(
            zip_path=portable_for_fallback,
            app_dir=str(FALLBACK_APP_DIR),
            app_exe_path=str(FALLBACK_APP_DIR / "KeyQuest.exe"),
            current_pid=old_process.pid,
            bat_path=DOWNLOADS_DIR / "run_keyquest_portable_fallback.bat",
            backup_zip_path=fallback_backup,
        )
        launcher_process = subprocess.Popen(
            update_manager.quote_bat_command(fallback_bat),
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        fallback_return = launcher_process.wait(timeout=120)
        old_process.wait(timeout=20)
        fallback_applied = _wait_for_boot_version(fallback_new_boot, NEW_VERSION, 30)
        fallback_version = (_run([str(FALLBACK_APP_DIR / "KeyQuest.exe"), "--version"], cwd=FALLBACK_APP_DIR, timeout=15).stdout or "").strip()
        steps.append(
            StepResult(
                "portable fallback applies update and relaunches",
                fallback_applied and fallback_version == NEW_VERSION,
                f"exit={fallback_return}, boot_ok={fallback_applied}, version={fallback_version!r}",
            )
        )

        # Both fallback layers must handle sentences exactly as the primary does.
        # They previously did not, and no test could see it: the portable
        # fallback staged nothing (so new content never arrived) and the
        # installer fallback had no backup at all (so Inno destroyed every user
        # edit). Protections that exist only on the happy path are worthless.
        fb_incoming = FALLBACK_APP_DIR / "_sentences_incoming" / "English.txt"
        fb_user = FALLBACK_APP_DIR / "Sentences" / "English.txt"
        fb_user_text = fb_user.read_text(encoding="utf-8") if fb_user.exists() else ""
        steps.append(
            StepResult(
                "portable fallback stages sentences and keeps the user's edits",
                fb_incoming.exists() and fb_user_text == USER_SENTENCE,
                f"staged={fb_incoming.exists()}, user_edit_kept={fb_user_text == USER_SENTENCE}",
            )
        )

        # ------------------------------------------------------------------
        # Rollback, driven by a deliberately broken payload.
        #
        # The payload carries an exe (so the pre-mirror validation passes) and a
        # file only the "new release" ships, but no modules tree.  The mirror
        # therefore succeeds, the post-mirror structure check fails, and the
        # rollback path runs against a genuine snapshot.  This is the path that
        # a parenthesised log message silently broke earlier, and the one where
        # overlay-restore used to leave a mixed old/new tree.
        # ------------------------------------------------------------------
        _clean_dir(ROLLBACK_APP_DIR)
        _seed_fixture_tree(ROLLBACK_APP_DIR, fixture_exe, OLD_VERSION)
        (ROLLBACK_APP_DIR / "user_owned.txt").write_text("must survive rollback\n", encoding="utf-8")
        rollback_backup = update_manager.create_app_backup_zip(str(ROLLBACK_APP_DIR), OLD_VERSION)
        if not rollback_backup:
            raise RuntimeError("Could not build the rollback snapshot this phase needs.")

        broken_payload = ARTIFACT_ROOT / "broken_payload"
        _clean_dir(broken_payload)
        broken_keyquest = broken_payload / "KeyQuest"
        broken_keyquest.mkdir(parents=True)
        shutil.copy2(fixture_exe, broken_keyquest / "KeyQuest.exe")
        (broken_keyquest / "new_only.dll").write_text("shipped only by the new release\n", encoding="utf-8")
        broken_zip = ARTIFACT_ROOT / "broken_payload.zip"
        with zipfile.ZipFile(broken_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in broken_keyquest.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(broken_payload))

        rollback_old_boot = ROLLBACK_APP_DIR / "old_boot.json"
        rollback_new_boot = ROLLBACK_APP_DIR / "updater_boot.json"
        old_process = subprocess.Popen(
            [str(ROLLBACK_APP_DIR / "KeyQuest.exe"), "--hold-seconds", "3", "--boot-file", rollback_old_boot.name],
            cwd=str(ROLLBACK_APP_DIR),
            close_fds=True,
        )
        rollback_boot_ok = _wait_for_path(rollback_old_boot, 10)
        steps.append(StepResult("launch old build for rollback", rollback_boot_ok, f"pid={old_process.pid}"))
        if not rollback_boot_ok:
            raise RuntimeError("Old build did not start for the rollback phase.")

        rollback_bat = update_manager.create_portable_update_launcher(
            zip_path=broken_zip,
            app_dir=str(ROLLBACK_APP_DIR),
            app_exe_path=str(ROLLBACK_APP_DIR / "KeyQuest.exe"),
            current_pid=old_process.pid,
            script_path=DOWNLOADS_DIR / "run_keyquest_rollback.bat",
            backup_zip_path=rollback_backup,
        )
        launcher_process = subprocess.Popen(
            update_manager.quote_bat_command(rollback_bat),
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        rollback_return = launcher_process.wait(timeout=180)
        old_process.wait(timeout=20)

        rollback_log = ROLLBACK_APP_DIR / "keyquest_error.log"
        rollback_log_text = rollback_log.read_text(encoding="utf-8", errors="replace") if rollback_log.exists() else ""
        # The app must come back, and it must come back as the OLD version.
        rollback_relaunched = _wait_for_boot_version(rollback_new_boot, OLD_VERSION, 30)
        rollback_version = (_run([str(ROLLBACK_APP_DIR / "KeyQuest.exe"), "--version"], cwd=ROLLBACK_APP_DIR, timeout=15).stdout or "").strip()
        new_only_gone = not (ROLLBACK_APP_DIR / "new_only.dll").exists()
        user_file_kept = (ROLLBACK_APP_DIR / "user_owned.txt").exists()
        steps.append(
            StepResult(
                "rollback restores old version and restarts the app",
                rollback_relaunched and rollback_version == OLD_VERSION and "Backup restored" in rollback_log_text,
                f"exit={rollback_return}, boot_ok={rollback_relaunched}, version={rollback_version!r}, "
                f"restored={'Backup restored' in rollback_log_text}",
            )
        )
        steps.append(
            StepResult(
                "rollback removes new-only files and keeps user files",
                new_only_gone and user_file_kept,
                f"new_only_removed={new_only_gone}, user_file_kept={user_file_kept}",
            )
        )

        # ------------------------------------------------------------------
        # Fallback layer 2 for the installer layout: the silent installer bat.
        # No process is left running here; this path deliberately has no PID
        # wait and relies on the installer's own /CLOSEAPPLICATIONS.
        # ------------------------------------------------------------------
        _clean_dir(INSTALLER_FALLBACK_APP_DIR)
        _seed_fixture_tree(INSTALLER_FALLBACK_APP_DIR, fixture_exe, OLD_VERSION)
        installer_fb_boot = INSTALLER_FALLBACK_APP_DIR / "updater_boot.json"
        (INSTALLER_FALLBACK_APP_DIR / "Sentences" / "English.txt").write_text(USER_SENTENCE, encoding="utf-8")
        installer_fb_bat = update_manager.create_installer_fallback_bat(
            installer_path=installer_for_fallback,
            app_dir=str(INSTALLER_FALLBACK_APP_DIR),
            app_exe_path=str(INSTALLER_FALLBACK_APP_DIR / "KeyQuest.exe"),
            bat_path=DOWNLOADS_DIR / "run_keyquest_installer_fallback.bat",
        )
        launcher_process = subprocess.Popen(
            update_manager.quote_bat_command(installer_fb_bat),
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        installer_fb_return = launcher_process.wait(timeout=120)
        installer_fb_applied = _wait_for_boot_version(installer_fb_boot, NEW_VERSION, 30)
        installer_fb_version = (_run([str(INSTALLER_FALLBACK_APP_DIR / "KeyQuest.exe"), "--version"], cwd=INSTALLER_FALLBACK_APP_DIR, timeout=15).stdout or "").strip()
        steps.append(
            StepResult(
                "installer fallback applies update and relaunches",
                installer_fb_applied and installer_fb_version == NEW_VERSION,
                f"exit={installer_fb_return}, boot_ok={installer_fb_applied}, version={installer_fb_version!r}",
            )
        )

        ifb_incoming = INSTALLER_FALLBACK_APP_DIR / "_sentences_incoming" / "English.txt"
        ifb_user = INSTALLER_FALLBACK_APP_DIR / "Sentences" / "English.txt"
        ifb_user_text = ifb_user.read_text(encoding="utf-8") if ifb_user.exists() else ""
        steps.append(
            StepResult(
                "installer fallback keeps the user's edits and stages the shipped set",
                ifb_incoming.exists() and ifb_user_text == USER_SENTENCE,
                f"staged={ifb_incoming.exists()}, user_edit_kept={ifb_user_text == USER_SENTENCE}",
            )
        )

        # ------------------------------------------------------------------
        # Did the update actually replace the executable, and did user data
        # survive?  Neither question could previously be answered: one fixture
        # exe was used for both trees, and no phase looked at user files.
        # ------------------------------------------------------------------
        applied_exe_sha = _sha256(PORTABLE_APP_DIR / "KeyQuest.exe")
        applied_build_id = (_run(
            [str(PORTABLE_APP_DIR / "KeyQuest.exe"), "--build-id"],
            cwd=PORTABLE_APP_DIR, timeout=15,
        ).stdout or "").strip()
        if strict:
            exe_swapped = applied_exe_sha == new_exe_sha and applied_build_id == NEW_BUILD_ID
            detail = f"sha_matches_new={applied_exe_sha == new_exe_sha}, build_id={applied_build_id!r}"
        else:
            # Default mode sets KEYQUEST_UPDATER_SKIP_EXE_COPY, so the old exe is
            # expected to remain. Asserting that keeps the step honest instead of
            # quietly passing on a check that never ran.
            exe_swapped = applied_exe_sha == old_exe_sha and applied_build_id == OLD_BUILD_ID
            detail = f"exe-copy skipped by override; still old={applied_exe_sha == old_exe_sha}"
        steps.append(
            StepResult(
                "portable update replaces KeyQuest.exe (strict) / honours the skip override",
                exe_swapped,
                detail,
            )
        )

        surviving_progress = (PORTABLE_APP_DIR / "progress.json").read_text(encoding="utf-8") if (PORTABLE_APP_DIR / "progress.json").exists() else ""
        sentence_path = PORTABLE_APP_DIR / "Sentences" / "English.txt"
        surviving_sentence = sentence_path.read_text(encoding="utf-8") if sentence_path.exists() else ""
        steps.append(
            StepResult(
                "portable update preserves user progress and edited sentences",
                surviving_progress == USER_PROGRESS and surviving_sentence == USER_SENTENCE,
                f"progress_kept={surviving_progress == USER_PROGRESS}, "
                f"sentence_kept={surviving_sentence == USER_SENTENCE}",
            )
        )

        # Sentence content: the launcher stages the release's files for the app
        # to merge, and must not touch the user's folder on the way past. The
        # merge decision itself is covered by tests/test_sentence_merge.py.
        incoming = PORTABLE_APP_DIR / "_sentences_incoming" / "English.txt"
        staged_ok = incoming.exists() and incoming.read_text(encoding="utf-8") == SHIPPED_SENTENCE
        steps.append(
            StepResult(
                "portable update stages shipped sentences without touching the user's folder",
                staged_ok and surviving_sentence == USER_SENTENCE,
                f"staged={staged_ok}, user_file_untouched={surviving_sentence == USER_SENTENCE}",
            )
        )

        merge_result = sentence_merge.merge_sentences(str(PORTABLE_APP_DIR))
        merged_text = (PORTABLE_APP_DIR / "Sentences" / "English.txt").read_text(encoding="utf-8")
        steps.append(
            StepResult(
                "startup merge keeps the user's edited sentence file",
                merged_text == USER_SENTENCE and "English.txt" in merge_result.kept_customized,
                f"kept={merge_result.kept_customized}, added={merge_result.added}, "
                f"updated={merge_result.updated}",
            )
        )

        marker_verdict = update_manager.check_pending_update_marker(str(PORTABLE_APP_DIR), NEW_VERSION)
        steps.append(
            StepResult(
                "pending_update.json survives the portable mirror and reports success",
                marker_verdict == "success",
                f"verdict={marker_verdict!r} (None means /MIR deleted the marker)",
            )
        )

        summary = "PASS" if all(step.passed for step in steps) else "FAIL"
        report_path = STRICT_REPORT_PATH if strict else REPORT_PATH
        _write_report(steps, summary, strict_portable=strict)
        if summary == "PASS":
            print(f"Local updater integration test passed. Report: {report_path}")
            return 0
        print(f"Local updater integration test failed. Report: {report_path}", file=sys.stderr)
        return 1
    except Exception:
        error_text = traceback.format_exc()
        report_path = STRICT_REPORT_PATH if strict else REPORT_PATH
        _write_report(steps, "FAIL", error_text=error_text, strict_portable=strict)
        print(error_text, file=sys.stderr)
        print(f"Report: {report_path}", file=sys.stderr)
        return 1
    finally:
        if launcher_process is not None and launcher_process.poll() is None:
            launcher_process.kill()
        if old_process is not None and old_process.poll() is None:
            old_process.kill()
        swept = _sweep_mei_temp_dirs(run_start)
        if swept:
            print(f"Cleaned {swept} leftover onefile _MEI temp dir(s) from this run.")


if __name__ == "__main__":
    raise SystemExit(main())
