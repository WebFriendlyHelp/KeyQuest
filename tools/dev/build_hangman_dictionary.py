"""Build offline Hangman word/definition data from Kaikki Wiktionary.

Usage:
  python tools/dev/build_hangman_dictionary.py --target 220000
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import urllib.request
from pathlib import Path


KAIKKI_URL = "https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz"
ROOT = Path(__file__).resolve().parents[2]
# Git-ignored build input for tools/dev/build_hangman_common.py; the shipped
# list (data/wordlists/hangman_common.json) is built from what lands here.
DATA_DIR = ROOT / "tools" / "dev" / "hangman_source"
KAIKKI_GZ_PATH = DATA_DIR / "kaikki_english.jsonl.gz"
DEFINITIONS_PATH = DATA_DIR / "hangman_definitions.json"
WORDS_PATH = DATA_DIR / "hangman_words.txt"

MIN_LEN = 5
BAD_TAGS = {"obsolete", "archaic", "dated", "rare"}
INFLECTION_PATTERNS = (
    "plural of ",
    "alternative spelling of ",
    "alternative form of ",
    "past tense of ",
    "past participle of ",
    "present participle of ",
    "simple past of ",
    "third-person singular simple present indicative of ",
    "misspelling of ",
    "comparative of ",
    "superlative of ",
)


def download_kaikki_if_missing() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KAIKKI_GZ_PATH.exists() and KAIKKI_GZ_PATH.stat().st_size > 0:
        return

    print(f"Downloading Kaikki dump to {KAIKKI_GZ_PATH} ...")
    with urllib.request.urlopen(KAIKKI_URL, timeout=120) as response:
        with KAIKKI_GZ_PATH.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    print("Download complete.")


def normalize_word(raw_word: str) -> str:
    word = raw_word.strip().lower()
    if len(word) < MIN_LEN or not word.isalpha():
        return ""
    return word


def normalize_definition(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned


def definition_score(defn: str, has_bad_tags: bool) -> int:
    """Higher score is better."""
    lower = defn.lower()
    score = 100
    if has_bad_tags:
        score -= 25
    if any(lower.startswith(prefix) for prefix in INFLECTION_PATTERNS):
        score -= 60
    if len(defn) < 12:
        score -= 20
    if len(defn) > 240:
        score -= 10
    return score


def extract_best_definition(entry: dict) -> tuple[str, int] | tuple[None, None]:
    senses = entry.get("senses")
    if not isinstance(senses, list):
        return (None, None)

    best_definition = None
    best_score = -10**9

    for sense in senses:
        if not isinstance(sense, dict):
            continue
        glosses = sense.get("glosses") or sense.get("raw_glosses") or []
        if not isinstance(glosses, list):
            continue
        tags = sense.get("tags") or []
        has_bad_tags = isinstance(tags, list) and bool({str(t).lower() for t in tags} & BAD_TAGS)
        for gloss in glosses:
            if not isinstance(gloss, str):
                continue
            definition = normalize_definition(gloss)
            if not definition:
                continue
            score = definition_score(definition, has_bad_tags)
            if score > best_score:
                best_score = score
                best_definition = definition

    if best_definition is None:
        return (None, None)
    return (best_definition, best_score)


def build_definitions(target: int) -> dict[str, str]:
    word_to_best: dict[str, tuple[int, str]] = {}
    lines = 0

    with gzip.open(KAIKKI_GZ_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            lines += 1
            if lines % 250000 == 0:
                print(f"Processed {lines:,} lines; collected {len(word_to_best):,} words ...")

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("lang_code") != "en":
                continue

            word = normalize_word(str(entry.get("word", "")))
            if not word:
                continue

            definition, score = extract_best_definition(entry)
            if not definition:
                continue

            existing = word_to_best.get(word)
            if existing is None or score > existing[0]:
                word_to_best[word] = (score, definition)

    definitions = {w: d for w, (_score, d) in word_to_best.items()}
    print(f"Collected {len(definitions):,} defined words (>= {MIN_LEN} letters).")

    if len(definitions) < target:
        print(
            f"Warning: collected {len(definitions):,}, below requested target {target:,}. "
            "Using maximum available from this source."
        )
    return definitions


def write_outputs(definitions: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sorted_words = sorted(definitions.keys())
    ordered_definitions = {w: definitions[w] for w in sorted_words}

    DEFINITIONS_PATH.write_text(
        json.dumps(ordered_definitions, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    WORDS_PATH.write_text("\n".join(sorted_words) + "\n", encoding="utf-8")

    print(f"Wrote {len(sorted_words):,} definitions -> {DEFINITIONS_PATH}")
    print(f"Wrote {len(sorted_words):,} words -> {WORDS_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Hangman dictionary data.")
    parser.add_argument("--target", type=int, default=200000, help="Desired minimum number of words.")
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep downloaded Kaikki .jsonl.gz after build (default: remove to save space).",
    )
    args = parser.parse_args()

    download_kaikki_if_missing()
    definitions = build_definitions(target=args.target)
    write_outputs(definitions)
    if not args.keep_source and KAIKKI_GZ_PATH.exists():
        KAIKKI_GZ_PATH.unlink()
        print(f"Removed source dump: {KAIKKI_GZ_PATH}")


if __name__ == "__main__":
    main()
