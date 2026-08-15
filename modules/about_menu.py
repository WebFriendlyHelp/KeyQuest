"""About menu data and actions."""

from modules.version import __release_date__

WEBSITE_URL = "https://webfriendlyhelp.com"

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def speak_release_date(iso_date: str) -> str:
    """Turn 2026-08-15 into "August 15, 2026" for speech.

    Month names are spelled out here rather than through ``strftime``, which
    would follow the machine's locale and could hand a screen reader a month
    name in a language the rest of the app is not speaking.
    """
    try:
        year, month, day = (int(part) for part in iso_date.split("-"))
        return f"Release date: {_MONTHS[month - 1]} {day}, {year}."
    except (ValueError, IndexError):
        return f"Release date: {iso_date}."


def build_about_items(version: str, release_date: str = __release_date__) -> list[dict[str, str]]:
    """Return the About menu items for the current app version."""
    return [
        {
            "id": "app",
            "display": f"Application: KeyQuest {version}",
            "speak": f"Application: KeyQuest version {version}.",
        },
        {
            "id": "release_date",
            "display": f"Release Date: {release_date}",
            "speak": speak_release_date(release_date),
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
            "id": "report_problem",
            "display": "Report a Problem: save a diagnostics file to send",
            "speak": (
                "Report a Problem. Press Enter to save a diagnostics file to your "
                "Downloads folder, so you can attach it to an email."
            ),
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
    save_diagnostics=None,
) -> None:
    """Handle a selected About menu item."""
    item_id = item.get("id", "")
    if item_id == "report_problem":
        if save_diagnostics is None:
            speech.say("Diagnostics are not available.", priority=True)
        else:
            save_diagnostics()
        return
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
