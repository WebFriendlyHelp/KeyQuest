"""Warn when this machine would build something different from what CI ships.

Why this exists. On 2026-08-15 the dev machine was found to be running wxPython
4.2.5 while CI had shipped v1.27.1 built on 4.3.1. wxPython owns the accessible
results dialog, so **the dialogs users received were built on a version that had
never been run here**, and every local test pass was against a stack nobody
shipped. Nothing compared the two, so nothing noticed.

The cause is structural rather than careless: `requirements.txt` carries floors,
CI installs fresh on every run and therefore resolves to the newest allowed
version, and a dev machine is installed once and then left alone. They drift
apart quietly and by default.

This is the same failure the ruff step in `run_quality_checks.ps1` already
guards against, where local ran a narrower rule set than CI and produced false
confidence. Same principle: if CI would use something different, say so here
rather than at the release.

    py -3.11 tools/dev/check_env_matches_ci.py            # warn, always exit 0
    py -3.11 tools/dev/check_env_matches_ci.py --strict   # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements.txt"

# Installed by the workflows on top of requirements.txt. Kept here because a
# drifting build tool is exactly as capable of changing the shipped exe.
CI_EXTRAS = ["pyinstaller", "pytest", "ruff"]

TIMEOUT_SECONDS = 6


def parse_requirements(text: str):
    """Yield (name, specifier) for each real requirement line."""
    from packaging.requirements import Requirement

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            requirement = Requirement(line)
        except Exception:
            continue
        yield requirement.name, requirement.specifier


def installed_version(name: str) -> str | None:
    import importlib.metadata as metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def newest_allowed(name: str, specifier) -> str | None:
    """The version a fresh `pip install` would choose, which is what CI gets.

    Must honour each release's ``requires_python``. Without it this reports
    false drift the moment a project publishes a release that drops the Python
    version we build on: numpy 2.5.2 exists but has no 3.11 build, so pip
    correctly stops at 2.4.6 and a naive "newest version" check calls that
    drift. Caught by this script's own first run.
    """
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    running = Version(
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    best = None
    for candidate, files in data.get("releases", {}).items():
        usable = [f for f in files if not f.get("yanked")]
        if not usable:
            continue
        try:
            version = Version(candidate)
        except InvalidVersion:
            continue
        if version.is_prerelease:
            continue
        if specifier is not None and not specifier.contains(version):
            continue
        if not any(_runs_on(f.get("requires_python"), running, SpecifierSet, InvalidSpecifier)
                   for f in usable):
            continue
        if best is None or version > best:
            best = version
    return str(best) if best else None


def _runs_on(requires_python, running, SpecifierSet, InvalidSpecifier) -> bool:
    """Whether a release file accepts the interpreter we build with."""
    if not requires_python:
        return True
    try:
        return SpecifierSet(requires_python).contains(running, prereleases=True)
    except InvalidSpecifier:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when this machine differs from what CI would build")
    args = parser.parse_args()

    try:
        import packaging  # noqa: F401
    except ImportError:
        print("check skipped: the 'packaging' module is not available")
        return 0

    wanted = list(parse_requirements(REQUIREMENTS.read_text(encoding="utf-8")))
    wanted += [(name, None) for name in CI_EXTRAS]

    drift = []
    missing = []
    offline = False

    for name, specifier in wanted:
        local = installed_version(name)
        if local is None:
            missing.append(name)
            continue
        remote = newest_allowed(name, specifier)
        if remote is None:
            offline = True
            continue
        if remote != local:
            drift.append((name, local, remote))

    if offline and not drift:
        print("check skipped: could not reach PyPI, so no comparison was made")
        return 0

    for name in missing:
        print(f"  NOT INSTALLED  {name}")

    if not drift:
        print("Local environment matches what CI would build with.")
        return 0

    print("This machine would build something different from what CI ships:")
    for name, local, remote in drift:
        print(f"  {name:14} local {local:14} CI would use {remote}")
    print()
    print("  Fix: py -3.11 -m pip install --upgrade -r requirements.txt "
          + " ".join(CI_EXTRAS))
    print("  Then exercise anything the changed package owns. wxPython owns the")
    print("  accessible dialogs; pygame owns input; cytolk owns screen reader output.")

    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
