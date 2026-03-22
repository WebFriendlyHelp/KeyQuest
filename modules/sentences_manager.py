import os
import re
import unicodedata

from modules.app_paths import get_app_dir


DEFAULT_SPEED_TEST_SENTENCES = [
    "Keep going.",
    "Stay relaxed.",
    "Accuracy matters.",
    "Speed will come.",
    "One key at a time.",
    "Build your skills.",
    "Trust the process.",
    "You are improving.",
]


CHARACTER_NORMALIZATION_MAP = str.maketrans(
    {
        "\ufeff": "",
        "\u00ad": "",
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\u2060": "",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2026": "...",
        "\u2022": " ",
        "\u25cf": " ",
        "\u25e6": " ",
        "\u2043": "-",
        "\u2212": "-",
    }
)


MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "\ufffd")


def _repair_mojibake_text(text: str) -> str:
    """Repair common UTF-8/Latin-1 mojibake sequences when they appear."""
    repaired = text
    for _ in range(2):
        if not any(marker in repaired for marker in MOJIBAKE_MARKERS):
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def normalize_sentence_text(text: str) -> str:
    """Normalize copied text into the plain punctuation style used by built-in files."""
    normalized = _repair_mojibake_text(text)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = normalized.translate(CHARACTER_NORMALIZATION_MAP)
    normalized = re.sub(r"^\s*(?:[-*•●◦]\s+|\d+[.)]\s+)", "", normalized)
    normalized = "".join(
        ch
        for ch in normalized
        if unicodedata.category(ch) not in {"Cc", "Cs"}
        and not unicodedata.category(ch).startswith("So")
    )
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"([(\[{])\s+", r"\1", normalized)
    normalized = re.sub(r"\s+([)\]}])", r"\1", normalized)
    normalized = re.sub(r"([!?,])\1{1,}", r"\1", normalized)
    normalized = re.sub(r"\.{4,}", "...", normalized)
    normalized = re.sub(r"^[^\w\"'(\[]+|[^\w.!?\"')\]]+$", "", normalized)
    normalized = " ".join(normalized.split())
    return normalized.strip()


def _clean_sentence_lines(lines):
    """Return cleaned sentence lines in on-disk format."""
    sentences = []
    seen = set()
    for line in lines:
        if "\ufffd" in line:
            continue
        line = normalize_sentence_text(line)
        if not line:
            continue
        if not any(ch.isalnum() for ch in line):
            continue
        if any(marker in line for marker in MOJIBAKE_MARKERS):
            continue
        line_key = line.casefold()
        if line_key in seen:
            continue
        seen.add(line_key)
        sentences.append(line)
    return sentences


def _load_sentences_file(file_path: str):
    with open(file_path, "r", encoding="utf-8") as file:
        original_lines = file.readlines()

    sentences = _clean_sentence_lines(original_lines)
    cleaned_text = ""
    if sentences:
        cleaned_text = "\n".join(sentences) + "\n"

    original_text = "".join(original_lines)
    if cleaned_text != original_text:
        with open(file_path, "w", encoding="utf-8", newline="\n") as file:
            file.write(cleaned_text)

    return sentences


def get_sentence_topics_from_folder(app_dir: str = ""):
    """Load available practice topics from Sentences/*.txt filenames."""
    app_dir = app_dir or get_app_dir()
    sentences_dir = os.path.join(app_dir, "Sentences")
    topics = []
    try:
        if not os.path.isdir(sentences_dir):
            return []
        for entry in os.listdir(sentences_dir):
            if not entry.lower().endswith(".txt"):
                continue
            topic = os.path.splitext(entry)[0]
            if topic.lower() == "speedtest":
                continue
            topics.append(topic)
    except Exception:
        return []

    return sorted(set(topics), key=lambda t: t.lower())


def _find_topic_file(language: str, app_dir: str = "") -> str:
    """Return the matching Sentences file path for a practice topic."""
    app_dir = app_dir or get_app_dir()
    sentences_dir = os.path.join(app_dir, "Sentences")
    if not os.path.isdir(sentences_dir):
        return ""

    preferred_names = (
        f"{language}.txt",
        f"{language} Sentences.txt",
    )
    for filename in preferred_names:
        file_path = os.path.join(sentences_dir, filename)
        if os.path.exists(file_path):
            return file_path

    topic_key = language.casefold()
    try:
        for entry in os.listdir(sentences_dir):
            if not entry.lower().endswith(".txt"):
                continue
            topic = os.path.splitext(entry)[0]
            if topic.casefold() == topic_key:
                return os.path.join(sentences_dir, entry)
    except OSError:
        return ""

    return ""


def load_practice_sentences(language: str = "English", fallback_sentences=None, app_dir: str = ""):
    """Load sentences from the Sentences folder based on language/topic selection."""
    app_dir = app_dir or get_app_dir()
    fallback_sentences = list(fallback_sentences or DEFAULT_SPEED_TEST_SENTENCES)

    available_topics = set(get_practice_topics()) | set(get_sentence_topics_from_folder(app_dir=app_dir))
    normalized_topics = {topic.casefold(): topic for topic in available_topics}
    if language != "SpeedTest":
        language = normalized_topics.get(language.casefold(), language)
    if language not in available_topics and language != "SpeedTest":
        language = "English"

    try:
        file_path = _find_topic_file(language, app_dir=app_dir)
        if file_path:
            sentences = _load_sentences_file(file_path)
            print(f"Loaded {len(sentences)} {language} sentences from {os.path.basename(file_path)}")
            return sentences

        print(f"File not found for topic: {language}")
        print(f"Using {len(fallback_sentences)} fallback sentences")
        return list(fallback_sentences)
    except Exception as e:
        print(f"Could not load sentences for {language}: {e}")
        print(f"Using {len(fallback_sentences)} fallback sentences")
        return list(fallback_sentences)


def load_speed_test_sentences(app_dir: str = ""):
    """Load the speed test sentence pool."""
    return load_practice_sentences(
        "SpeedTest",
        fallback_sentences=DEFAULT_SPEED_TEST_SENTENCES,
        app_dir=app_dir,
    )


PRACTICE_TOPICS = [
    "English",
    "Spanish",
    "Windows Commands",
    "JAWS Commands",
    "NVDA Commands",
    "Science Facts",
    "History Facts",
    "Geography",
    "Math Vocabulary",
    "Literature Quotes",
    "Vocabulary Building",
]

PRACTICE_TOPIC_DISPLAY_NAMES = {
    "English": "General",
    "Spanish": "General Spanish",
}

PRACTICE_TOPIC_EXPLANATIONS = {
    "English": "Practice with general English sentences.",
    "Spanish": "Practice with general Spanish sentences.",
    "Windows Commands": "Learn Windows keyboard shortcuts and commands while typing.",
    "JAWS Commands": "Practice JAWS screen reader commands and shortcuts.",
    "NVDA Commands": "Practice NVDA screen reader commands and shortcuts.",
    "Science Facts": "Type interesting science facts while improving your skills.",
    "History Facts": "Learn historical events and dates while practicing typing.",
    "Geography": "Explore world geography facts and locations while typing.",
    "Math Vocabulary": "Practice mathematical terms and concepts.",
    "Literature Quotes": "Type famous quotes from classic literature.",
    "Vocabulary Building": "Build your vocabulary with grade-appropriate words and definitions.",
}


def get_practice_topics():
    """Return the canonical list of practice topic names."""
    return list(PRACTICE_TOPICS)


def get_practice_topic_display_name(topic: str) -> str:
    """Return the user-facing label for a practice topic."""
    return PRACTICE_TOPIC_DISPLAY_NAMES.get(topic, topic)


def get_practice_topic_explanation(topic: str) -> str:
    """Return a short explanation for a practice topic."""
    return PRACTICE_TOPIC_EXPLANATIONS.get(topic, "")
