"""
Full end-to-end update simulation.

Creates a temporary GitHub pre-release tagged v99.0.0-smoketest with:
  - a dummy installer  (KeyQuestSetup.exe)
  - a dummy portable   (KeyQuest-win64.zip)
  - SHA-256 sidecars   (*.sha256)

Runs the complete check -> download -> verify flow against that release,
then deletes the release and tag from GitHub.

Usage:
    python tests/run_full_update_sim.py

Requirements:
    - gh CLI installed and authenticated  (gh auth status)
    - Push access to the repository
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import update_manager

TEST_TAG = "v99.0.0-smoketest"
TEST_VERSION = "99.0.0"
REPO = "WebFriendlyHelp/KeyQuest"
TAG_API_URL = f"https://api.github.com/repos/{REPO}/releases/tags/{TEST_TAG}"

INSTALLER_NAME = "KeyQuestSetup.exe"
PORTABLE_NAME = "KeyQuest-win64.zip"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(label: str, condition: bool, detail: str = ""):
    if not condition:
        msg = f"  FAIL  {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        cleanup_release()
        sys.exit(1)
    print(f"  ok    {label}")


def run_gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cleanup_release():
    print("\n--- Cleanup ---")
    try:
        run_gh("release", "delete", TEST_TAG, "--repo", REPO, "--yes", "--cleanup-tag")
        print(f"  Deleted release and tag {TEST_TAG}")
    except Exception as e:
        print(f"  Warning: cleanup failed — {e}")
        print(f"  Delete manually:  gh release delete {TEST_TAG} --repo {REPO} --yes --cleanup-tag")


# ---------------------------------------------------------------------------
# Build dummy assets
# ---------------------------------------------------------------------------

def build_dummy_assets(work_dir: Path) -> tuple[Path, Path]:
    """Create minimal but real dummy installer and portable zip."""

    # Dummy installer: a small self-contained text file renamed .exe
    # (enough to test download + SHA-256; won't be executed)
    installer = work_dir / INSTALLER_NAME
    installer.write_bytes(
        b"KeyQuest dummy installer for smoke test. Not a real executable.\n"
        b"This file is safe to delete.\n" * 64  # ~4 KB
    )

    # Dummy portable: a real zip with a placeholder structure
    portable = work_dir / PORTABLE_NAME
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("KeyQuest/KeyQuest.exe", "dummy exe placeholder\n" * 64)
        zf.writestr("KeyQuest/modules/__init__.py", "# placeholder\n")
        zf.writestr("KeyQuest/Sentences/English.txt", "The quick brown fox.\n")
        zf.writestr("KeyQuest/progress.json", '{"version": "99.0.0"}\n')

    return installer, portable


def write_sidecars(installer: Path, portable: Path) -> tuple[Path, Path]:
    inst_hash = sha256_of(installer)
    port_hash = sha256_of(portable)

    inst_sidecar = installer.parent / (INSTALLER_NAME + ".sha256")
    port_sidecar = portable.parent / (PORTABLE_NAME + ".sha256")

    inst_sidecar.write_text(f"{inst_hash}  {INSTALLER_NAME}\n", encoding="utf-8")
    port_sidecar.write_text(f"{port_hash}  {PORTABLE_NAME}\n", encoding="utf-8")

    print(f"  installer hash : {inst_hash[:16]}...")
    print(f"  portable hash  : {port_hash[:16]}...")

    return inst_sidecar, port_sidecar


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("KeyQuest full update simulation")
    print(f"Test tag: {TEST_TAG}")
    print("=" * 60)

    work_dir = Path(tempfile.mkdtemp(prefix="kq_update_sim_"))
    try:
        _run_sim(work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _run_sim(work_dir: Path):
    # ------------------------------------------------------------------
    # Step 1: Build dummy assets + sidecars
    # ------------------------------------------------------------------
    print("\n--- Step 1: Build dummy assets ---")
    installer, portable = build_dummy_assets(work_dir)
    print(f"  installer : {installer.stat().st_size:,} bytes")
    print(f"  portable  : {portable.stat().st_size:,} bytes")

    print("\n--- Step 2: Generate SHA-256 sidecars ---")
    inst_sidecar, port_sidecar = write_sidecars(installer, portable)

    # ------------------------------------------------------------------
    # Step 3: Publish pre-release to GitHub
    # ------------------------------------------------------------------
    print(f"\n--- Step 3: Create pre-release {TEST_TAG} on GitHub ---")
    run_gh(
        "release", "create", TEST_TAG,
        "--repo", REPO,
        "--prerelease",
        "--title", f"KeyQuest {TEST_VERSION} (smoke test — safe to delete)",
        "--notes", "Automated smoke test release. Will be deleted automatically.",
        str(installer),
        str(inst_sidecar),
        str(portable),
        str(port_sidecar),
    )
    print(f"  Published. Waiting 3 seconds for GitHub API propagation...")
    time.sleep(3)

    # ------------------------------------------------------------------
    # Step 4: check_for_update against the test release
    # ------------------------------------------------------------------
    print("\n--- Step 4: check_for_update against test release ---")

    print("  4a. installer path (0.0.1 -> should be UpdateAvailable)")
    result = update_manager.check_for_update("0.0.1", portable=False, url=TAG_API_URL)
    check("returns UpdateAvailable", isinstance(result, update_manager.UpdateAvailable))
    check("version matches test tag", result.version == TEST_VERSION, result.version)
    check("asset is installer", result.asset_name == INSTALLER_NAME, result.asset_name)
    check("download_url is https", result.download_url.startswith("https://"))
    check("asset_size > 0", result.asset_size > 0, str(result.asset_size))
    check("release payload present", bool(result.release))

    print("  4b. portable path (0.0.1 -> should be UpdateAvailable)")
    result_p = update_manager.check_for_update("0.0.1", portable=True, url=TAG_API_URL)
    check("returns UpdateAvailable", isinstance(result_p, update_manager.UpdateAvailable))
    check("asset is portable zip", result_p.asset_name == PORTABLE_NAME, result_p.asset_name)

    print("  4c. up-to-date path (99.0.0 -> should be UpdateUpToDate)")
    result_u = update_manager.check_for_update(TEST_VERSION, portable=False, url=TAG_API_URL)
    check("returns UpdateUpToDate", isinstance(result_u, update_manager.UpdateUpToDate))

    # ------------------------------------------------------------------
    # Step 5: Download installer + verify SHA-256
    # ------------------------------------------------------------------
    print("\n--- Step 5: Download installer and verify SHA-256 ---")
    dest_dir = work_dir / "downloads"
    dest_dir.mkdir()
    dest = dest_dir / INSTALLER_NAME

    downloaded = update_manager.download_file(result.download_url, dest)
    check("file downloaded", downloaded.exists())
    check("file size matches", downloaded.stat().st_size == result.asset_size,
          f"{downloaded.stat().st_size} vs {result.asset_size}")

    sha256_asset = update_manager.select_sha256_asset(result.release, result.asset_name)
    check("SHA-256 sidecar found in release", sha256_asset is not None)

    expected_hash = update_manager.fetch_sha256_for_asset(sha256_asset)
    check("sidecar hash fetched", bool(expected_hash), repr(expected_hash))

    check(
        "SHA-256 matches downloaded file",
        update_manager.verify_file_sha256(downloaded, expected_hash),
        f"expected {expected_hash[:16]}...",
    )
    print(f"  hash verified: {expected_hash[:16]}...")

    # ------------------------------------------------------------------
    # Step 6: Download portable zip + verify SHA-256
    # ------------------------------------------------------------------
    print("\n--- Step 6: Download portable zip and verify SHA-256 ---")
    dest_zip = dest_dir / PORTABLE_NAME

    downloaded_zip = update_manager.download_file(result_p.download_url, dest_zip)
    check("zip downloaded", downloaded_zip.exists())

    sha256_asset_p = update_manager.select_sha256_asset(result_p.release, result_p.asset_name)
    check("SHA-256 sidecar found for portable", sha256_asset_p is not None)

    expected_hash_p = update_manager.fetch_sha256_for_asset(sha256_asset_p)
    check("sidecar hash fetched", bool(expected_hash_p))
    check(
        "SHA-256 matches portable zip",
        update_manager.verify_file_sha256(downloaded_zip, expected_hash_p),
        f"expected {expected_hash_p[:16]}...",
    )
    print(f"  hash verified: {expected_hash_p[:16]}...")

    # ------------------------------------------------------------------
    # Step 7: Verify corrupted file is rejected
    # ------------------------------------------------------------------
    print("\n--- Step 7: Tampered file is rejected ---")
    tampered = dest_dir / "tampered.exe"
    tampered.write_bytes(b"this is not the real file")
    check(
        "tampered file fails SHA-256",
        not update_manager.verify_file_sha256(tampered, expected_hash),
    )

    # ------------------------------------------------------------------
    # Step 8: Cleanup
    # ------------------------------------------------------------------
    cleanup_release()

    print("\n" + "=" * 60)
    print("All checks passed. Full update flow verified end-to-end.")
    print("=" * 60)


if __name__ == "__main__":
    main()
