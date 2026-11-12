"""Hangman's own Escape branch queues the menu behind "Returning to game menu."

Release review low 4 (2026-11-11): games/hangman.py said "Returning to game
menu." and then announced the game menu with interrupt on, which cuts the
first line off: the pattern already fixed in Letter Fall and Word Typing. The
app's triple-Escape guard consumes Escape before a playing game sees it, so
this branch is not reached in play today; it is made to queue anyway, so it
is right if the guard ever lets an Escape through.

Drives HangmanGame.handle_game_input directly with stub speech. Proves the
interrupt flags passed to Speech.say, not what a screen reader voices.
"""

import unittest

import pygame

from games.hangman import HangmanGame


class _Speech:
    def __init__(self):
        self.spoken = []

    def say(self, text, **kwargs):
        self.spoken.append((text, kwargs))


def _game(speech):
    game = HangmanGame(
        screen=None,
        fonts={"title_font": None, "text_font": None, "small_font": None},
        speech=speech,
        play_sound_func=lambda *_a, **_k: None,
        show_info_dialog_func=lambda *_a, **_k: None,
    )
    game.mode = "PLAYING"
    game.running = True
    game.game_start_time = 0.0
    return game


class TestHangmanEscapeQueuesMenu(unittest.TestCase):
    def test_menu_is_queued_after_the_returning_line(self):
        speech = _Speech()
        game = _game(speech)
        game.handle_game_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), 0)

        texts = [t for t, _ in speech.spoken]
        self.assertEqual(texts[0], "Returning to game menu.")
        menu = [(t, k) for t, k in speech.spoken if t.startswith(f"{game.NAME} menu.")]
        self.assertEqual(len(menu), 1)
        self.assertIs(menu[0][1].get("interrupt"), False, "the menu must not cut off the line before it")
        self.assertEqual(game.mode, "MENU")

    def test_menu_from_elsewhere_still_interrupts(self):
        # Twin: say_game_menu's default is unchanged for callers that want it.
        speech = _Speech()
        game = _game(speech)
        game.say_game_menu()
        self.assertTrue(speech.spoken[-1][1].get("interrupt"))


if __name__ == "__main__":
    unittest.main()
