"""About menu data and actions."""

WEBSITE_URL = "https://webfriendlyhelp.com"


def build_about_items(version: str) -> list[dict[str, str]]:
    """Return the About menu items for the current app version."""
    return [
        {
            "id": "app",
            "display": f"Application: KeyQuest {version}",
            "speak": f"Application: KeyQuest version {version}.",
        },
        {
            "id": "release_date",
            "display": "Release Date: 2026-02-19",
            "speak": "Release date: February 19, 2026.",
        },
        {
            "id": "name",
            "display": "Name: Casey Mathews",
            "speak": "Name: Casey Mathews.",
        },
        {
            "id": "company",
            "display": "Company: Web Friendly Help LLC",
            "speak": "Company: Web Friendly Help L L C.",
        },
        {
            "id": "tagline",
            "display": "Tagline: Helping You Tame Your Access Technology",
            "speak": "Tagline: Helping You Tame Your Access Technology.",
        },
        {
            "id": "copyright",
            "display": "Copyright: (c) 2026 Casey Mathews and Web Friendly Help LLC",
            "speak": "Copyright 2026 Casey Mathews and Web Friendly Help L L C.",
        },
        {
            "id": "license",
            "display": "License: MIT (free to use, modify, and distribute)",
            "speak": "License: M I T. Free to use, modify, and distribute.",
        },
        {
            "id": "website",
            "display": "Website: webfriendlyhelp.com",
            "speak": "Website: webfriendlyhelp.com. Press Enter to open in your browser.",
        },
        {
            "id": "official_downloads",
            "display": "Official Downloads: GitHub Releases only",
            "speak": (
                "Official downloads: GitHub Releases only. "
                "The updater uses those releases. Other builds are not official."
            ),
        },
        {
            "id": "donate",
            "display": "Donate: Support KeyQuest",
            "speak": "Donate: Support KeyQuest. Press Enter to open the donation page in your browser.",
        },
        {
            "id": "credits",
            "display": "Credits: Built with Python and Pygame",
            "speak": "Credits: Built with Python and Pygame.",
        },
        {
            "id": "back",
            "display": "Back to Main Menu",
            "speak": "Back to Main Menu.",
        },
    ]


def get_about_menu_announcement(version: str) -> str:
    """Return the opening About menu announcement."""
    return (
        f"About menu. KeyQuest version {version}. Name: Casey Mathews. "
        "Company: Web Friendly Help L L C. Use Up and Down to choose. "
        "Press Enter or Space to select. Press Escape to return to main menu."
    )


def handle_about_select(
    item: dict[str, str],
    *,
    speech,
    return_to_main_menu,
    open_url,
    donate_url: str,
) -> None:
    """Handle a selected About menu item."""
    item_id = item.get("id", "")
    if item_id == "website":
        speech.say("Opening webfriendlyhelp dot com.", priority=True)
        try:
            open_url(WEBSITE_URL, new=2)
        except Exception:
            speech.say("Unable to open website.", priority=True)
        return
    if item_id == "donate":
        speech.say("Opening the KeyQuest donation page.", priority=True)
        try:
            open_url(donate_url, new=2)
        except Exception:
            speech.say("Unable to open donation page.", priority=True)
        return
    if item_id == "back":
        return_to_main_menu()
        return
    speech.say(item.get("speak", item.get("display", "")), priority=True)
