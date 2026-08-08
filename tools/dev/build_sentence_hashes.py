"""Record the hash of every sentence file KeyQuest has ever shipped.

Why this exists
---------------
The sentence merge has to answer one question per file: did the user change
this, or is it exactly as we shipped it? Comparing against only the *previous*
release cannot answer it in two important cases:

1. The transition. An install that predates the merge feature has no record of
   what shipped, so every file has to be conservatively kept. The baseline then
   advances to the new release, and every untouched file whose content changed
   across that gap differs from the baseline forever: never corrected again, and
   announced as "your own file" to someone who never touched it.

2. A one-time failure. A file locked during one update is skipped, but the
   baseline moves on regardless, so that file is frozen as "customized" for good.

Both dissolve if "unmodified" means "matches ANY version we have ever shipped"
rather than "matches the last one". This file is that record.

Usage
-----
Run whenever sentence content changes, and before cutting a release::

    py -3.11 tools/dev/build_sentence_hashes.py

It only ever ADDS hashes. Removing one would tell a future release that a file
the user still has was edited by them, which is exactly the wrong answer.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SENTENCES_DIR = REPO_ROOT / "Sentences"
HISTORY_PATH = REPO_ROOT / "sentence_history.json"


def content_hash(path: Path) -> str:
    """Hash with line endings normalised.

    An editor that rewrites CRLF as LF has not meaningfully changed the file,
    and the user should still receive corrections to it. This must stay in step
    with ``_same_content`` in ``modules/sentence_merge.py``.
    """
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_history() -> dict[str, list[str]]:
    if not HISTORY_PATH.exists():
        return {}
    try:
        loaded = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(name): [str(h) for h in hashes]
        for name, hashes in loaded.items()
        if isinstance(hashes, list)
    }


def main() -> int:
    if not SENTENCES_DIR.is_dir():
        print(f"No Sentences folder at {SENTENCES_DIR}", file=sys.stderr)
        return 1

    history = load_history()
    added = 0
    for path in sorted(SENTENCES_DIR.iterdir()):
        if not path.is_file():
            continue
        digest = content_hash(path)
        entries = history.setdefault(path.name, [])
        if digest not in entries:
            entries.append(digest)
            added += 1
            print(f"  + {path.name}  {digest[:12]}")

    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    total = sum(len(v) for v in history.values())
    print(f"{added} new hash(es) recorded. {len(history)} file(s), {total} known version(s).")
    print(f"Wrote {HISTORY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
