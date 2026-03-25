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
import textwrap
import time
import traceback
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import update_manager


ARTIFACT_ROOT = ROOT / "tests" / "logs" / "local_updater"
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
OLD_BOOT_PATH = APP_DIR / "old_boot.json"
NEW_BOOT_PATH = APP_DIR / "updater_boot.json"
PORTABLE_OLD_BOOT_PATH = PORTABLE_APP_DIR / "old_boot.json"
PORTABLE_NEW_BOOT_PATH = PORTABLE_APP_DIR / "updater_boot.json"
INSTALLER_TRACE_PATH = APP_DIR / "fake_installer_trace.json"

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


def _build_pyinstaller_exe(script_path: Path, dist_dir: Path, work_dir: Path, name: str) -> Path:
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
    return exe_path


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


def _write_report(steps: list[StepResult], summary: str, error_text: str = "") -> None:
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
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RESULT_JSON_PATH.write_text(
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
    parser.add_argument(
        "--strict-portable",
        action="store_true",
        help=(
            "Disable the portable-path test-only overrides so the harness runs as close to "
            "production behavior as this machine allows."
        ),
    )
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        args = _parse_args()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--strict-portable", action="store_true")
        args = parser.parse_args(argv)
    steps: list[StepResult] = []
    old_process: subprocess.Popen[str] | None = None
    launcher_process: subprocess.Popen[str] | None = None
    error_text = ""
    try:
        _clean_dir(ARTIFACT_ROOT)
        BUILD_ROOT.mkdir(parents=True, exist_ok=True)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        if args.strict_portable:
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

        fixture_exe = _build_pyinstaller_exe(
            ROOT / "tests" / "updater_fixture_app.py",
            FIXTURE_DIST,
            FIXTURE_WORK,
            "KeyQuest",
        )
        steps.append(StepResult("build fixture app", fixture_exe.exists(), str(fixture_exe)))

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
        steps.append(
            StepResult(
                "seed old portable app",
                (PORTABLE_APP_DIR / "KeyQuest.exe").exists() and (PORTABLE_APP_DIR / "modules" / "version.py").exists(),
                str(PORTABLE_APP_DIR),
            )
        )

        payload_keyquest = NEW_PAYLOAD_ROOT / "KeyQuest"
        _seed_fixture_tree(payload_keyquest, fixture_exe, NEW_VERSION, include_sentences=False)
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
        )
        steps.append(StepResult("build fake installer exe", installer_exe.exists(), str(installer_exe)))

        release_path = _prepare_feed(installer_exe, portable_zip)
        release_url = release_path.resolve().as_uri()
        steps.append(StepResult("prepare local file feed", release_path.exists(), release_url))
        if args.strict_portable:
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
            script_path=DOWNLOADS_DIR / "run_keyquest_update.cmd",
        )
        launcher_process = subprocess.Popen(
            ["cmd", "/c", str(launcher_path)],
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        launcher_return = launcher_process.wait(timeout=90)
        old_exit_ok = old_process.wait(timeout=20) is not None
        steps.append(
            StepResult(
                "run update launcher and stop old process",
                launcher_return == 0 and old_exit_ok,
                f"launcher_exit={launcher_return}",
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
            script_path=DOWNLOADS_DIR / "run_keyquest_portable_update.cmd",
        )
        launcher_process = subprocess.Popen(
            ["cmd", "/c", str(launcher_path)],
            cwd=str(DOWNLOADS_DIR),
            close_fds=True,
        )
        launcher_return = launcher_process.wait(timeout=90)
        old_exit_ok = old_process.wait(timeout=20) is not None
        steps.append(
            StepResult(
                "run portable update launcher and stop old process",
                launcher_return == 0 and old_exit_ok,
                f"launcher_exit={launcher_return}",
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

        summary = "PASS" if all(step.passed for step in steps) else "FAIL"
        _write_report(steps, summary)
        if summary == "PASS":
            print(f"Local updater integration test passed. Report: {REPORT_PATH}")
            return 0
        print(f"Local updater integration test failed. Report: {REPORT_PATH}", file=sys.stderr)
        return 1
    except Exception:
        error_text = traceback.format_exc()
        _write_report(steps, "FAIL", error_text=error_text)
        print(error_text, file=sys.stderr)
        return 1
    finally:
        if launcher_process is not None and launcher_process.poll() is None:
            launcher_process.kill()
        if old_process is not None and old_process.poll() is None:
            old_process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
