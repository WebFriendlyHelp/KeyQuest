"""Letter Fall - Type the active falling letter before it reaches the bottom.

A typing game where one spoken target is active at a time while future letters
remain on screen as lower-emphasis visual pressure. This keeps the game fair
for slower speech rates without removing the arcade feel for sighted players.
"""

from dataclasses import dataclass
import math
import random
import time
from collections import deque

import pygame

from games.base_game import BaseGame
from games import sounds
from modules import audio_manager, phonetics
from ui.a11y import draw_controls_hint
from ui.game_layout import draw_centered_status_lines, draw_game_title
from ui.layout import center_x, get_footer_y


SCREEN_W = 900
SCREEN_H = 600
TARGET_BOTTOM_Y = 520
DANGER_START_Y = 400
BACKGROUND_HOLD_Y = 340

ARCADE_PROFILE = {
    "name": "arcade",
    "spawn_interval": 1.25,
    "active_speed_multiplier": 1.15,
    "queue_speed_multiplier": 0.75,
    "queue_hold_y": 360,
    "announce_interval": 4.5,
    "countdown_from": 3,
}

SPEECH_SAFE_PROFILE = {
    "name": "speech_safe",
    "spawn_interval": 2.65,
    "active_speed_multiplier": 0.52,
    "queue_speed_multiplier": 0.46,
    "queue_hold_y": 300,
    "announce_interval": 4.0,
    "countdown_from": 6,
}

SLOW_SPEECH_PROFILE = {
    "name": "slow_speech",
    "spawn_interval": 3.10,
    "active_speed_multiplier": 0.44,
    "queue_speed_multiplier": 0.38,
    "queue_hold_y": 280,
    "announce_interval": 3.5,
    "countdown_from": 7,
}


@dataclass
class FallingLetter:
    """Track a falling letter and whether it is the active target."""

    letter: str
    x: float
    y: float
    speed: float = 1.0
    is_active: bool = False
    announced_danger: bool = False
    promoted_at: float = 0.0
    last_countdown_second: int = -1


def get_active_target_scale(y_pos):
    """Return the render scale for the active target based on vertical progress."""
    progress = max(0.0, min(1.0, (y_pos - 50.0) / (TARGET_BOTTOM_Y - 50.0)))
    scale = 1.15 + (0.18 * progress)
    if progress >= 0.75:
        danger_progress = (progress - 0.75) / 0.25
        scale += 0.07 * max(0.0, min(1.0, danger_progress))
    return min(1.40, scale)


def get_active_target_outline_width(y_pos):
    """Return the active target outline width."""
    if y_pos >= DANGER_START_Y:
        return 4
    if y_pos >= 250:
        return 3
    return 2


def choose_letter_fall_profile(speech):
    """Choose a pacing profile from the current speech backend and rate."""
    if speech is None:
        return dict(ARCADE_PROFILE)

    if not getattr(speech, "enabled", True):
        return dict(ARCADE_PROFILE)

    backend = (getattr(speech, "backend", "") or "").strip().lower()
    if backend in ("", "none"):
        return dict(ARCADE_PROFILE)

    tts_rate = int(getattr(speech, "tts_rate", 200) or 200)
    if backend == "tts" and tts_rate <= 150:
        return dict(SLOW_SPEECH_PROFILE)

    return dict(SPEECH_SAFE_PROFILE)


class LetterFallGame(BaseGame):
    """Letters fall from the top; only one spoken target is active at a time."""

    NAME = "Letter Fall"
    DESCRIPTION = (
        "Type the active target before it reaches the bottom. Future letters stay on screen "
        "so you can plan ahead while the current target is highlighted."
    )
    INSTRUCTIONS = (
        "Type the highlighted target letter before it reaches the bottom. Only the active "
        "target can hurt you or score points. Press Tab to hear the current target and how "
        "many letters are waiting. Press Control plus Space to hear only the current target. "
        "Press Escape during play to pause and return to the game menu. In the results "
        "dialog, press Escape to close."
    )
    HOTKEYS = """Type the active target: Letter keys
List current target and queue: Tab
Repeat current target: Ctrl+Space
Escape: Pause and return to game menu"""

    def __init__(self, screen, fonts, speech, play_sound_func, show_info_dialog_func, session_complete_callback=None):
        """Initialize the Letter Fall game."""
        super().__init__(
            screen,
            fonts,
            speech,
            play_sound_func,
            show_info_dialog_func,
            session_complete_callback,
        )

        self.running = False
        self.score = 0
        self.high_score = 0
        self.lives = 3
        self.combo = 0
        self.max_combo = 0

        self.fall_speed = 1.0
        self.spawn_interval = 1.5

        self.letters = []
        self.last_spawn = 0

        self.last_hit_time = 0
        self.hit_letter = ""
        self.hit_x = 0
        self.hit_y = 0

        self.last_letter_announcement = 0
        self.announce_interval = 4.0
        self.game_start_time = 0.0
        self.profile = dict(SPEECH_SAFE_PROFILE)
        self.queue_hold_y = BACKGROUND_HOLD_Y
        self.countdown_flash_until = 0.0
        self.recent_letters = deque(maxlen=6)

    def start_playing(self):
        """Initialize/reset game state and begin playing."""
        self.profile = choose_letter_fall_profile(self.speech)
        current_time = time.time()
        self.mode = "PLAYING"
        self.running = True
        self.score = 0
        self.lives = 3
        self.combo = 0
        self.max_combo = 0
        self.fall_speed = 1.0
        self.spawn_interval = self.profile["spawn_interval"]
        self.letters = []
        self.last_spawn = current_time
        self.last_hit_time = 0
        self.last_letter_announcement = 0
        self.announce_interval = self.profile["announce_interval"]
        self.queue_hold_y = self.profile["queue_hold_y"]
        self.countdown_flash_until = 0.0
        self.recent_letters.clear()
        self.game_start_time = current_time
        self.play_sound(sounds.level_start())
        self.spawn_letter()

    def handle_game_input(self, event, mods):
        """Handle input during gameplay."""
        if event.key == pygame.K_ESCAPE:
            elapsed_minutes = max(0.01, (time.time() - self.game_start_time) / 60.0)
            if self.on_session_complete:
                self.on_session_complete(
                    self,
                    {
                        "score": self.score,
                        "accuracy": min(100.0, 65.0 + min(30, self.max_combo * 2)),
                        "session_duration_minutes": elapsed_minutes,
                        "pet_xp": max(10, int(self.score / 20)),
                        "ended_early": True,
                        "exit_reason": "escape",
                    },
                )
            self.running = False
            self.mode = "MENU"
            self.speech.say(
                f"Game paused. Final score: {self.score}. Returning to menu.",
                priority=True
            )
            self.say_game_menu()
            return None

        if event.key == pygame.K_SPACE and (mods & pygame.KMOD_CTRL):
            self.announce_current_target()
            return None

        if event.key == pygame.K_TAB:
            self.announce_current_letters()
            return None

        char = event.unicode.lower()
        if char.isalpha() and len(char) == 1:
            self.try_hit_letter(char)

        return None

    def _current_target(self):
        """Return the active target, if one exists."""
        for item in self.letters:
            if item.is_active:
                return item
        return None

    def _queue_letters(self):
        """Return queued future letters in promotion order."""
        return [item for item in self.letters if not item.is_active]

    def _choose_next_letter(self):
        """Choose a letter while avoiding immediate repetition."""
        alphabet = list("abcdefghijklmnopqrstuvwxyz")
        blocked_letters = {item.letter for item in self.letters}
        blocked_letters.update(self.recent_letters)

        available_letters = [letter for letter in alphabet if letter not in blocked_letters]
        if not available_letters:
            available_letters = [letter for letter in alphabet if letter not in {item.letter for item in self.letters}]
        if not available_letters:
            available_letters = alphabet

        letter = random.choice(available_letters)
        self.recent_letters.append(letter)
        return letter

    def _spoken_letter(self, letter):
        """Return a speech-friendly name for the target letter."""
        hint = phonetics.phonetic_hint_for_key(letter)
        return hint if hint else str(letter).upper()

    def _announce_active_target(self, item, priority=False):
        """Speak the newly promoted target."""
        if item is None:
            return
        item.last_countdown_second = -1
        self.speech.say(f"Target {self._spoken_letter(item.letter)}", priority=priority)
        self.last_letter_announcement = time.time()

    def _promote_next_target(self, priority=False):
        """Promote the next queued letter to be the active target."""
        next_target = None
        for item in self.letters:
            if not item.is_active:
                next_target = item
                break

        if next_target is None:
            return None

        next_target.is_active = True
        next_target.announced_danger = False
        next_target.promoted_at = time.time()
        self._announce_active_target(next_target, priority=priority)
        return next_target

    def _handle_speed_up(self):
        """Increase difficulty at score milestones."""
        if self.score > 0 and self.score % 50 == 0:
            self.fall_speed += 0.2
            minimum_spawn_interval = 0.75 if self.profile["name"] == "arcade" else 1.05
            self.spawn_interval = max(minimum_spawn_interval, self.spawn_interval - 0.08)
            self.speech.say("Speed up!", priority=False)
            self.play_sound(sounds.speed_up())

    def _active_target_remaining_seconds(self, item):
        """Estimate how long the active target has before reaching the bottom."""
        if item is None:
            return 0.0

        pixels_remaining = max(0.0, TARGET_BOTTOM_Y - item.y)
        pixels_per_second = item.speed * self.fall_speed * 120 * self.profile["active_speed_multiplier"]
        if pixels_per_second <= 0:
            return 0.0
        return pixels_remaining / pixels_per_second

    def _play_active_target_countdown_cue(self, item):
        """Play a once-per-second descending cue as the active target runs out of time."""
        if item is None:
            return

        countdown_from = int(self.profile.get("countdown_from", 0))
        if countdown_from <= 0:
            return

        remaining_seconds = self._active_target_remaining_seconds(item)
        countdown_step = int(math.ceil(remaining_seconds))
        if countdown_step <= 0 or countdown_step > countdown_from:
            return

        if countdown_step == item.last_countdown_second:
            return

        item.last_countdown_second = countdown_step
        self.countdown_flash_until = time.time() + 0.2
        remaining_ratio = max(0.0, min(1.0, countdown_step / float(countdown_from)))
        self.play_sound(audio_manager.AudioManager.make_progressive_tone(remaining_ratio))
        self.speech.say(self._spoken_letter(item.letter), priority=False)

    def try_hit_letter(self, char):
        """Try to hit the active target letter."""
        active_target = self._current_target()
        if active_target is None:
            self.combo = 0
            self.play_sound(audio_manager.AudioManager.make_miss_sound())
            return False

        if active_target.letter != char:
            self.combo = 0
            self.play_sound(audio_manager.AudioManager.make_miss_sound())
            return False

        self.letters.remove(active_target)
        bonus = 5 if active_target.y >= DANGER_START_Y else 0
        self.score += 10 + bonus
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        if self.score > self.high_score:
            self.high_score = self.score

        self.last_hit_time = time.time()
        self.hit_letter = char.upper()
        self.hit_x = active_target.x
        self.hit_y = active_target.y

        self.play_sound(audio_manager.AudioManager.make_coin_sound())

        if bonus:
            self.speech.say("Clutch save!", priority=False)
        if self.combo in (3, 5, 10):
            self.play_sound(audio_manager.AudioManager.make_success_tones())

        if self.combo == 3:
            self.speech.say("Combo 3!", priority=False)
        elif self.combo == 5:
            self.speech.say("Combo 5! On fire!", priority=False)
        elif self.combo == 10:
            self.speech.say("Amazing! Combo 10!", priority=False)

        self._handle_speed_up()
        self._promote_next_target(priority=False)
        return True

    def _handle_target_missed(self, target):
        """Process the active target reaching the bottom."""
        if target in self.letters:
            self.letters.remove(target)
        self.lives -= 1
        self.combo = 0
        self.play_sound(sounds.life_lost())

        if self.lives > 0:
            self.speech.say(
                f"Missed {self._spoken_letter(target.letter)}! {self.lives} lives left.",
                priority=True,
            )
            self._promote_next_target(priority=True)
            return

        self.running = False
        self.mode = "MENU"
        self.play_sound(sounds.game_over())

        results = f"""GAME OVER

Final Score: {self.score}
High Score: {self.high_score}
Max Combo: {self.max_combo}

{self._get_performance_message()}
"""
        elapsed_minutes = max(0.01, (time.time() - self.game_start_time) / 60.0)
        self.show_game_results(
            results,
            session_stats={
                "score": self.score,
                "accuracy": min(100.0, 65.0 + min(30, self.max_combo * 2)),
                "session_duration_minutes": elapsed_minutes,
                "pet_xp": max(10, int(self.score / 20)),
            },
        )
        self.say_game_menu()

    def update(self, dt):
        """Update the game state."""
        if self.mode != "PLAYING" or not self.running:
            return

        current_time = time.time()

        if current_time - self.last_spawn > self.spawn_interval:
            self.spawn_letter()
            self.last_spawn = current_time

        active_target = self._current_target()
        if active_target is None:
            active_target = self._promote_next_target(priority=True)

        for item in self.letters:
            if item.is_active:
                item.y += item.speed * self.fall_speed * 120 * self.profile["active_speed_multiplier"] * dt
            else:
                item.y += item.speed * self.fall_speed * 70 * self.profile["queue_speed_multiplier"] * dt
                if item.y > self.queue_hold_y:
                    item.y = self.queue_hold_y

        active_target = self._current_target()
        if active_target is not None:
            self._play_active_target_countdown_cue(active_target)

            if active_target.y >= DANGER_START_Y and not active_target.announced_danger:
                active_target.announced_danger = True

            if active_target.y >= TARGET_BOTTOM_Y:
                self._handle_target_missed(active_target)
                return

        if self.letters and current_time - self.last_letter_announcement > self.announce_interval:
            self.announce_current_letters()
            self.last_letter_announcement = current_time

    def spawn_letter(self):
        """Spawn a new falling letter."""
        letter = self._choose_next_letter()
        x = random.randint(50, 750)
        item = FallingLetter(letter=letter, x=x, y=50.0)

        if self._current_target() is None:
            item.is_active = True
            item.promoted_at = time.time()

        self.letters.append(item)

        if item.is_active:
            self._announce_active_target(item, priority=False)

    def announce_score(self):
        """Announce current score and stats."""
        active_target = self._current_target()
        if active_target is None:
            msg = f"No current target. Score: {self.score}. Lives: {self.lives}. Combo: {self.combo}."
        else:
            msg = (
                f"Target: {self._spoken_letter(active_target.letter)}. Score: {self.score}. "
                f"Lives: {self.lives}. Combo: {self.combo}."
            )
        self.speech.say(msg, priority=True)

    def announce_current_target(self):
        """Announce only the current target letter."""
        active_target = self._current_target()
        if active_target is None:
            self.speech.say("No current target.", priority=True)
            return
        self.speech.say(self._spoken_letter(active_target.letter), priority=True)

    def announce_current_letters(self):
        """Announce the active target and current queue."""
        active_target = self._current_target()
        queued = self._queue_letters()

        if active_target is None and not queued:
            self.speech.say("No letters falling.", priority=True)
            return

        if active_target is None:
            waiting = len(queued)
            msg = "No active target." if waiting == 0 else f"No active target. {waiting} waiting."
            self.speech.say(msg, priority=True)
            return

        if not queued:
            msg = self._spoken_letter(active_target.letter)
        else:
            msg = f"{self._spoken_letter(active_target.letter)}. {len(queued)} waiting."

        self.speech.say(msg, priority=True)

    def _get_performance_message(self):
        """Get an encouraging message based on performance."""
        if self.score >= 500:
            return "Outstanding performance!"
        if self.score >= 300:
            return "Great job!"
        if self.score >= 150:
            return "Good work!"
        if self.score >= 50:
            return "Nice try! Keep practicing."
        return "Keep practicing to improve!"

    def _draw_active_target(self, item):
        """Draw the active target with size, halo, and outline cues."""
        scale = get_active_target_scale(item.y)
        outline_width = get_active_target_outline_width(item.y)
        in_danger = item.y >= DANGER_START_Y
        is_countdown_flash = time.time() < self.countdown_flash_until

        base_color = self.DANGER if in_danger else self.FG
        if is_countdown_flash:
            base_color = self.FG

        outline_color = self.ACCENT if not in_danger else self.FG
        halo_color = self.ACCENT if not in_danger else self.DANGER
        if is_countdown_flash:
            outline_color = self.FG
            halo_color = self.ACCENT
            outline_width += 2

        letter_surface, _ = self.text_font.render(item.letter.upper(), base_color)
        scaled_size = (
            max(1, int(letter_surface.get_width() * scale)),
            max(1, int(letter_surface.get_height() * scale)),
        )
        letter_surface = pygame.transform.smoothscale(letter_surface, scaled_size)
        rect = letter_surface.get_rect(center=(int(item.x), int(item.y)))

        halo_rect = rect.inflate(28, 18)
        halo_surface = pygame.Surface(halo_rect.size, pygame.SRCALPHA)
        halo_alpha = 60 if not in_danger else 90
        if is_countdown_flash:
            halo_alpha = 140
        pygame.draw.ellipse(halo_surface, (*halo_color, halo_alpha), halo_surface.get_rect())
        self.screen.blit(halo_surface, halo_rect.topleft)

        pygame.draw.ellipse(self.screen, outline_color, halo_rect, outline_width)
        self.screen.blit(letter_surface, rect)

    def _draw_queued_letter(self, item):
        """Draw a queued non-active letter with lower emphasis."""
        letter_surface, _ = self.small_font.render(item.letter.upper(), (190, 190, 190))
        rect = letter_surface.get_rect(center=(int(item.x), int(item.y)))
        self.screen.blit(letter_surface, rect)

    def draw_game(self):
        """Draw the active game screen."""
        screen_w, screen_h = self._screen_size()
        draw_game_title(
            screen=self.screen,
            title_font=self.title_font,
            text=self.NAME,
            color=self.ACCENT,
            screen_w=screen_w,
            y=10,
        )
        draw_centered_status_lines(
            screen=self.screen,
            font=self.small_font,
            entries=[("Type now: Active target", self.ACCENT)],
            screen_w=screen_w,
            start_y=40,
        )

        active_target = self._current_target()
        for item in self.letters:
            if item.is_active:
                self._draw_active_target(item)
            else:
                self._draw_queued_letter(item)

        if time.time() - self.last_hit_time < 0.3:
            hit_surf, _ = self.text_font.render(self.hit_letter, self.GOOD)
            self.screen.blit(hit_surf, (int(self.hit_x), int(self.hit_y)))

        status_lines = [
            f"Queued: {len(self._queue_letters())}",
            f"Score: {self.score}  Lives: {self.lives}  Combo: {self.combo}",
        ]
        if active_target is not None:
            status_lines.append(f"Target: {active_target.letter.upper()}")
        if self.high_score > 0:
            status_lines.append(f"High Score: {self.high_score}")

        draw_centered_status_lines(
            screen=self.screen,
            font=self.small_font,
            entries=[
                (line, self.ACCENT if not line.startswith("Target:") else self.FG)
                for line in status_lines
            ],
            screen_w=screen_w,
            start_y=screen_h - 90,
        )

        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Type target; Tab status; Ctrl+Space repeat target; Esc quit",
            screen_w=screen_w,
            y=get_footer_y(screen_h),
            accent=self.FG,
        )

        danger_y = min(TARGET_BOTTOM_Y, screen_h - 120)
        pygame.draw.line(self.screen, self.DANGER, (0, danger_y), (screen_w, danger_y), 2)
        if active_target is not None and active_target.y > DANGER_START_Y:
            warn_text = "ACTIVE TARGET IN DANGER"
            warn_surf, _ = self.small_font.render(warn_text, self.DANGER)
            self.screen.blit(warn_surf, (center_x(screen_w, warn_surf.get_width()), max(80, screen_h - 150)))
