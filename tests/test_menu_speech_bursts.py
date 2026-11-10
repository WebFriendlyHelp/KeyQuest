"""Opening Pets, Shop categories and lesson intros: the main line is heard.

Fable review 2026-11-10, modules finding 5. Several screens spoke their main
announcement and then, in the same call, a second line with the default
interrupt=True, which cancelled the first. Opening Pets left only the first
menu option; a lesson intro lost its heading and key instructions; a shop
category lost "Press Enter to purchase"; "Purchased" was cut by the balance.

Uses tests/speech_burst.py (real Speech.say drop logic, muted). It models
cancellation by a following interrupting line; it cannot tell what NVDA says.
"""

import types
import unittest
from unittest import mock

from modules import lesson_intro_mode, pet_manager, pet_mode, shop_manager, shop_mode, state_manager
from modules.state_manager import Settings
from tests.speech_burst import heard_text, lines_reaching_backend, make_speech


def _plain_app():
    app = types.SimpleNamespace()
    app.state = state_manager.AppState()
    app.state.settings = Settings()
    app.speech = make_speech()
    app.audio = mock.MagicMock()
    app.save_progress = mock.Mock()
    return app


class TestPetScreens(unittest.TestCase):
    def test_opening_pets_with_a_pet_keeps_its_status(self):
        app = _plain_app()
        pet_manager.choose_pet(app.state.settings, list(pet_manager.PET_TYPES)[0])
        pet_mode.show_pet(app)
        text = heard_text(app.speech)
        self.assertIn("Your Pet:", text, lines_reaching_backend(app.speech))
        self.assertIn("Happiness", text)

    def test_opening_pets_without_a_pet_keeps_the_invitation(self):
        app = _plain_app()
        pet_mode.show_pet(app)
        text = heard_text(app.speech)
        self.assertIn("You don't have a pet yet", text, lines_reaching_backend(app.speech))
        first = pet_manager.get_pet_info(list(pet_manager.PET_TYPES)[0])["name"]
        self.assertIn(first, text, "the first pet type is still announced")

    def test_browsing_pet_types_still_interrupts(self):
        """Negative twin: arrowing must still cut the previous item."""
        app = _plain_app()
        pet_mode.show_pet(app)
        before = len(lines_reaching_backend(app.speech))
        import pygame

        pet_mode.handle_pet_input(app, types.SimpleNamespace(key=pygame.K_DOWN), 0)
        lines = lines_reaching_backend(app.speech)[before:]
        self.assertTrue(lines and lines[-1]["interrupt"], lines)


class TestShopScreens(unittest.TestCase):
    def test_entering_a_category_keeps_its_instructions(self):
        import pygame

        app = _plain_app()
        shop_mode.show_shop(app)
        before = len(lines_reaching_backend(app.speech))
        shop_mode.handle_shop_input(app, types.SimpleNamespace(key=pygame.K_RETURN), 0)
        entries = lines_reaching_backend(app.speech)[before:]
        survivors = [e["text"] for i, e in enumerate(entries)
                     if not (i + 1 < len(entries) and entries[i + 1]["interrupt"])]
        self.assertTrue(any("Press Enter to purchase" in t for t in survivors), entries)

    def test_a_purchase_is_heard_before_the_balance(self):
        app = _plain_app()
        with mock.patch.object(shop_manager, "can_purchase", return_value=(True, "")), \
                mock.patch.object(shop_manager, "purchase_item", return_value=(True, "Purchased Hat.")):
            shop_mode.purchase_shop_item(app, "hat")
        text = heard_text(app.speech)
        self.assertIn("Purchased Hat", text, lines_reaching_backend(app.speech))
        self.assertIn("Remaining balance", text)


class TestLessonIntro(unittest.TestCase):
    def test_the_heading_survives_the_first_item(self):
        app = _plain_app()
        lesson_intro_mode.show_lesson_intro(app, 1)
        text = heard_text(app.speech)
        self.assertIn("Lesson 1,", text, lines_reaching_backend(app.speech))
        self.assertIn("Control Space repeats", text)
        first_item = app.state.lesson_intro.intro_items[0][1]
        self.assertIn(first_item, text, "the first intro item is still read")


if __name__ == "__main__":
    unittest.main()
