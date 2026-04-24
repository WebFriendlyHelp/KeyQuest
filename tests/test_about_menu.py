import unittest

from modules import about_menu


class _Speech:
    def __init__(self):
        self.spoken = []

    def say(self, text, **kwargs):
        self.spoken.append((text, kwargs))


class TestAboutMenu(unittest.TestCase):
    def test_build_about_items_includes_current_version_and_actions(self):
        items = about_menu.build_about_items("1.19.0")
        ids = [item["id"] for item in items]

        self.assertEqual(ids[0], "app")
        self.assertIn("website", ids)
        self.assertIn("donate", ids)
        self.assertEqual(ids[-1], "back")
        self.assertIn("KeyQuest 1.19.0", items[0]["display"])

    def test_announcement_names_version_and_keyboard_contract(self):
        announcement = about_menu.get_about_menu_announcement("1.19.0")

        self.assertIn("KeyQuest version 1.19.0", announcement)
        self.assertIn("Use Up and Down", announcement)
        self.assertIn("Press Escape", announcement)

    def test_handle_about_select_opens_website(self):
        speech = _Speech()
        opened = []

        about_menu.handle_about_select(
            {"id": "website"},
            speech=speech,
            return_to_main_menu=lambda: None,
            open_url=lambda url, new=0: opened.append((url, new)),
            donate_url="https://example.test/donate",
        )

        self.assertEqual(opened, [(about_menu.WEBSITE_URL, 2)])
        self.assertIn("Opening webfriendlyhelp dot com.", speech.spoken[0][0])

    def test_handle_about_select_returns_to_main_menu(self):
        speech = _Speech()
        returned = []

        about_menu.handle_about_select(
            {"id": "back"},
            speech=speech,
            return_to_main_menu=lambda: returned.append(True),
            open_url=lambda _url, new=0: None,
            donate_url="https://example.test/donate",
        )

        self.assertEqual(returned, [True])
        self.assertEqual(speech.spoken, [])


if __name__ == "__main__":
    unittest.main()
