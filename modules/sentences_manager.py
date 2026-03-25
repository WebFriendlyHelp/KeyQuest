import json
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

MANIFEST_FILE_NAME = "manifest.json"
DEFAULT_SPEED_TEST_FILE = "SpeedTest.txt"
DEFAULT_SPEED_TEST_DISPLAY_NAME = "Configured Speed Test"
DEFAULT_TOPIC_DISPLAY_NAMES = {
    "english": "General",
    "spanish": "General Spanish",
}

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


def _sentences_dir(app_dir: str = "") -> str:
    app_dir = app_dir or get_app_dir()
    return os.path.join(app_dir, "Sentences")


def _topic_name_from_filename(filename: str) -> str:
    topic = os.path.splitext(filename)[0].strip()
    if topic.casefold().endswith(" sentences"):
        topic = topic[: -len(" Sentences")].strip()
    return topic


def _build_inferred_manifest(app_dir: str = "") -> dict:
    sentences_dir = _sentences_dir(app_dir)
    topics = []
    if os.path.isdir(sentences_dir):
        for entry in sorted(os.listdir(sentences_dir), key=str.lower):
            if not entry.lower().endswith(".txt"):
                continue
            if entry.casefold() == DEFAULT_SPEED_TEST_FILE.casefold():
                continue
            topic_name = _topic_name_from_filename(entry)
            if not topic_name:
                continue
            topics.append(
                {
                    "name": topic_name,
                    "file": entry,
                    "display_name": DEFAULT_TOPIC_DISPLAY_NAMES.get(
                        topic_name.casefold(),
                        topic_name,
                    ),
                    "explanation": "",
                }
            )
    return {
        "version": 1,
        "speed_test_file": DEFAULT_SPEED_TEST_FILE,
        "topics": topics,
    }


def _load_sentence_manifest(app_dir: str = "") -> dict:
    sentences_dir = _sentences_dir(app_dir)
    manifest_path = os.path.join(sentences_dir, MANIFEST_FILE_NAME)
    if not os.path.exists(manifest_path):
        return _build_inferred_manifest(app_dir)
    try:
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except (OSError, json.JSONDecodeError):
        return _build_inferred_manifest(app_dir)

    topics = manifest.get("topics")
    speed_test_file = manifest.get("speed_test_file")
    if not isinstance(topics, list) or not isinstance(speed_test_file, str) or not speed_test_file.strip():
        return _build_inferred_manifest(app_dir)
    return manifest


def _manifest_topic_entries(app_dir: str = "") -> list[dict]:
    manifest = _load_sentence_manifest(app_dir)
    entries = []
    for entry in manifest.get("topics", []):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        filename = str(entry.get("file") or "").strip()
        if not name or not filename:
            continue
        entries.append(
            {
                "name": name,
                "file": filename,
                "display_name": str(entry.get("display_name") or name).strip() or name,
                "explanation": str(entry.get("explanation") or "").strip(),
            }
        )
    return entries


def _manifest_topic_map(app_dir: str = "") -> dict[str, dict]:
    return {entry["name"].casefold(): entry for entry in _manifest_topic_entries(app_dir)}


def _manifest_speed_test_file(app_dir: str = "") -> str:
    manifest = _load_sentence_manifest(app_dir)
    speed_test_file = str(manifest.get("speed_test_file") or "").strip()
    return speed_test_file or DEFAULT_SPEED_TEST_FILE


def get_sentence_topics_from_folder(app_dir: str = ""):
    """Load available practice topics from the Sentences folder and manifest."""
    sentences_dir = _sentences_dir(app_dir)
    topics = set()
    manifest_path = os.path.join(sentences_dir, MANIFEST_FILE_NAME)
    if os.path.exists(manifest_path):
        topics.update(entry["name"] for entry in _manifest_topic_entries(app_dir))
    try:
        if not os.path.isdir(sentences_dir):
            return sorted(topics, key=lambda t: t.lower())
        for entry in os.listdir(sentences_dir):
            if not entry.lower().endswith(".txt"):
                continue
            topic = _topic_name_from_filename(entry)
            if topic.casefold() == "speedtest":
                continue
            topics.add(topic)
    except Exception:
        return sorted(topics, key=lambda t: t.lower())

    return sorted(topics, key=lambda t: t.lower())


def _find_topic_file(language: str, app_dir: str = "") -> str:
    """Return the matching Sentences file path for a practice topic."""
    sentences_dir = _sentences_dir(app_dir)
    if not os.path.isdir(sentences_dir):
        return ""

    if language == "SpeedTest":
        speed_test_file = _manifest_speed_test_file(app_dir)
        speed_test_path = os.path.join(sentences_dir, speed_test_file)
        if os.path.exists(speed_test_path):
            return speed_test_path

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

    manifest_topic = _manifest_topic_map(app_dir).get(language.casefold())
    if manifest_topic:
        manifest_path = os.path.join(sentences_dir, manifest_topic["file"])
        if os.path.exists(manifest_path):
            return manifest_path

    return ""


def load_practice_sentences(language: str = "English", fallback_sentences=None, app_dir: str = ""):
    """Load sentences from the Sentences folder based on language/topic selection."""
    fallback_sentences = list(fallback_sentences or DEFAULT_SPEED_TEST_SENTENCES)

    available_topics = set(get_practice_topics(app_dir=app_dir)) | set(
        get_sentence_topics_from_folder(app_dir=app_dir)
    )
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


def get_practice_topics(app_dir: str = ""):
    """Return the canonical list of practice topic names."""
    return [entry["name"] for entry in _manifest_topic_entries(app_dir)]


def get_practice_topic_display_name(topic: str, app_dir: str = "") -> str:
    """Return the user-facing label for a practice topic."""
    if topic == "SpeedTest":
        return DEFAULT_SPEED_TEST_DISPLAY_NAME
    manifest_topic = _manifest_topic_map(app_dir).get(topic.casefold())
    if manifest_topic:
        return manifest_topic["display_name"]
    return topic


def get_practice_topic_explanation(topic: str, app_dir: str = "") -> str:
    """Return a short explanation for a practice topic."""
    if topic == "SpeedTest":
        return "Uses the dedicated speed-test sentence file configured in the manifest."
    manifest_topic = _manifest_topic_map(app_dir).get(topic.casefold())
    if manifest_topic:
        return manifest_topic["explanation"]
    return ""
