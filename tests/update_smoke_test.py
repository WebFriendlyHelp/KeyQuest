"""Live integration smoke test for update_manager against the real GitHub API.

This is NOT part of the normal pytest suite — it makes real network requests
and downloads a release asset to verify SHA-256 end-to-end.

Run manually:
  python tests/update_smoke_test.py

Or trigger via GitHub Actions:
  Actions > Update Smoke Test > Run workflow
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import update_manager
from modules.version import __version__


def check(label: str, condition: bool, detail: str = ""):
    if not condition:
        msg = f"FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        sys.exit(1)
    print(f"  ok  {label}")


def run():
    print(f"Update smoke test  (installed version: {__version__})\n")

    # ------------------------------------------------------------------
    # 1. check_for_update with an old version → UpdateAvailable
    # ------------------------------------------------------------------
    print("1. check_for_update('0.0.1', portable=False)")
    result = update_manager.check_for_update("0.0.1", portable=False)
    check("returns UpdateAvailable", isinstance(result, update_manager.UpdateAvailable))
    check("version is non-empty", bool(result.version), result.version)
    check("download_url is https", result.download_url.startswith("https://"), result.download_url)
    check("asset_name is non-empty", bool(result.asset_name), result.asset_name)
    check("asset_size > 0", result.asset_size > 0, str(result.asset_size))
    check("asset_name is .exe", result.asset_name.lower().endswith(".exe"), result.asset_name)
    check("release dict is present", bool(result.release))
    print(f"     version={result.version}  asset={result.asset_name}  size={result.asset_size:,} bytes\n")

    # ------------------------------------------------------------------
    # 2. check_for_update with current version → UpdateUpToDate
    # ------------------------------------------------------------------
    print(f"2. check_for_update('{__version__}', portable=False)")
    result2 = update_manager.check_for_update(__version__, portable=False)
    check("returns UpdateUpToDate", isinstance(result2, update_manager.UpdateUpToDate))
    check("current_version matches", result2.current_version == __version__)
    print(f"     current_version={result2.current_version} — up to date\n")

    # ------------------------------------------------------------------
    # 3. Portable asset selection
    # ------------------------------------------------------------------
    print("3. check_for_update('0.0.1', portable=True)")
    result3 = update_manager.check_for_update("0.0.1", portable=True)
    check("returns UpdateAvailable", isinstance(result3, update_manager.UpdateAvailable))
    check("asset_name is .zip", result3.asset_name.lower().endswith(".zip"), result3.asset_name)
    print(f"     version={result3.version}  asset={result3.asset_name}\n")

    # ------------------------------------------------------------------
    # 4. SHA-256 sidecar — download and verify if published
    # ------------------------------------------------------------------
    print("4. SHA-256 sidecar verification")
    sha256_asset = update_manager.select_sha256_asset(result.release, result.asset_name)
    if sha256_asset:
        print(f"     sidecar: {sha256_asset['name']} — downloading installer and verifying hash ...")
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / result.asset_name
            update_manager.download_file(result.download_url, dest)
            check("installer downloaded", dest.exists() and dest.stat().st_size > 0)
            expected = update_manager.fetch_sha256_for_asset(sha256_asset)
            check("sidecar hash is non-empty", bool(expected), repr(expected))
            check(
                "SHA-256 matches downloaded file",
                update_manager.verify_file_sha256(dest, expected),
                f"expected {expected[:16]}...",
            )
        print(f"     hash verified: {expected[:16]}...\n")
    else:
        print("     no SHA-256 sidecar published for this release — skipping hash check\n")
        print("     NOTE: publish KeyQuestSetup.exe.sha256 alongside the release asset to enable this check.")

    # ------------------------------------------------------------------
    # 5. Typed error: HTTP error path
    # ------------------------------------------------------------------
    print("5. Typed error on bad URL")
    try:
        update_manager.fetch_latest_release(
            url="https://api.github.com/repos/WebFriendlyHelp/KeyQuest/releases/tags/v0.0.0.nonexistent"
        )
        check("raised UpdateHttpError", False, "no exception raised")
    except update_manager.UpdateHttpError as e:
        check("raised UpdateHttpError", True)
        check("status_code is set", e.status_code > 0, str(e.status_code))
        print(f"     status_code={e.status_code}\n")

    print("All checks passed.")


if __name__ == "__main__":
    run()
