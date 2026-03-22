"""Classic Hangman game with visual + speech parity."""

from pathlib import Path
import json
import random
import time

import pygame

from games.base_game import BaseGame
from games import sounds
from modules import speech_format
from ui.a11y import draw_controls_hint, draw_focus_frame
from ui.game_layout import draw_game_title
from ui.layout import draw_centered_text, draw_left_wrapped_text, get_content_width, get_footer_y
from ui.text_wrap import wrap_text


WORD_BANK = {
    "tomorrow": "The day after today.",
    "keyboard": "An input device with keys used for typing.",
    "practice": "Repeated work to improve a skill.",
    "science": "Systematic study of the natural world.",
    "history": "The study of past events.",
    "dragon": "A large mythical creature, often shown with wings and fire.",
    "phoenix": "A legendary bird that is reborn from ashes.",
    "accessibility": "Design that ensures people with disabilities can use a product.",
    "progress": "Forward movement toward a goal or improved state.",
    "adventure": "An unusual or exciting experience.",
    "learning": "The process of gaining knowledge or skill.",
    "challenge": "A difficult task that tests ability.",
    "trainer": "A person or tool that helps build a skill.",
    "journey": "A process of moving from one level to another.",
    "clarity": "The quality of being clear and easy to understand.",
    "mastery": "Complete command of a skill or subject.",
}

EXTERNAL_WORDLIST_PATH = Path(__file__).resolve().parents[1] / "data" / "wordlists" / "hangman_words.txt"
EXTERNAL_DEFINITIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "wordlists" / "hangman_definitions.json"
_EXTERNAL_WORDS_CACHE = None
_EXTERNAL_DEFINITIONS_CACHE = None
_CANDIDATE_POOL_CACHE = None
_CANDIDATE_LENGTH_BUCKETS_CACHE = None
MIN_WORD_LENGTH = 5


def _is_plain_ascii_word(word: str) -> bool:
    """Return True for simple A-Z words only."""
    return word.isascii() and word.isalpha()


def _determine_max_word_length() -> int:
    """Return maximum allowed word length based on available dictionary data."""
    lengths: list[int] = []

    definitions = load_external_definitions()
    for raw_word in definitions.keys():
        word = raw_word.strip().lower()
        if _is_plain_ascii_word(word) and len(word) >= MIN_WORD_LENGTH:
            lengths.append(len(word))

    if not lengths:
        for raw_word in WORD_BANK.keys():
            word = raw_word.strip().lower()
            if _is_plain_ascii_word(word) and len(word) >= MIN_WORD_LENGTH:
                lengths.append(len(word))

    return max(lengths) if lengths else MIN_WORD_LENGTH


def load_external_words() -> list[str]:
    """Load and cache external hangman words with fair length bounds."""
    global _EXTERNAL_WORDS_CACHE
    if _EXTERNAL_WORDS_CACHE is not None:
        return _EXTERNAL_WORDS_CACHE

    if not EXTERNAL_WORDLIST_PATH.exists():
        _EXTERNAL_WORDS_CACHE = []
        return _EXTERNAL_WORDS_CACHE

    max_word_length = _determine_max_word_length()

    try:
        with EXTERNAL_WORDLIST_PATH.open("r", encoding="utf-8") as f:
            words = set()
            for line in f:
                word = line.strip().lower()
                if MIN_WORD_LENGTH <= len(word) <= max_word_length and _is_plain_ascii_word(word):
                    words.add(word)
            _EXTERNAL_WORDS_CACHE = sorted(words)
    except Exception:
        _EXTERNAL_WORDS_CACHE = []
    return _EXTERNAL_WORDS_CACHE


def load_external_definitions() -> dict[str, str]:
    """Load and cache external definitions for offline lookup."""
    global _EXTERNAL_DEFINITIONS_CACHE
    if _EXTERNAL_DEFINITIONS_CACHE is not None:
        return _EXTERNAL_DEFINITIONS_CACHE

    if not EXTERNAL_DEFINITIONS_PATH.exists():
        _EXTERNAL_DEFINITIONS_CACHE = {}
        return _EXTERNAL_DEFINITIONS_CACHE

    try:
        with EXTERNAL_DEFINITIONS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            _EXTERNAL_DEFINITIONS_CACHE = data if isinstance(data, dict) else {}
    except Exception:
        _EXTERNAL_DEFINITIONS_CACHE = {}
    return _EXTERNAL_DEFINITIONS_CACHE


def load_candidate_pool() -> list[tuple[str, str]]:
    """Load and cache playable (word, definition) candidates.

    Every candidate is guaranteed to have a definition.
    """
    global _CANDIDATE_POOL_CACHE
    if _CANDIDATE_POOL_CACHE is not None:
        return _CANDIDATE_POOL_CACHE

    external_definitions = load_external_definitions()
    max_word_length = _determine_max_word_length()
    pool: list[tuple[str, str]] = []

    # Primary source: offline dictionary definitions.
    for raw_word, raw_definition in external_definitions.items():
        word = raw_word.strip().lower()
        definition = raw_definition.strip() if isinstance(raw_definition, str) else ""
        if MIN_WORD_LENGTH <= len(word) <= max_word_length and _is_plain_ascii_word(word) and definition:
            pool.append((word, definition))

    # Curated fallback only (no generic placeholder definitions).
    if not pool:
        for raw_word, raw_definition in WORD_BANK.items():
            word = raw_word.strip().lower()
            definition = raw_definition.strip()
            if MIN_WORD_LENGTH <= len(word) <= max_word_length and _is_plain_ascii_word(word) and definition:
                pool.append((word, definition))

    # Deduplicate while preserving order.
    deduped: list[tuple[str, str]] = []
    seen_words: set[str] = set()
    for word, definition in pool:
        if word in seen_words:
            continue
        seen_words.add(word)
        deduped.append((word, definition))

    _CANDIDATE_POOL_CACHE = deduped
    return _CANDIDATE_POOL_CACHE


def load_candidate_length_buckets() -> dict[int, list[tuple[str, str]]]:
    """Group candidates by exact word length for better variation."""
    global _CANDIDATE_LENGTH_BUCKETS_CACHE
    if _CANDIDATE_LENGTH_BUCKETS_CACHE is not None:
        return _CANDIDATE_LENGTH_BUCKETS_CACHE

    buckets: dict[int, list[tuple[str, str]]] = {}
    for word, definition in load_candidate_pool():
        buckets.setdefault(len(word), []).append((word, definition))

    _CANDIDATE_LENGTH_BUCKETS_CACHE = buckets
    return _CANDIDATE_LENGTH_BUCKETS_CACHE


def build_spoken_word_progress(word: str, guessed_letters: set[str]) -> str:
    """Return a speakable progress string with 'blank' placeholders."""
    tokens = []
    for ch in word:
        if ch.isalpha():
            tokens.append(ch if ch in guessed_letters else "blank")
        elif ch == " ":
            tokens.append("space")
        else:
            tokens.append(ch)
    return ", ".join(tokens)


def build_visual_word_progress(word: str, guessed_letters: set[str]) -> str:
    """Return a visual progress string with underscores for unknown letters."""
    tokens = []
    for ch in word:
        if ch == " ":
            tokens.append("/")
        elif not ch.isalpha():
            tokens.append(ch)
        elif ch in guessed_letters:
            tokens.append(ch.upper())
        else:
            tokens.append("_")
    return " ".join(tokens)


def describe_hangman_stage(stage: int) -> str:
    """Speech description for each wrong-guess visual stage."""
    descriptions = {
        1: "Head drawn.",
        2: "Torso drawn.",
        3: "Left arm drawn.",
        4: "Right arm drawn.",
        5: "Left leg drawn.",
        6: "Right leg drawn.",
        7: "Left hand drawn.",
        8: "Right hand drawn.",
        9: "Left foot and right foot drawn.",
        10: "Face details drawn.",
    }
    return descriptions.get(stage, "Hangman updated.")


def build_sentence_practice_items(word: str, definition: str = "", count: int = 5) -> list[str]:
    """Generate varied sentence-practice prompts containing the solved word."""
    token = word.lower().strip()
    target_count = max(1, int(count))

    definition_text = (definition or "").strip().rstrip(".")
    context_text = definition_text if definition_text else "a word from this round"

    style_templates = {
        "story": [
            "In the story, {word} appeared just before the final clue.",
            "By the last chapter, {word} changed everything for the hero.",
            "A quiet hint led me to {word} before anyone else guessed it.",
        ],
        "mystery": [
            "The detective circled {word} as the missing piece of the case.",
            "Each clue pointed toward {word}, even when the trail went cold.",
            "The evidence looked random until {word} connected every detail.",
        ],
        "science": [
            "In science class, {word} became the key term in our discussion.",
            "Our experiment notes made {word} easier to remember and explain.",
            "The lab prompt used {word} to test careful observation.",
        ],
        "adventure": [
            "On the map, {word} marked the place we had to reach by sunrise.",
            "After the storm, {word} became our signal to keep moving.",
            "The journey felt impossible until {word} showed up in the clue.",
        ],
        "school": [
            "During typing practice, {word} was the line everyone wanted to master.",
            "In class today, {word} sparked a quick debate and a lot of laughs.",
            "My notes stayed clear because I wrote {word} with full focus.",
        ],
        "definition": [
            "{word} means {context}, and that clue made the answer click.",
            "Hearing that {word} means {context} made this round feel easier.",
            "The definition, {context}, helped me lock in {word}.",
        ],
        "reflective": [
            "I solved {word} by slowing down and checking each letter.",
            "Once I understood the clue, typing {word} felt natural.",
            "A little patience turned {word} from tricky to clear.",
        ],
    }

    # Pick unique sentence styles first, then fill extras from remaining templates if needed.
    selected_styles = list(style_templates.keys())
    random.shuffle(selected_styles)

    sentences: list[str] = []
    used_sentences: set[str] = set()

    for style in selected_styles:
        template = random.choice(style_templates[style])
        sentence = template.format(word=token, context=context_text)
        if sentence not in used_sentences:
            used_sentences.add(sentence)
            sentences.append(sentence)
        if len(sentences) >= target_count:
            return sentences

    fallback_pool: list[str] = []
    for templates in style_templates.values():
        for template in templates:
            fallback_pool.append(template.format(word=token, context=context_text))
    random.shuffle(fallback_pool)

    for sentence in fallback_pool:
        if sentence in used_sentences:
            continue
        used_sentences.add(sentence)
        sentences.append(sentence)
        if len(sentences) >= target_count:
            break

    return sentences


class HangmanGame(BaseGame):
    NAME = "Hangman"
    DESCRIPTION = "Guess the hidden word one letter at a time. Wrong guesses add hangman visuals up to 10 steps."
    INSTRUCTIONS = (
        "At round start, Hangman announces the guess prompt and total letter count. "
        "Guess letters to reveal the word. Repeated guesses are allowed and never cost a guess. "
        "Wrong guesses add a visual stage, then announce progress and remaining guesses. "
        "After each round, use the results menu to review word and definition, copy them, "
        "play again, or start sentence practice with the solved word."
    )
    HOTKEYS = """Gameplay
A-Z: Guess letter
Ctrl+Space: Read current word progress
Alt+R: Read remaining guesses
Alt+U: Read guessed letters
Alt+L: Read letters left and total letters
Left/Right: Move through current word progress
Home/End: Jump to start or end of current word progress
Esc x3: Exit to main menu

Results menu
Up/Down: Move through result items
Enter/Space: Select or re-read selected item
Esc: Back to game menu

Sentence practice
Type sentence text
Enter: Submit sentence
Ctrl+Space: Read remaining text
Esc x3: Exit to main menu"""

    def __init__(
        self,
        screen,
        fonts,
        speech,
        play_sound_func,
        show_info_dialog_func,
        session_complete_callback=None,
    ):
        super().__init__(
            screen,
            fonts,
            speech,
            play_sound_func,
            show_info_dialog_func,
            session_complete_callback,
        )
        self.running = False
        self.word = ""
        self.word_definition = ""
        self.guessed_letters = set()
        self.max_wrong = 10
        self.remaining_guesses = self.max_wrong
        self.wrong_guesses = 0
        self.correct_guesses = 0
        self.guess_attempts = 0
        self.repeated_guesses = 0
        self.last_feedback = "Guess a letter."
        self.game_start_time = 0.0
        self.results_menu_items = []
        self.results_menu_index = 0
        self.round_headline = ""
        self.round_ending = ""
        self.round_accuracy = 0.0
        self.round_session_stats = {}
        self.round_results_lines: list[str] = []
        self.word_cursor_index = 0
        self.sentence_items: list[str] = []
        self.sentence_index = 0
        self.sentence_typed = ""
        self.sentence_correct = 0
        self.sentence_feedback = "Type the sentence exactly as shown, including capitals and punctuation."

    def _choose_word(self) -> tuple[str, str]:
        buckets = load_candidate_length_buckets()
        if not buckets:
            return ("typing", "The act of entering text using a keyboard.")
        lengths = sorted(buckets.keys())

        # Blend toward common-length words, while still allowing short and very long outliers.
        total_words = sum(len(words) for words in buckets.values())
        weighted_avg = (
            sum(length * len(buckets[length]) for length in lengths) / max(1, total_words)
        )
        # "Common speech" center: keep near practical typing lengths.
        center = max(5.0, min(10.0, weighted_avg))

        short_lengths = [length for length in lengths if length <= 6]
        very_long_lengths = [length for length in lengths if length >= 28]

        roll = random.random()
        if short_lengths and roll < 0.15:
            chosen_length = random.choice(short_lengths)
            return random.choice(buckets[chosen_length])
        if very_long_lengths and roll < 0.22:
            chosen_length = random.choice(very_long_lengths)
            return random.choice(buckets[chosen_length])

        # Default path: weighted toward the center, with non-zero chance for all lengths.
        weighted_lengths = []
        for length in lengths:
            distance = abs(length - center)
            # Smoothly reduce weight farther from center; never drop to zero.
            weight = max(0.08, 1.0 / (1.0 + (distance / 2.5) ** 2))
            # Keep length-frequency influence so common lengths appear naturally.
            weight *= max(1, len(buckets[length]))
            weighted_lengths.append(weight)

        chosen_length = random.choices(lengths, weights=weighted_lengths, k=1)[0]
        return random.choice(buckets[chosen_length])

    def start_playing(self):
        self.mode = "PLAYING"
        self.running = True
        self.word, self.word_definition = self._choose_word()
        self.guessed_letters = set()
        self.remaining_guesses = self.max_wrong
        self.wrong_guesses = 0
        self.correct_guesses = 0
        self.guess_attempts = 0
        self.repeated_guesses = 0
        self.last_feedback = "New game started. Guess a letter."
        self.word_cursor_index = 0
        self.game_start_time = time.time()
        self.speech.say(
            "Hangman started.",
            priority=True,
            protect_seconds=1.4,
        )
        self.speech.say(
            "Guess a letter.",
            priority=True,
            protect_seconds=2.0,
        )
        pygame.time.wait(250)
        self.speech.say(
            f"New word has {len(self.word)} letters.",
            priority=True,
            protect_seconds=1.8,
        )
        # Keep the start cue subtle so it does not mask spoken instructions.
        self.play_sound((sounds.level_start() * 0.2).astype("float32"))

    def announce_word_progress(self, priority: bool = False, interrupt: bool = True):
        progress = build_spoken_word_progress(self.word, self.guessed_letters)
        self.speech.say(
            progress,
            priority=priority,
            protect_seconds=1.6 if priority else 0.0,
            interrupt=interrupt,
        )

    def announce_guessed_letters(self):
        if not self.guessed_letters:
            self.speech.say("No guessed letters yet.", priority=True)
            return
        letters = ", ".join(sorted(ch.upper() for ch in self.guessed_letters))
        self.speech.say(f"Guessed letters: {letters}", priority=True)

    def announce_remaining(self, interrupt: bool = True):
        self.speech.say(
            f"Remaining guesses: {self.remaining_guesses}",
            priority=True,
            interrupt=interrupt,
        )

    def announce_letter_count(self):
        total_letters = sum(1 for ch in self.word if ch.isalpha())
        remaining_letters = sum(1 for ch in self.word if ch.isalpha() and ch not in self.guessed_letters)
        left_label = "letter" if remaining_letters == 1 else "letters"
        total_label = "letter" if total_letters == 1 else "letters"
        self.speech.say(
            f"{remaining_letters} {left_label} left. {total_letters} total {total_label}.",
            priority=True,
        )

    def _get_visual_progress_tokens(self) -> list[str]:
        tokens = []
        for ch in self.word:
            if ch == " ":
                tokens.append("/")
            elif not ch.isalpha():
                tokens.append(ch)
            elif ch in self.guessed_letters:
                tokens.append(ch.upper())
            else:
                tokens.append("_")
        return tokens

    def _get_cursor_spoken_token(self) -> str:
        if not self.word:
            return "blank"
        ch = self.word[self.word_cursor_index]
        if ch == " ":
            return "space"
        if ch.isalpha():
            return ch if ch in self.guessed_letters else "blank"
        return ch

    def _announce_cursor_position(self):
        if not self.word:
            return
        token = self._get_cursor_spoken_token()
        self.last_feedback = f"{token}. Position {self.word_cursor_index + 1} of {len(self.word)}."
        self.speech.say(
            f"{token}. Position {self.word_cursor_index + 1} of {len(self.word)}.",
            priority=True,
        )

    def _move_word_cursor(self, delta: int):
        if not self.word:
            return
        max_index = len(self.word) - 1
        self.word_cursor_index = max(0, min(max_index, self.word_cursor_index + delta))
        self._announce_cursor_position()

    def _set_word_cursor(self, index: int):
        if not self.word:
            return
        max_index = len(self.word) - 1
        self.word_cursor_index = max(0, min(max_index, index))
        self._announce_cursor_position()

    def _is_word_solved(self) -> bool:
        for ch in self.word:
            if ch.isalpha() and ch not in self.guessed_letters:
                return False
        return True

    def _draw_hangman(self):
        # Gallows
        pygame.draw.line(self.screen, self.FG, (120, 500), (300, 500), 4)
        pygame.draw.line(self.screen, self.FG, (170, 500), (170, 120), 4)
        pygame.draw.line(self.screen, self.FG, (170, 120), (350, 120), 4)
        pygame.draw.line(self.screen, self.FG, (350, 120), (350, 165), 4)

        # Body parts
        if self.wrong_guesses >= 1:  # head
            pygame.draw.circle(self.screen, self.DANGER, (350, 195), 30, width=3)
        if self.wrong_guesses >= 2:  # torso
            pygame.draw.line(self.screen, self.DANGER, (350, 225), (350, 330), 3)
        if self.wrong_guesses >= 3:  # left arm
            pygame.draw.line(self.screen, self.DANGER, (350, 255), (310, 295), 3)
        if self.wrong_guesses >= 4:  # right arm
            pygame.draw.line(self.screen, self.DANGER, (350, 255), (390, 295), 3)
        if self.wrong_guesses >= 5:  # left leg
            pygame.draw.line(self.screen, self.DANGER, (350, 330), (315, 390), 3)
        if self.wrong_guesses >= 6:  # right leg
            pygame.draw.line(self.screen, self.DANGER, (350, 330), (385, 390), 3)
        if self.wrong_guesses >= 7:  # left hand
            pygame.draw.circle(self.screen, self.DANGER, (306, 300), 5, width=2)
        if self.wrong_guesses >= 8:  # right hand
            pygame.draw.circle(self.screen, self.DANGER, (394, 300), 5, width=2)
        if self.wrong_guesses >= 9:  # feet
            pygame.draw.line(self.screen, self.DANGER, (305, 394), (325, 394), 3)
            pygame.draw.line(self.screen, self.DANGER, (375, 394), (395, 394), 3)
        if self.wrong_guesses >= 10:  # face details
            pygame.draw.line(self.screen, self.DANGER, (338, 186), (346, 194), 2)
            pygame.draw.line(self.screen, self.DANGER, (346, 186), (338, 194), 2)
            pygame.draw.line(self.screen, self.DANGER, (354, 186), (362, 194), 2)
            pygame.draw.line(self.screen, self.DANGER, (362, 186), (354, 194), 2)
            pygame.draw.arc(self.screen, self.DANGER, pygame.Rect(338, 205, 24, 16), 3.5, 5.9, 2)

    def _announce_results_menu(self):
        item = self.results_menu_items[self.results_menu_index]
        if item.startswith("Word:"):
            self.speech.say(item, priority=True, protect_seconds=1.2)
            return
        if item.startswith("Definition:"):
            self.speech.say(item, priority=True, protect_seconds=2.0)
            return
        self.speech.say(item, priority=True, protect_seconds=1.2)

    def _set_clipboard_text(self, text: str) -> bool:
        """Copy text to system clipboard."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return True
        except Exception:
            return False

    def copy_word_and_definition(self):
        payload = f"Word: {self.word.upper()}\nDefinition: {self.word_definition}"
        if self._set_clipboard_text(payload):
            self.speech.say("Copied word and definition to clipboard.", priority=True, protect_seconds=1.4)
        else:
            self.speech.say("Unable to copy to clipboard.", priority=True, protect_seconds=1.4)

    def _wrap_text(self, text: str, max_chars: int = 80) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def start_sentence_practice(self):
        self.mode = "SENTENCE_PRACTICE"
        self.sentence_items = build_sentence_practice_items(self.word, definition=self.word_definition, count=5)
        self.sentence_index = 0
        self.sentence_typed = ""
        self.sentence_correct = 0
        self.sentence_feedback = "Match capitals and punctuation."
        self.speech.say(
            "Sentence practice started.",
            priority=True,
            protect_seconds=1.4,
        )
        self.announce_current_sentence()

    def announce_current_sentence(self):
        if not self.sentence_items:
            return
        current = self.sentence_items[self.sentence_index]
        self.speech.say(
            f"Sentence {self.sentence_index + 1} of {len(self.sentence_items)}. {current}",
            priority=True,
            protect_seconds=2.5,
        )

    def announce_sentence_remaining(self):
        if not self.sentence_items:
            return
        current = self.sentence_items[self.sentence_index]
        typed = self.sentence_typed
        typed_pos = min(len(typed), len(current))
        remaining = current[typed_pos:]
        self.speech.say(
            speech_format.build_remaining_text_feedback(remaining),
            priority=True,
            protect_seconds=2.0,
        )

    def _finish_round(self, won: bool):
        self.running = False
        elapsed_minutes = max(0.01, (time.time() - self.game_start_time) / 60.0)
        accuracy = (self.correct_guesses / self.guess_attempts * 100.0) if self.guess_attempts > 0 else 0.0
        remaining = self.remaining_guesses

        if won:
            self.play_sound(sounds.level_complete())
            headline = "YOU WIN!"
            ending = "Great word solving."
        else:
            self.play_sound(sounds.game_over())
            headline = "GAME OVER"
            ending = "Better luck next round."

        self.round_headline = headline
        self.round_ending = ending
        self.round_accuracy = accuracy
        self.round_session_stats = {
            "session_duration_minutes": elapsed_minutes,
            "pet_xp": max(10, int(self.correct_guesses * 3)),
            "words_completed": 1 if won else 0,
        }
        self.round_results_lines = [
            f"Word: {self.word.upper()}",
            f"Correct guesses: {self.correct_guesses}",
            f"Wrong guesses: {self.wrong_guesses}",
            f"Repeated guesses: {self.repeated_guesses}",
            f"Accuracy: {accuracy:.0f}%",
            f"Remaining guesses: {remaining}",
            ending,
        ]
        if self.on_session_complete:
            self.on_session_complete(self, self.round_session_stats)

        self.mode = "RESULTS"
        self.results_menu_items = [
            f"Word: {self.word.upper()}",
            f"Definition: {self.word_definition}",
            "Copy Word + Definition",
            "Play Again",
            "Type Practice Sentences",
            "Back to Game Menu",
        ]
        self.results_menu_index = 0
        self.speech.say(
            f"{headline}. Word was {self.word}. Definition: {self.word_definition}",
            priority=True,
            protect_seconds=2.5,
        )
        self._announce_results_menu()

    def process_guess(self, letter: str):
        letter = letter.lower()
        if not letter.isalpha() or len(letter) != 1:
            return

        if letter in self.guessed_letters:
            self.repeated_guesses += 1
            self.last_feedback = f"{letter.upper()} was already guessed. No penalty."
            self.speech.say(self.last_feedback, priority=True)
            self.play_sound(sounds.menu_move())
            self.announce_word_progress(priority=True)
            return

        self.guessed_letters.add(letter)
        self.guess_attempts += 1

        if letter in self.word:
            self.correct_guesses += 1
            self.last_feedback = f"Correct letter: {letter.upper()}."
            self.speech.say(self.last_feedback, priority=True)
            self.play_sound(sounds.letter_hit())
            self.announce_word_progress(priority=True)
            if self._is_word_solved():
                self.speech.say(f"Word solved: {self.word}.", priority=True, protect_seconds=1.8)
                self._finish_round(won=True)
            return

        if self.remaining_guesses > 0:
            self.remaining_guesses -= 1
        self.wrong_guesses = self.max_wrong - self.remaining_guesses
        stage_description = describe_hangman_stage(self.wrong_guesses)
        self.last_feedback = f"Wrong letter: {letter.upper()}."
        self.speech.say(stage_description, priority=True, protect_seconds=1.2, interrupt=True)
        self.play_sound(sounds.letter_miss())
        self.announce_word_progress(priority=True, interrupt=False)
        self.announce_remaining(interrupt=False)
        if self.remaining_guesses <= 0:
            self.speech.say(f"No guesses left. The word was {self.word}.", priority=True, protect_seconds=1.8)
            self._finish_round(won=False)

    def handle_game_input(self, event, mods):
        if event.key == pygame.K_ESCAPE:
            elapsed_minutes = max(0.01, (time.time() - self.game_start_time) / 60.0)
            if self.on_session_complete:
                self.on_session_complete(
                    self,
                    {
                        "session_duration_minutes": elapsed_minutes,
                        "pet_xp": max(10, int(self.correct_guesses * 3)),
                        "words_completed": 0,
                    },
                )
            self.running = False
            self.mode = "MENU"
            self.speech.say("Returning to game menu.", priority=True)
            self.say_game_menu()
            return None

        if event.key == pygame.K_SPACE and (mods & pygame.KMOD_CTRL):
            self.announce_word_progress(priority=True)
            return None

        if event.key == pygame.K_r and (mods & pygame.KMOD_ALT):
            self.announce_remaining()
            return None

        if event.key == pygame.K_u and (mods & pygame.KMOD_ALT):
            self.announce_guessed_letters()
            return None

        if event.key == pygame.K_l and (mods & pygame.KMOD_ALT):
            self.announce_letter_count()
            return None

        if event.key == pygame.K_LEFT:
            self._move_word_cursor(-1)
            return None

        if event.key == pygame.K_RIGHT:
            self._move_word_cursor(1)
            return None

        if event.key == pygame.K_HOME:
            self._set_word_cursor(0)
            return None

        if event.key == pygame.K_END:
            self._set_word_cursor(len(self.word) - 1)
            return None

        if not self.running:
            return None

        ch = event.unicode.lower() if event.unicode else ""
        if ch and ch.isalpha() and len(ch) == 1:
            self.process_guess(ch)
        return None

    def handle_results_input(self, event):
        if event.key == pygame.K_ESCAPE:
            self.mode = "MENU"
            self.say_game_menu()
            return None
        if event.key == pygame.K_UP:
            self.results_menu_index = (self.results_menu_index - 1) % len(self.results_menu_items)
            self.play_sound(sounds.menu_move())
            self._announce_results_menu()
            return None
        if event.key == pygame.K_DOWN:
            self.results_menu_index = (self.results_menu_index + 1) % len(self.results_menu_items)
            self.play_sound(sounds.menu_move())
            self._announce_results_menu()
            return None
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = self.results_menu_items[self.results_menu_index]
            if choice.startswith("Word:"):
                self.speech.say(choice, priority=True)
            elif choice.startswith("Definition:"):
                self.speech.say(choice, priority=True, protect_seconds=2.0)
            elif choice == "Copy Word + Definition":
                self.copy_word_and_definition()
            elif choice == "Play Again":
                self.play_sound(sounds.menu_select())
                self.start_playing()
            elif choice == "Type Practice Sentences":
                self.play_sound(sounds.menu_select())
                self.start_sentence_practice()
            else:
                self.play_sound(sounds.menu_select())
                self.mode = "MENU"
                self.say_game_menu()
        return None

    def handle_sentence_practice_input(self, event, mods):
        if event.key == pygame.K_ESCAPE:
            self.mode = "RESULTS"
            self._announce_results_menu()
            return None
        if event.key == pygame.K_SPACE and (mods & pygame.KMOD_CTRL):
            self.announce_sentence_remaining()
            return None
        if event.key == pygame.K_BACKSPACE:
            if self.sentence_typed:
                self.sentence_typed = self.sentence_typed[:-1]
            return None
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            target = self.sentence_items[self.sentence_index]
            if self.sentence_typed != target:
                self.sentence_feedback = "Sentence does not match. Try again."
                self.play_sound(sounds.letter_miss())
                self.speech.say("Sentence does not match. Try again.", priority=True)
            return None

        ch = event.unicode if event.unicode else ""
        if ch and ch.isprintable() and ch not in ("\r", "\n"):
            target = self.sentence_items[self.sentence_index]
            pos = len(self.sentence_typed)
            if pos < len(target) and ch == target[pos]:
                self.sentence_typed += ch
                if self.sentence_typed == target:
                    self.sentence_correct += 1
                    self.sentence_feedback = "Correct sentence."
                    self.play_sound(sounds.level_complete())
                    self.speech.say("Correct sentence.", priority=True)
                    self.sentence_index += 1
                    self.sentence_typed = ""
                    if self.sentence_index >= len(self.sentence_items):
                        self.mode = "RESULTS"
                        self.speech.say(
                            f"Sentence practice complete. {self.sentence_correct} of {len(self.sentence_items)} correct.",
                            priority=True,
                            protect_seconds=2.0,
                        )
                        self._announce_results_menu()
                        return None
                    self.announce_current_sentence()
            else:
                remaining = target[pos:]
                self.sentence_feedback = speech_format.build_remaining_text_feedback(remaining)
                self.play_sound(sounds.letter_miss())
                self.speech.say(self.sentence_feedback, priority=True, protect_seconds=1.5)
        return None

    def handle_input(self, event, mods):
        """Route input for menu, gameplay, round results, and sentence practice."""
        if self.mode == "MENU":
            return self.handle_menu_input(event, mods)
        if self.mode == "PLAYING":
            return self.handle_game_input(event, mods)
        if self.mode == "RESULTS":
            return self.handle_results_input(event)
        if self.mode == "SENTENCE_PRACTICE":
            return self.handle_sentence_practice_input(event, mods)
        return None

    def draw_game(self):
        screen_w, screen_h = self._screen_size()
        draw_game_title(
            screen=self.screen,
            title_font=self.title_font,
            text=self.NAME,
            color=self.ACCENT,
            screen_w=screen_w,
            y=18,
        )

        self._draw_hangman()

        panel_center_x = max(590, screen_w // 2 + 120)
        panel_max_width = max(220, screen_w - panel_center_x - 30)
        draw_centered_text(
            screen=self.screen,
            font=self.small_font,
            text="Word progress",
            color=self.ACCENT,
            screen_w=panel_center_x * 2,
            y=150,
        )

        progress_tokens = self._get_visual_progress_tokens()
        token_surfaces = []
        spacing = 16
        total_width = 0
        for token in progress_tokens:
            surf, _ = self.text_font.render(token, self.FG)
            token_surfaces.append(surf)
            total_width += surf.get_width()
        if token_surfaces:
            total_width += spacing * (len(token_surfaces) - 1)
        x = panel_center_x - total_width // 2
        y = 200
        for idx, surf in enumerate(token_surfaces):
            rect = surf.get_rect(topleft=(x, y))
            self.screen.blit(surf, rect)
            if idx == self.word_cursor_index and self.word:
                draw_focus_frame(self.screen, rect, self.GOOD, self.ACCENT)
            x += surf.get_width() + spacing

        guessed = ", ".join(sorted(ch.upper() for ch in self.guessed_letters)) if self.guessed_letters else "None"
        guessed_lines = wrap_text(self.small_font, f"Guessed: {guessed}", panel_max_width, self.ACCENT)
        y = 260
        for line in guessed_lines:
            guessed_surf, _ = self.small_font.render(line, self.ACCENT)
            self.screen.blit(guessed_surf, (panel_center_x - guessed_surf.get_width() // 2, y))
            y += guessed_surf.get_height() + 4

        remaining = self.remaining_guesses
        remain_color = self.DANGER if remaining <= 2 else self.GOOD
        remaining_lines = wrap_text(self.text_font, f"Remaining guesses: {remaining}", panel_max_width, remain_color)
        y = max(y + 8, 320)
        for line in remaining_lines:
            remaining_surf, _ = self.text_font.render(line, remain_color)
            self.screen.blit(remaining_surf, (panel_center_x - remaining_surf.get_width() // 2, y))
            y += remaining_surf.get_height() + 4

        letters_surf, _ = self.small_font.render(f"Letters in word: {len(self.word)}", self.ACCENT)
        self.screen.blit(letters_surf, (panel_center_x - letters_surf.get_width() // 2, y + 4))
        y += letters_surf.get_height() + 12

        feedback_lines = wrap_text(self.small_font, self.last_feedback, panel_max_width, self.FG)
        for line in feedback_lines:
            feedback_surf, _ = self.small_font.render(line, self.FG)
            self.screen.blit(feedback_surf, (panel_center_x - feedback_surf.get_width() // 2, y))
            y += feedback_surf.get_height() + 4

        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Type letters; Tab word progress; Ctrl+Space guessed count; Esc quit",
            screen_w=screen_w,
            y=get_footer_y(screen_h),
            accent=self.FG,
        )

    def draw_results_menu(self):
        screen_w, screen_h = self._screen_size()
        draw_game_title(
            screen=self.screen,
            title_font=self.title_font,
            text=self.round_headline,
            color=self.ACCENT,
            screen_w=screen_w,
            y=18,
        )

        y = 78
        for line in self.round_results_lines:
            block = draw_left_wrapped_text(
                screen=self.screen,
                font=self.small_font,
                text=line,
                color=self.FG,
                x=60,
                y=y,
                max_width=get_content_width(screen_w, side_margin=60),
                line_gap=4,
            )
            y = block.bottom + 4

        y = max(370, y + 18)
        for idx, item in enumerate(self.results_menu_items):
            selected = idx == self.results_menu_index
            display_item = item
            if item.startswith("Definition:"):
                display_item = item
            text = f"> {display_item}" if selected else f"  {display_item}"
            color = self.GOOD if selected else self.FG
            font = self.small_font if idx < 2 else self.text_font
            line_height = 34 if idx < 2 else 44
            item_rect = None
            wrapped_lines = wrap_text(font, text, screen_w - 160, color) or [text]
            for wrapped in wrapped_lines:
                surf, _ = font.render(wrapped, color)
                rect = surf.get_rect(topleft=(80, y))
                self.screen.blit(surf, rect)
                item_rect = rect if item_rect is None else item_rect.union(rect)
                y += surf.get_height() + 4
            if selected and item_rect is not None:
                draw_focus_frame(self.screen, item_rect, self.GOOD, self.ACCENT)
            y += max(4, line_height - 22)

        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Up/Down choose; Enter select; Esc menu",
            screen_w=screen_w,
            y=get_footer_y(screen_h),
            accent=self.FG,
        )

    def draw_sentence_practice(self):
        screen_w, screen_h = self._screen_size()
        draw_game_title(
            screen=self.screen,
            title_font=self.title_font,
            text="Sentence Practice",
            color=self.ACCENT,
            screen_w=screen_w,
            y=18,
        )
        if not self.sentence_items:
            empty_surf, _ = self.small_font.render("No sentence prompts available.", self.FG)
            self.screen.blit(empty_surf, (60, 120))
            return

        status = f"Sentence {self.sentence_index + 1} of {len(self.sentence_items)}"
        draw_centered_text(
            screen=self.screen,
            font=self.small_font,
            text=status,
            color=self.ACCENT,
            screen_w=screen_w,
            y=76,
        )

        target_label, _ = self.small_font.render("Type now:", self.ACCENT)
        self.screen.blit(target_label, (60, 120))
        current = self.sentence_items[self.sentence_index]
        y = 150
        for line in wrap_text(self.text_font, current, screen_w - 120, self.FG):
            surf, _ = self.text_font.render(line, self.FG)
            self.screen.blit(surf, (60, y))
            y += 36

        typed_label, _ = self.small_font.render("You typed:", self.ACCENT)
        typed_label_y = max(300, y + 12)
        self.screen.blit(typed_label, (60, typed_label_y))
        typed_value = self.sentence_typed if self.sentence_typed else "_"
        typed_color = self.GOOD if current.startswith(self.sentence_typed) else self.DANGER
        y = typed_label_y + 30
        for line in wrap_text(self.text_font, typed_value, screen_w - 120, typed_color) or [typed_value]:
            typed_surf, _ = self.text_font.render(line, typed_color)
            self.screen.blit(typed_surf, (60, y))
            y += typed_surf.get_height() + 4

        for line in wrap_text(self.small_font, self.sentence_feedback, screen_w - 120, self.FG):
            feedback_surf, _ = self.small_font.render(line, self.FG)
            self.screen.blit(feedback_surf, (60, y + 8))
            y += feedback_surf.get_height() + 4

        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Match capitals and punctuation; Ctrl+Space remaining text; Esc back",
            screen_w=screen_w,
            y=get_footer_y(screen_h),
            accent=self.ACCENT,
        )

    def draw(self):
        self.screen.fill(self.BG)
        if self.mode == "MENU":
            self.draw_menu()
        elif self.mode == "PLAYING":
            self.draw_game()
        elif self.mode == "RESULTS":
            self.draw_results_menu()
        elif self.mode == "SENTENCE_PRACTICE":
            self.draw_sentence_practice()
