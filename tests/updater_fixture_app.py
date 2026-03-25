"""Small Windows fixture app used by the local updater integration harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _read_version(app_dir: Path) -> str:
    version_file = app_dir / "modules" / "version.py"
    namespace: dict[str, str] = {}
    exec(version_file.read_text(encoding="utf-8"), namespace)
    return str(namespace.get("__version__", "0.0.0"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--hold-seconds", type=float, default=0.0)
    parser.add_argument("--boot-file", default="updater_boot.json")
    args = parser.parse_args()

    app_dir = _get_app_dir()
    version = _read_version(app_dir)
    if args.version:
        print(version)
        return 0

    boot_path = app_dir / args.boot_file
    boot_path.write_text(
        json.dumps(
            {
                "version": version,
                "pid": os.getpid(),
                "exe": str(Path(sys.executable).resolve()),
                "timestamp": time.time(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if args.hold_seconds > 0:
        time.sleep(args.hold_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
