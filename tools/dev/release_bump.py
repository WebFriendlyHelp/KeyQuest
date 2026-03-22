from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = REPO_ROOT / "modules" / "version.py"
README_HTML_FILE = REPO_ROOT / "README.html"
WHATS_NEW_FILE = REPO_ROOT / "docs" / "user" / "WHATS_NEW.md"
BUILD_PAGES_SITE = REPO_ROOT / "tools" / "dev" / "build_pages_site.py"


def read_version() -> str:
    match = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        VERSION_FILE.read_text(encoding="utf-8"),
    )
    if not match:
        raise SystemExit("Could not read __version__ from modules/version.py")
    return match.group(1)


def write_version(version: str) -> None:
    source = VERSION_FILE.read_text(encoding="utf-8")
    updated = re.sub(
        r'__version__\s*=\s*"([^"]+)"',
        f'__version__ = "{version}"',
        source,
        count=1,
    )
    if updated == source:
        raise SystemExit("Could not update modules/version.py")
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)


def sync_readme_version_text(source: str, version: str) -> str:
    """Return README.html content with the version text aligned."""
    updated = source.replace("{{APP_VERSION}}", version)
    updated = re.sub(
        r"(<p><strong>Version )[^<]+(</strong></p>)",
        rf"\g<1>{version}\g<2>",
        updated,
        count=1,
    )
    updated = re.sub(
        r"(<li><strong>Application</strong>: KeyQuest )[^<]+(</li>)",
        rf"\g<1>{version}\g<2>",
        updated,
        count=1,
    )
    return updated


def sync_readme_version(version: str) -> None:
    """Keep the plain-language guide version text aligned with the app version."""
    source = README_HTML_FILE.read_text(encoding="utf-8")
    updated = sync_readme_version_text(source, version)
    with open(README_HTML_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)


def sync_whats_new_version_text(source: str, version: str) -> str:
    """Return What's New content with the top release version aligned."""
    updated, count = re.subn(
        r"(?m)^(Version )([0-9]+(?:\.[0-9]+)*)$",
        rf"\g<1>{version}",
        source,
        count=1,
    )
    if count == 0:
        raise SystemExit("Could not update the top version entry in docs/user/WHATS_NEW.md")
    return updated


def sync_whats_new_version(version: str) -> None:
    """Update the first visible release version in What's New."""
    source = WHATS_NEW_FILE.read_text(encoding="utf-8")
    updated = sync_whats_new_version_text(source, version)
    with open(WHATS_NEW_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)


def read_top_whats_new_version(source: str | None = None) -> str:
    """Return the first visible release version from What's New."""
    if source is None:
        source = WHATS_NEW_FILE.read_text(encoding="utf-8")
    match = re.search(r"(?m)^(Version )([0-9]+(?:\.[0-9]+)*)$", source)
    if not match:
        raise SystemExit("Could not read the top version entry from docs/user/WHATS_NEW.md")
    return match.group(2)


def validate_release_metadata(version: str | None = None, whats_new_source: str | None = None) -> None:
    """Ensure release metadata is aligned before shipping."""
    expected_version = version or read_version()
    whats_new_version = read_top_whats_new_version(whats_new_source)
    if whats_new_version != expected_version:
        raise SystemExit(
            "Release metadata mismatch: "
            f"modules/version.py is {expected_version} but docs/user/WHATS_NEW.md starts with {whats_new_version}"
        )


def rebuild_pages_site() -> None:
    """Regenerate static site files that mirror README.html."""
    subprocess.run(
        ["python", str(BUILD_PAGES_SITE)],
        cwd=REPO_ROOT,
        check=True,
    )


def bump_version(version: str, bump: str) -> str:
    parts = [int(token) for token in version.split(".")]
    while len(parts) < 3:
        parts.append(0)

    major, minor, patch = parts[:3]

    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"Unsupported bump type: {bump}")


def get_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip())
    return files


def suggest_bump(files: list[str]) -> str:
    if not files:
        return "patch"

    minor_prefixes = (
        "modules/",
        "games/",
        "keyquest.pyw",
        ".github/workflows/release.yml",
        "tools/build/",
    )
    patch_prefixes = (
        "docs/",
        "site/",
        "README",
        "Sentences/",
        "tools/dev/write_keyquest_blog_post.py",
        "tools/dev/build_pages_site.py",
    )

    for path in files:
        normalized = path.replace("\\", "/")
        if normalized == "modules/version.py":
            continue
        if normalized.startswith(minor_prefixes):
            return "minor"

    for path in files:
        normalized = path.replace("\\", "/")
        if normalized.startswith(patch_prefixes):
            continue
        return "minor"

    return "patch"


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest or apply a KeyQuest release version bump.")
    parser.add_argument("--suggest", action="store_true", help="Print the suggested bump type.")
    parser.add_argument("--apply", choices=["patch", "minor", "major"], help="Apply a version bump.")
    args = parser.parse_args()

    files = get_changed_files()

    if args.suggest:
        print(suggest_bump(files))
        return

    if args.apply:
        current = read_version()
        new_version = bump_version(current, args.apply)
        write_version(new_version)
        sync_readme_version(new_version)
        sync_whats_new_version(new_version)
        validate_release_metadata(new_version)
        rebuild_pages_site()
        print(new_version)
        return

    parser.error("Use --suggest or --apply.")


if __name__ == "__main__":
    main()
