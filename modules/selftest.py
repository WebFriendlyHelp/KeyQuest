"""Release smoke test: prove a bundle can load the app, not just its version.

``KeyQuest.exe --version`` exits before the app is imported, so it stayed
green on a bundle missing wx, pygame, the Tolk DLLs or the data files (the
Hangman word list was missing from every release). ``--selftest`` imports the
app, loads and unloads Tolk, checks the shipped data files, and exits 0 or 1.
It opens no window and speaks nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_PATHS = (
    "Sentences",
    "sentence_history.json",
    "data/wordlists/hangman_common.json",
)
# Made by the build spec, so only a frozen bundle has it.
FROZEN_ONLY_PATHS = ("defaults/Sentences",)


def run(app_dir: str | Path, *, load_tolk: bool = True) -> int:
    root = Path(app_dir)
    try:
        import pygame  # noqa: F401
        import wx  # noqa: F401

        import modules.keyquest_app  # noqa: F401  every module the app imports

        if load_tolk:
            from cytolk import tolk

            tolk.load()
            tolk.unload()
    except Exception as exc:  # noqa: BLE001 - any failure is the finding
        print(f"Self-test failed: {type(exc).__name__}: {exc}")
        return 1

    required = REQUIRED_PATHS + (FROZEN_ONLY_PATHS if getattr(sys, "frozen", False) else ())
    missing = [rel for rel in required if not (root / rel).exists()]
    if missing:
        print("Self-test failed: missing " + ", ".join(missing))
        return 1
    print("Self-test passed.")
    return 0
