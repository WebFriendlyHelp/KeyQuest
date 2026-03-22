import unittest
from unittest import mock

from games.letter_fall import (
    BACKGROUND_HOLD_Y,
    DANGER_START_Y,
    ARCADE_PROFILE,
    FallingLetter,
    LetterFallGame,
    SLOW_SPEECH_PROFILE,
    SPEECH_SAFE_PROFILE,
    choose_letter_fall_profile,
    get_active_target_outline_width,
    get_active_target_scale,
)


class _DummySpeech:
    def __init__(self):
        self.messages = []

    def say(self, text, priority=False, protect_seconds=0.0):
        self.messages.append(text)


class TestLetterFallGame(unittest.TestCase):
    def _build_game(self):
        game = LetterFallGame(
            screen=None,
            fonts={"title_font": None, "text_font": None, "small_font": None},
            speech=_DummySpeech(),
            play_sound_func=lambda sound, *_args, **_kwargs: game.played_sounds.append(sound),
            show_info_dialog_func=lambda *_args, **_kwargs: None,
        )
        game.played_sounds = []
        return game

    def test_spawn_first_letter_becomes_active_and_is_announced(self):
        game = self._build_game()

        with mock.patch("games.letter_fall.random.choice", return_value="a"), mock.patch(
            "games.letter_fall.random.randint", return_value=120
        ), mock.patch("games.letter_fall.time.time", return_value=10.0):
            game.spawn_letter()

        self.assertEqual(len(game.letters), 1)
        self.assertTrue(game.letters[0].is_active)
        self.assertEqual(game.speech.messages[-1], "Target A, like alpha")

    def test_hitting_active_target_promotes_next_queued_letter(self):
        game = self._build_game()
        game.letters = [
            FallingLetter("a", 100, 120, is_active=True),
            FallingLetter("b", 150, 180),
        ]

        with mock.patch("games.letter_fall.time.time", return_value=25.0):
            result = game.try_hit_letter("a")

        self.assertTrue(result)
        self.assertEqual(game.score, 10)
        self.assertEqual(game.combo, 1)
        self.assertEqual(len(game.letters), 1)
        self.assertEqual(game.letters[0].letter, "b")
        self.assertTrue(game.letters[0].is_active)
        self.assertEqual(game.speech.messages[-1], "Target B, like bravo")

    def test_wrong_letter_does_not_clear_background_match(self):
        game = self._build_game()
        game.letters = [
            FallingLetter("a", 100, 120, is_active=True),
            FallingLetter("b", 150, 180),
        ]
        game.combo = 4

        with mock.patch("games.letter_fall.audio_manager.AudioManager.make_miss_sound", return_value="lesson-bad"):
            result = game.try_hit_letter("b")

        self.assertFalse(result)
        self.assertEqual(game.combo, 0)
        self.assertEqual([item.letter for item in game.letters], ["a", "b"])
        self.assertTrue(game.letters[0].is_active)
        self.assertEqual(game.played_sounds[-1], "lesson-bad")

    def test_background_letters_stop_at_queue_hold_line(self):
        game = self._build_game()
        game.mode = "PLAYING"
        game.running = True
        game.last_spawn = 999.0
        game.letters = [
            FallingLetter("a", 100, 100, is_active=True),
            FallingLetter("b", 150, BACKGROUND_HOLD_Y - 2),
        ]

        with mock.patch("games.letter_fall.time.time", return_value=1000.0):
            game.update(1.0)

        self.assertGreater(game.letters[0].y, 100)
        self.assertEqual(game.letters[1].y, BACKGROUND_HOLD_Y)

    def test_missing_active_target_costs_life_and_promotes_next_letter(self):
        game = self._build_game()
        game.mode = "PLAYING"
        game.running = True
        game.lives = 3
        game.last_spawn = 999.0
        game.letters = [
            FallingLetter("a", 100, 519, is_active=True),
            FallingLetter("b", 140, 220),
        ]

        with mock.patch("games.letter_fall.time.time", return_value=1000.0):
            game.update(0.02)

        self.assertEqual(game.lives, 2)
        self.assertEqual(len(game.letters), 1)
        self.assertEqual(game.letters[0].letter, "b")
        self.assertTrue(game.letters[0].is_active)
        self.assertIn("Missed A, like alpha! 2 lives left.", game.speech.messages)
        self.assertEqual(game.speech.messages[-1], "Target B, like bravo")

    def test_tab_announcement_reports_target_and_queue(self):
        game = self._build_game()
        game.letters = [
            FallingLetter("a", 100, 120, is_active=True),
            FallingLetter("b", 150, 180),
            FallingLetter("c", 180, 200),
        ]

        game.announce_current_letters()

        self.assertEqual(
            game.speech.messages[-1],
            "A, like alpha. 2 waiting.",
        )

    def test_ctrl_space_announcement_includes_current_target_letter(self):
        game = self._build_game()
        game.letters = [FallingLetter("j", 100, 140, is_active=True)]

        game.announce_current_target()

        self.assertEqual(
            game.speech.messages[-1],
            "J, like juliet",
        )

    def test_clutch_save_bonus_applies_in_danger_zone(self):
        game = self._build_game()
        game.letters = [FallingLetter("a", 100, DANGER_START_Y + 5, is_active=True)]

        with mock.patch("games.letter_fall.audio_manager.AudioManager.make_coin_sound", return_value="lesson-good"):
            result = game.try_hit_letter("a")

        self.assertTrue(result)
        self.assertEqual(game.score, 15)
        self.assertIn("Clutch save!", game.speech.messages)
        self.assertEqual(game.played_sounds[-1], "lesson-good")

    def test_correct_letter_keeps_lesson_tone_even_with_combo(self):
        game = self._build_game()
        game.combo = 1
        game.letters = [FallingLetter("a", 100, 120, is_active=True)]

        with mock.patch("games.letter_fall.audio_manager.AudioManager.make_coin_sound", return_value="lesson-good"):
            result = game.try_hit_letter("a")

        self.assertTrue(result)
        self.assertEqual(game.played_sounds[-1], "lesson-good")

    def test_combo_milestone_adds_item_complete_sound(self):
        game = self._build_game()
        game.combo = 2
        game.letters = [FallingLetter("a", 100, 120, is_active=True)]

        with mock.patch("games.letter_fall.audio_manager.AudioManager.make_coin_sound", return_value="lesson-good"), mock.patch(
            "games.letter_fall.audio_manager.AudioManager.make_success_tones", return_value="item-complete"
        ):
            result = game.try_hit_letter("a")

        self.assertTrue(result)
        self.assertEqual(game.played_sounds[-2:], ["lesson-good", "item-complete"])

    def test_choose_next_letter_avoids_recent_and_current_letters_when_possible(self):
        game = self._build_game()
        game.letters = [
            FallingLetter("a", 100, 120, is_active=True),
            FallingLetter("b", 150, 180),
        ]
        game.recent_letters.extend(["c", "d", "e"])

        with mock.patch("games.letter_fall.random.choice", side_effect=lambda seq: seq[0]):
            chosen = game._choose_next_letter()

        self.assertNotIn(chosen, {"a", "b", "c", "d", "e"})
        self.assertEqual(game.recent_letters[-1], chosen)

    def test_escape_records_partial_session_before_returning_to_menu(self):
        game = self._build_game()
        recorded = []
        game.on_session_complete = lambda current_game, stats: recorded.append((current_game, stats))
        game.mode = "PLAYING"
        game.running = True
        game.score = 45
        game.max_combo = 3
        game.game_start_time = 100.0
        event = type("Event", (), {"key": 27, "unicode": ""})()

        with mock.patch("games.letter_fall.time.time", return_value=130.0):
            game.handle_game_input(event, 0)

        self.assertFalse(game.running)
        self.assertEqual(game.mode, "MENU")
        self.assertEqual(len(recorded), 1)
        self.assertIs(recorded[0][0], game)
        self.assertEqual(recorded[0][1]["score"], 45)
        self.assertGreater(recorded[0][1]["session_duration_minutes"], 0)


class TestLetterFallVisualHelpers(unittest.TestCase):
    def test_active_target_scale_grows_with_progress(self):
        self.assertLess(get_active_target_scale(60), get_active_target_scale(300))
        self.assertLess(get_active_target_scale(300), get_active_target_scale(500))
        self.assertLessEqual(get_active_target_scale(500), 1.4)

    def test_active_target_outline_width_steps_up_near_danger(self):
        self.assertEqual(get_active_target_outline_width(100), 2)
        self.assertEqual(get_active_target_outline_width(300), 3)
        self.assertEqual(get_active_target_outline_width(450), 4)


class TestLetterFallProfiles(unittest.TestCase):
    def test_choose_arcade_profile_when_speech_is_off(self):
        speech = type("Speech", (), {"enabled": False, "backend": "tts", "tts_rate": 200})()

        profile = choose_letter_fall_profile(speech)

        self.assertEqual(profile["name"], ARCADE_PROFILE["name"])

    def test_choose_arcade_profile_when_no_backend_is_active(self):
        speech = type("Speech", (), {"enabled": True, "backend": "none", "tts_rate": 200})()

        profile = choose_letter_fall_profile(speech)

        self.assertEqual(profile["name"], ARCADE_PROFILE["name"])

    def test_choose_speech_safe_profile_for_screen_reader_or_normal_tts(self):
        tts_speech = type("Speech", (), {"enabled": True, "backend": "tts", "tts_rate": 200})()
        reader_speech = type("Speech", (), {"enabled": True, "backend": "tolk", "tts_rate": 200})()

        self.assertEqual(choose_letter_fall_profile(tts_speech)["name"], SPEECH_SAFE_PROFILE["name"])
        self.assertEqual(choose_letter_fall_profile(reader_speech)["name"], SPEECH_SAFE_PROFILE["name"])

    def test_choose_slow_speech_profile_for_slower_tts_rates(self):
        speech = type("Speech", (), {"enabled": True, "backend": "tts", "tts_rate": 100})()

        profile = choose_letter_fall_profile(speech)

        self.assertEqual(profile["name"], SLOW_SPEECH_PROFILE["name"])

    def test_start_playing_applies_selected_profile_values(self):
        played_sounds = []
        game = LetterFallGame(
            screen=None,
            fonts={"title_font": None, "text_font": None, "small_font": None},
            speech=type(
                "Speech",
                (),
                {
                    "enabled": True,
                    "backend": "tts",
                    "tts_rate": 100,
                    "messages": [],
                    "say": lambda self, text, **_kwargs: self.messages.append(text),
                },
            )(),
            play_sound_func=lambda sound, *_args, **_kwargs: played_sounds.append(sound),
            show_info_dialog_func=lambda *_args, **_kwargs: None,
        )

        with mock.patch("games.letter_fall.time.time", return_value=50.0), mock.patch(
            "games.letter_fall.random.choice", return_value="q"
        ), mock.patch("games.letter_fall.random.randint", return_value=200):
            game.start_playing()

        self.assertEqual(game.profile["name"], SLOW_SPEECH_PROFILE["name"])
        self.assertEqual(game.spawn_interval, SLOW_SPEECH_PROFILE["spawn_interval"])
        self.assertEqual(game.announce_interval, SLOW_SPEECH_PROFILE["announce_interval"])
        self.assertEqual(game.queue_hold_y, SLOW_SPEECH_PROFILE["queue_hold_y"])
        self.assertEqual(len(game.letters), 1)
        self.assertEqual(game.letters[0].letter, "q")
        self.assertEqual(game.speech.messages, ["Target Q"])
        self.assertTrue(played_sounds)

    def test_countdown_cue_plays_once_per_second_bucket(self):
        played_sounds = []
        game = LetterFallGame(
            screen=None,
            fonts={"title_font": None, "text_font": None, "small_font": None},
            speech=_DummySpeech(),
            play_sound_func=lambda sound, *_args, **_kwargs: played_sounds.append(sound),
            show_info_dialog_func=lambda *_args, **_kwargs: None,
        )
        game.mode = "PLAYING"
        game.running = True
        game.profile = dict(SPEECH_SAFE_PROFILE)
        game.fall_speed = 1.0
        target = FallingLetter("a", 100, 100, is_active=True)
        game.letters = [target]

        with mock.patch.object(
            game,
            "_active_target_remaining_seconds",
            side_effect=[6.0, 6.0, 5.0],
        ), mock.patch(
            "games.letter_fall.audio_manager.AudioManager.make_progressive_tone",
            side_effect=lambda pct: f"tone-{pct:.2f}",
        ):
            game._play_active_target_countdown_cue(target)
            game._play_active_target_countdown_cue(target)
            game._play_active_target_countdown_cue(target)

        self.assertEqual(played_sounds, ["tone-1.00", "tone-0.83"])
        self.assertEqual(game.speech.messages, ["A, like alpha", "A, like alpha"])


if __name__ == "__main__":
    unittest.main()
