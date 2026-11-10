"""Build the trimmed Hangman word list that ships with KeyQuest.

Why this exists
---------------
The full Wiktionary extraction (tools/dev/hangman_source/hangman_definitions.json,
git-ignored, from tools/dev/build_hangman_dictionary.py) is 62 MB with the word list and
holds 919,397 entries, most of them obscure, inflected or cross-references.
It never shipped: the build did not copy data/wordlists, so installed copies
fell back to Hangman's 16-word WORD_BANK.

The shipped list takes its WORDS from KeyQuest's own sentence files (words
learners already practise, written for this program, so family-friendly by
construction) and their DEFINITIONS from the full extraction, then drops
inflections, cross-references and anything whose definition mentions a
blocked term.

Licence: the definitions are Wiktionary text, CC BY-SA 4.0 (and GFDL), via
kaikki.org. The attribution file written next to the list must ship with it.
The selection of words is KeyQuest's own.

Usage::

    py -3.11 tools/dev/build_hangman_common.py

Run it after the sentence files or the full extraction change, and review
the list it prints of words that were left out.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SENTENCES_DIR = ROOT / "Sentences"
# The full extraction is a build input only and is git-ignored (moved out of
# data/wordlists on 2026-11-10; it is still in git history before that).
FULL_PATH = ROOT / "tools" / "dev" / "hangman_source" / "hangman_definitions.json"
OUT_PATH = ROOT / "data" / "wordlists" / "hangman_common.json"
ATTRIBUTION_PATH = ROOT / "data" / "wordlists" / "hangman_common_ATTRIBUTION.txt"

MIN_LEN = 5
MAX_DEFINITION_CHARS = 300

CROSS_REFERENCE_RE = re.compile(
    r"^(plural of|alternative (form|spelling) of|past tense of|past participle of|"
    r"present participle of|simple past|third-person singular|misspelling of|"
    r"comparative of|superlative of|synonym of|abbreviation of|initialism of|"
    r"obsolete form of|obsolete spelling of|misconstruction of|dated form of|dated spelling of|"
    r"archaic form of|archaic spelling of|eye dialect|nonstandard|ellipsis of|clipping of|"
    r"present participle and gerund of)",
    re.IGNORECASE,
)

# Wiktionary keys were lowercased, so "Nelson" or "Labor" can come back with a
# proper-noun sense ("The Australian Labor Party"). Those are left out.
PROPER_NOUN_SENSE_RE = re.compile(
    r"^(The [A-Z]|An? surname|An? (?:\w+ )?diminutive of|An? (?:\w+ )*given name|"
    r"An? (?:\w+ )*(?:unincorporated community|census-designated place|town|city|village) in [A-Z])"
)

# Sentence files written in another language would bring in words whose
# English Wiktionary sense has nothing to do with the sentence ("barra").
NON_ENGLISH_FILES = {"Spanish Sentences.txt"}

BLOCKED_RE = re.compile(
    r"\b(sex|sexual|sexually|penis|vagina|genital|genitals|intercourse|erotic|porn|"
    r"pornography|prostitute|prostitution|vulgar|obscene|offensive|derogatory|slur|"
    r"slang|masturbat\w*|rape|cocaine|heroin|drunk|intoxicat\w*)\b",
    re.IGNORECASE,
)

ATTRIBUTION = """Hangman word list (hangman_common.json)

The definitions in hangman_common.json are taken from Wiktionary
(https://en.wiktionary.org), extracted by kaikki.org
(https://kaikki.org/dictionary/English/), and shortened or selected by
KeyQuest. Wiktionary text is available under the Creative Commons
Attribution-ShareAlike 4.0 licence (CC BY-SA 4.0,
https://creativecommons.org/licenses/by-sa/4.0/) and the GNU Free
Documentation License. This file, hangman_common.json, is shared under
CC BY-SA 4.0 as well. The rest of KeyQuest is under its own MIT licence.
"""


def sentence_words() -> set[str]:
    """Words written in lower case somewhere in the English sentence files.

    A word that only ever appears capitalised ("Atacama", "Nelson") is a name
    in our text and is left out.
    """
    words: set[str] = set()
    for path in sorted(SENTENCES_DIR.glob("*.txt")):
        if path.name in NON_ENGLISH_FILES:
            continue
        for word in re.findall(r"[A-Za-z]+", path.read_text(encoding="utf-8")):
            if word.islower():
                words.add(word)
    return words


def main() -> int:
    if not FULL_PATH.exists():
        print(
            f"The full Wiktionary extraction was not found.\n"
            f"Expected folder: {FULL_PATH.parent}\n"
            f"Expected file:   {FULL_PATH.name}\n"
            f"This folder is git-ignored, so a fresh clone does not have it. Fill it with:\n"
            f"    py -3.11 tools/dev/build_hangman_dictionary.py\n"
            f"(it downloads the Kaikki English dump and writes the extraction there).",
            file=sys.stderr,
        )
        return 1
    full = json.loads(FULL_PATH.read_text(encoding="utf-8"))

    # An inflected form ("abilities": "plural of ability") is replaced by the
    # word it points to, which is just as familiar and has a real definition.
    candidates = sentence_words()
    for word in list(candidates):
        definition = full.get(word)
        if isinstance(definition, str):
            base = re.match(
                r"^(?:plural of|past tense of|past participle of|"
                r"present participle(?: and gerund)? of|"
                r"simple past(?: tense)? (?:and past participle )?of|"
                r"third-person singular simple present indicative of)\s+([a-z]+)\s*$",
                definition.strip().rstrip("."),
                re.IGNORECASE,
            )
            if base:
                candidates.add(base.group(1).lower())
    # No blind "strip the final s" step. One existed briefly and shipped
    # "darknes", "abilitie" and "compas" ("Obsolete spelling of ..." entries)
    # in place of the real words. A plural is only reduced to its singular
    # when the extraction itself says "plural of X" (the loop above), or when
    # the singular is itself written in the sentence files: then the plural's
    # own entry, often an odd sense ("buttons": the dung of sheep), is dropped
    # for a real word the learner has already typed.
    written = sentence_words()
    for word in list(candidates):
        if word.endswith("s") and word[:-1] in written:
            candidates.discard(word)

    kept: dict[str, str] = {}
    left_out: list[tuple[str, str]] = []
    for word in sorted(candidates):
        if len(word) < MIN_LEN or not (word.isascii() and word.isalpha()):
            continue
        definition = full.get(word)
        if not isinstance(definition, str) or not definition.strip():
            continue
        definition = " ".join(definition.split())
        if CROSS_REFERENCE_RE.match(definition):
            left_out.append((word, "cross-reference"))
            continue
        if PROPER_NOUN_SENSE_RE.match(definition):
            left_out.append((word, "proper-noun sense"))
            continue
        if BLOCKED_RE.search(definition) or BLOCKED_RE.search(word):
            left_out.append((word, "blocked term"))
            continue
        if len(definition) > MAX_DEFINITION_CHARS:
            definition = definition[:MAX_DEFINITION_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "..."
        kept[word] = definition

    OUT_PATH.write_text(json.dumps(kept, indent=0, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    ATTRIBUTION_PATH.write_text(ATTRIBUTION, encoding="utf-8")
    blocked = [w for w, why in left_out if why == "blocked term"]
    print(f"{len(kept)} words written to {OUT_PATH}")
    print(f"{len(left_out)} left out ({len(blocked)} for a blocked term): {', '.join(blocked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
