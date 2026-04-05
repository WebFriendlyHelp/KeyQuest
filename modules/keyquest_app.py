#!python3.11
"""Main Pygame application entry point for KeyQuest."""

import sys
import os
import time
import random
import threading
import subprocess
import traceback
import webbrowser
from collections import Counter
from pathlib import Path
from typing import List, Optional

from modules.app_paths import get_app_dir
from modules import dialog_manager
from modules import audio_manager
from modules import results_formatter
from modules import state_manager
from modules import lesson_manager
from modules import menu_handler
from modules import keyboard_explorer
from modules import challenge_manager
from modules import quest_manager
from modules.speech_manager import Speech
from modules import config as app_config
from modules import theme as theme_manager
from modules import error_logging
from modules import sentences_manager
from modules import streak_manager
from modules import test_modes
from modules import input_utils
from modules import phonetics
from modules import speech_format
from modules import tutorial_data
from modules import tutorial_mode
from modules import lesson_intro_mode
from modules import lesson_mode
from modules import sound_catalog
from modules import sound_demo
from modules import learn_sounds_mode
from modules.escape_guard import EscapePressGuard
from modules import flash_manager
from modules import font_manager
from modules import shop_mode
from modules import pet_mode
from modules import pet_manager
from modules import progress_views
from modules import notifications
from modules import update_manager
from modules import dashboard_manager
from modules import currency_manager
from modules.update_controller import AppUpdateController
from modules.version import __version__
import pygame
import pygame.freetype
from games import LetterFallGame
from games import HangmanGame
from games.word_typing import WordTypingGame
from ui.render_menus import draw_main_menu, draw_lesson_menu, draw_games_menu
from ui.render_shop import draw_shop
from ui.render_pet import draw_pet
from ui.render_options import draw_options
from ui.render_results import draw_results_screen
from ui.render_lesson import draw_lesson_screen
from ui.render_test_setup import draw_test_setup_screen, draw_practice_setup_screen
from ui.render_lesson_intro import draw_lesson_intro_screen
from ui.render_learn_sounds import draw_learn_sounds_menu
from ui.render_test_active import draw_test_screen, draw_practice_screen
from ui.render_keyboard_explorer import draw_keyboard_explorer_screen
from ui.render_free_practice_ready import draw_free_practice_ready_screen
from ui.render_tutorial import draw_tutorial_screen
from ui.text_wrap import wrap_text
from ui.render_updating import draw_updating_screen


# Minimum gap before a main-menu visit triggers a fresh update check.
_UPDATE_MENU_RECHECK_MIN_S = 3600         # 1 hour
# Kept here so update-idle tests can validate the app-level policy constants.
_UPDATE_PERIODIC_INTERVAL_S = 4 * 3600   # 4 hours
_UPDATE_IDLE_INSTALL_S = 30 * 60         # 30 minutes

REPO_OWNER = "WebFriendlyHelp"
REPO_NAME = "KeyQuest"
GITHUB_REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
PAGES_GUIDE_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/"
PAGES_CHANGELOG_URL = f"{PAGES_GUIDE_URL}changelog.html"
INSTALLER_DOWNLOAD_URL = f"{GITHUB_REPO_URL}/releases/latest/download/KeyQuestSetup.exe"
DONATE_URL = "https://square.link/u/XfI4Icmm"

# Optional wxPython for accessible dialogs
try:
    import wx
    WX_AVAILABLE = True
except Exception:
    wx = None
    WX_AVAILABLE = False

# ----------------- Config -----------------
SCREEN_W, SCREEN_H = app_config.SCREEN_W, app_config.SCREEN_H
FONT_NAME = app_config.FONT_NAME
TITLE_SIZE, TEXT_SIZE, SMALL_SIZE = app_config.TITLE_SIZE, app_config.TEXT_SIZE, app_config.SMALL_SIZE

SYSTEM_THEME = theme_manager.detect_theme()
BG, FG, ACCENT, HILITE = theme_manager.get_theme_colors(SYSTEM_THEME)


def _offer_general_error_log_copy() -> None:
    """Inform the user that an unexpected app error was written to the local log."""
    log_path = error_logging.touch_log_file()
    copied = error_logging.copy_log_to_clipboard()
    message = [
        "KeyQuest hit an unexpected error.",
        "",
        f"The details were written to:\n{log_path}",
        "",
    ]
    if copied:
        message.append("The local error log was also copied to the clipboard.")
    else:
        message.append("KeyQuest could not copy the local error log to the clipboard automatically.")
    dialog_manager.show_info_dialog("KeyQuest Error", "\n".join(message))

class KeyQuestApp:
    def __init__(self):
        # wx.App must exist before pygame so modal dialogs can be created reliably.
        try:
            import wx
            if not wx.App.Get():
                self.wx_app = wx.App(False)
                print("wx.App initialized at startup")
        except ImportError:
            self.wx_app = None
            print("wxPython not available - dialogs will print to console")
        except Exception as e:
            self.wx_app = None
            print(f"Warning: Could not initialize wx.App: {e}")

        try:
            # Lower mixer buffer for snappier short typing sounds.
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.init()
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
        except Exception as e:
            error_logging.log_exception(e)
            raise

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
        pygame.display.set_caption("Key Quest")
        self.clock = pygame.time.Clock()
        self._maximize_window()

        self.title_font = pygame.freetype.SysFont(FONT_NAME, TITLE_SIZE)
        self.text_font = pygame.freetype.SysFont(FONT_NAME, TEXT_SIZE)
        self.small_font = pygame.freetype.SysFont(FONT_NAME, SMALL_SIZE)

        self.state = state_manager.AppState()
        self.speech = Speech()
        self.state.backend_label = self._backend_label()
        self._last_speech_backend_check = 0.0
        self._startup_menu_event = pygame.USEREVENT + 1
        self._startup_menu_armed = False
        self.escape_guard = EscapePressGuard()
        self.updates = AppUpdateController(self)
        self._self_update_supported = self.updates.self_update_supported
        self._portable_update_mode = self.updates.portable_update_mode

        # Visual flash mirrors the success/error tones for sighted users.
        self._flash = flash_manager.FlashState()

        # Tracks the on-screen countdown for multi-press Escape exits.
        self._escape_remaining: int = 0
        self._escape_noun: str = ""

        self.audio = audio_manager.AudioManager()
        self.progress_manager = state_manager.ProgressManager()
        self.speed_test_sentences = []
        self.practice_sentences = []
        self.practice_setup_options = []
        self.practice_setup_index = 0
        self.practice_topic_options = []
        self.practice_topic_index = 0
        self.practice_setup_view = "menu"
        self.pet_options = []
        self.pet_types = []
        self.pet_view = "status"
        self.pet_menu_index = 0
        self.pet_choose_index = 0
        self.pet_choose_mode = "new"
        self.test_setup_view = "topics"
        self.test_setup_topic_options = ["Random Topic", "English", "Spanish"]
        self.test_setup_topic_index = 0
        self.test_setup_selected_source = "Random Topic"
        self.speed_test_source = self.state.settings.sentence_language
        self.speed_test_source_label = sentences_manager.get_practice_topic_display_name(
            self.state.settings.sentence_language
        )

        fonts = {
            'title_font': self.title_font,
            'text_font': self.text_font,
            'small_font': self.small_font
        }
        self.games = [
            LetterFallGame(
                self.screen,
                fonts,
                self.speech,
                self.audio.play_wave,
                self.show_info_dialog,
                self.handle_game_session_complete,
            ),
            WordTypingGame(
                self.screen,
                fonts,
                self.speech,
                self.audio.play_wave,
                self.show_info_dialog,
                self.handle_game_session_complete,
            ),
            HangmanGame(
                self.screen,
                fonts,
                self.speech,
                self.audio.play_wave,
                self.show_info_dialog,
                self.handle_game_session_complete,
            ),
        ]
        self.current_game = None
        self.game_time = 0

        self.load_progress()

        # Rebuild fonts after settings load so DPI and user overrides are applied together.
        self._rebuild_fonts()

        self.check_and_update_streak()
        quest_manager.initialize_quests(self.state.settings)
        if challenge_manager.check_if_new_day(self.state.settings):
            challenge_manager.reset_daily_challenge(self.state.settings)
            self.save_progress()

        # Cache practice content for the currently selected language.
        self.speed_test_sentences = sentences_manager.load_speed_test_sentences()
        self.practice_sentences = sentences_manager.load_practice_sentences(self.state.settings.sentence_language)
        print(f"Loaded {len(self.practice_sentences)} practice sentences in {self.state.settings.sentence_language}")

        self._init_menus()
        self._start_startup_update_check_if_enabled()

    def _init_menus(self):
        """Initialize all menu objects."""
        # Main menu
        self.main_menu = menu_handler.Menu(
            name="Main",
            items=self.state.menu_items,
            speech_system=self.speech,
            on_select_callback=self._handle_main_menu_select,
            initial_announcement=lambda: menu_handler.build_main_menu_announcement(
                self.state.menu_items[self.main_menu.current_index],
                self.get_streak_announcement()
            ),
            on_escape_callback=self._quit_app,
            enable_letter_nav=True
        )

        # Lesson menu (dynamic items)
        self.lesson_menu = menu_handler.Menu(
            name="Lesson",
            items=lambda: sorted(list(self.state.settings.unlocked_lessons)),
            speech_system=self.speech,
            on_select_callback=self.start_lesson,
            get_item_text_func=self._get_lesson_item_text,
            initial_announcement=lambda: self._get_lesson_menu_announcement(),
            on_escape_callback=self._return_to_main_menu
        )

        # Games menu
        self.games_menu = menu_handler.Menu(
            name="Games",
            items=self.games,
            speech_system=self.speech,
            on_select_callback=lambda game: self.start_game(self.games.index(game)),
            get_item_text_func=lambda game: f"{game.NAME}. {game.DESCRIPTION}",
            initial_announcement=lambda: self._get_games_menu_announcement(),
            on_escape_callback=self._return_to_main_menu
        )

        # Learn Sounds menu
        self.sound_items = list(sound_catalog.SOUND_ITEMS)
        self.sounds_menu = menu_handler.Menu(
            name="Learn Sounds",
            items=self.sound_items,
            speech_system=self.speech,
            on_select_callback=self._play_sound_demo,
            get_item_text_func=lambda item: f"{item['name']}. {item['description']}",
            initial_announcement=lambda: "Learn Sounds menu. Press Enter or Space on a sound to hear it. Press Escape to return to the main menu.",
            on_escape_callback=self._return_to_main_menu
        )

        # About menu
        self.about_items = [
            {
                "id": "app",
                "display": f"Application: KeyQuest {__version__}",
                "speak": f"Application: KeyQuest version {__version__}.",
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
                "speak": "Official downloads: GitHub Releases only. The updater uses those releases. Other builds are not official.",
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
        self.about_menu = menu_handler.Menu(
            name="About",
            items=self.about_items,
            speech_system=self.speech,
            on_select_callback=self._handle_about_select,
            get_item_text_func=lambda item: item["speak"],
            initial_announcement=self._get_about_menu_announcement,
            on_escape_callback=self._return_to_main_menu,
        )

        # Options menu
        self.options_menu = menu_handler.OptionsMenu(
            name="Options",
            options=[
                {
                    'name': 'speech_mode',
                    'get_value': lambda: self.state.settings.speech_mode,
                    'set_value': lambda v: setattr(self.state.settings, 'speech_mode', v),
                    'get_text': lambda: f"Speech: {self.state.settings.speech_mode}",
                    'get_explanation': lambda: menu_handler.get_speech_mode_explanation(self.state.settings.speech_mode),
                    'cycle': menu_handler.cycle_speech_mode
                },
                {
                    'name': 'typing_sound_intensity',
                    'get_value': lambda: self.state.settings.typing_sound_intensity,
                    'set_value': lambda v: setattr(self.state.settings, 'typing_sound_intensity', v),
                    'get_text': lambda: f"Typing Sounds: {self.state.settings.typing_sound_intensity}",
                    'get_explanation': lambda: menu_handler.get_typing_sound_intensity_explanation(self.state.settings.typing_sound_intensity),
                    'cycle': menu_handler.cycle_typing_sound_intensity
                },
                {
                    'name': 'tts_rate',
                    'get_value': lambda: self.state.settings.tts_rate,
                    'set_value': lambda v: setattr(self.state.settings, 'tts_rate', v),
                    'get_text': lambda: f"TTS Rate: {self.state.settings.tts_rate} WPM",
                    'get_explanation': lambda: menu_handler.get_tts_rate_explanation(self.state.settings.tts_rate),
                    'cycle': menu_handler.cycle_tts_rate
                },
                {
                    'name': 'tts_volume',
                    'get_value': lambda: self.state.settings.tts_volume,
                    'set_value': lambda v: setattr(self.state.settings, 'tts_volume', v),
                    'get_text': lambda: f"TTS Volume: {int(self.state.settings.tts_volume * 100)}%",
                    'get_explanation': lambda: menu_handler.get_tts_volume_explanation(self.state.settings.tts_volume),
                    'cycle': menu_handler.cycle_tts_volume
                },
                {
                    'name': 'tts_voice',
                    'get_value': lambda: self.state.settings.tts_voice,
                    'set_value': lambda v: setattr(self.state.settings, 'tts_voice', v),
                    'get_text': lambda: f"TTS Voice: {menu_handler.get_voice_name_from_id(self.state.settings.tts_voice, self.speech.get_available_voices())}",
                    'get_explanation': lambda: menu_handler.get_tts_voice_explanation(menu_handler.get_voice_name_from_id(self.state.settings.tts_voice, self.speech.get_available_voices())),
                    'cycle': lambda v, d: menu_handler.cycle_tts_voice(v, self.speech.get_available_voices(), d)
                },
                {
                    'name': 'auto_update_check',
                    'get_value': lambda: self.state.settings.auto_update_check,
                    'set_value': lambda v: setattr(self.state.settings, 'auto_update_check', v),
                    'get_text': lambda: f"Automatic Updates: {'On' if self.state.settings.auto_update_check else 'Off'}",
                    'get_explanation': lambda: menu_handler.get_auto_update_explanation(self.state.settings.auto_update_check),
                    'cycle': menu_handler.cycle_bool
                },
                {
                    'name': 'auto_start_next_lesson',
                    'get_value': lambda: self.state.settings.auto_start_next_lesson,
                    'set_value': lambda v: setattr(self.state.settings, 'auto_start_next_lesson', v),
                    'get_text': lambda: f"Auto Start Next Lesson: {'On' if self.state.settings.auto_start_next_lesson else 'Off'}",
                    'get_explanation': lambda: menu_handler.get_auto_start_next_lesson_explanation(self.state.settings.auto_start_next_lesson),
                    'cycle': menu_handler.cycle_bool
                },
                {
                    'name': 'visual_theme',
                    'get_value': lambda: self.state.settings.visual_theme,
                    'set_value': lambda v: setattr(self.state.settings, 'visual_theme', v),
                    'get_text': lambda: f"Visual Theme: {self.state.settings.visual_theme}",
                    'get_explanation': lambda: menu_handler.get_theme_explanation(self.state.settings.visual_theme),
                    'cycle': menu_handler.cycle_theme
                },
                {
                    'name': 'focus_assist',
                    'get_value': lambda: self.state.settings.focus_assist,
                    'set_value': lambda v: setattr(self.state.settings, 'focus_assist', v),
                    'get_text': lambda: f"Focus Assist: {'On' if self.state.settings.focus_assist else 'Off'}",
                    'get_explanation': lambda: menu_handler.get_focus_assist_explanation(self.state.settings.focus_assist),
                    'cycle': menu_handler.cycle_bool
                },
                {
                    'name': 'sentence_language',
                    'get_value': lambda: self.state.settings.sentence_language,
                    'set_value': lambda v: setattr(self.state.settings, 'sentence_language', v),
                    'get_text': lambda: (
                        "Practice Topic: "
                        f"{sentences_manager.get_practice_topic_display_name(self.state.settings.sentence_language)}"
                    ),
                    'get_explanation': lambda: menu_handler.get_language_explanation(self.state.settings.sentence_language),
                    'cycle': menu_handler.cycle_language
                },
                {
                    'name': 'font_scale',
                    'get_value': lambda: self.state.settings.font_scale,
                    'set_value': lambda v: setattr(self.state.settings, 'font_scale', v),
                    'get_text': lambda: f"Font Size: {self.state.settings.font_scale}",
                    'get_explanation': lambda: menu_handler.get_font_scale_explanation(self.state.settings.font_scale),
                    'cycle': menu_handler.cycle_font_scale
                }
            ],
            speech_system=self.speech,
            on_change_callback=self._handle_option_change,
            initial_announcement=lambda: self._get_options_menu_announcement(),
            on_escape_callback=self._return_to_main_menu_and_save
        )

    def _handle_main_menu_select(self, choice):
        """Handle main menu item selection."""
        # Strip the hotkey suffix (e.g., ": T") from the choice
        if ": " in choice:
            choice = choice.rsplit(": ", 1)[0]

        if choice == "Tutorial":
            self.start_tutorial()
        elif choice == "Keyboard Explorer":
            self.start_keyboard_explorer()
        elif choice == "Lessons":
            self.show_lesson_menu()
        elif choice == "Free Practice":
            self.start_free_practice_setup()
        elif choice == "Speed Test":
            self.start_test()
        elif choice == "Sentence Practice":
            self.start_practice()
        elif choice == "Open Sentences Folder":
            self.open_sentences_folder()
        elif choice == "Games":
            self.show_games_menu()
        elif choice == "Pet Shop":
            self.show_shop(categories=["pet_items"], title="Pet Shop")
        elif choice == "Pets":
            self.show_pet()
        elif choice in ("Badges", "View Badges"):
            self.show_badge_viewer()
        elif choice in ("Quests", "View Quests"):
            self.show_quest_viewer()
        elif choice == "Progress Dashboard":
            self.show_progress_dashboard()
        elif choice == "Practice Log":
            self.show_practice_log()
        elif choice == "Daily Challenge":
            self.show_daily_challenge()
        elif choice == "Key Performance":
            self.show_key_performance_report()
        elif choice == "Options":
            self.show_options_menu()
        elif choice == "Learn Sounds":
            self.show_learn_sounds_menu()
        elif choice == "Check for Updates":
            self.start_update_check(manual=True)
        elif choice == "Key Quest Instructions":
            self.open_keyquest_instructions()
        elif choice == "New in Key Quest":
            self.open_keyquest_whats_new()
        elif choice == "About":
            self.show_about_menu()
        elif choice == "Quit":
            self._quit_app()

    def _get_about_menu_announcement(self) -> str:
        return (
            f"About menu. KeyQuest version {__version__}. Name: Casey Mathews. Company: Web Friendly Help L L C. "
            "Use Up and Down to choose. Press Enter or Space to select. "
            "Press Escape to return to main menu."
        )

    def open_keyquest_instructions(self):
        """Open the published user instructions in the default browser."""
        self.speech.say("Opening Key Quest Instructions.", priority=True)
        try:
            webbrowser.open(PAGES_GUIDE_URL, new=2)
        except Exception:
            self.speech.say("Unable to open Key Quest Instructions.", priority=True)

    def open_keyquest_whats_new(self):
        """Open the published changelog page in the default browser."""
        self.speech.say("Opening New in Key Quest.", priority=True)
        try:
            webbrowser.open(PAGES_CHANGELOG_URL, new=2)
        except Exception:
            self.speech.say("Unable to open New in Key Quest.", priority=True)

    def open_sentences_folder(self):
        """Open the current Sentences folder in Windows Explorer."""
        sentences_dir = Path(get_app_dir()) / "Sentences"
        if not sentences_dir.exists():
            self.speech.say("Sentences folder was not found.", priority=True)
            return

        try:
            os.startfile(str(sentences_dir))
            self.speech.say("Opening Sentences folder.", priority=True)
        except Exception:
            self.speech.say("Unable to open the Sentences folder.", priority=True)

    def _offer_installer_download_after_update_failure(self):
        """Offer a direct fallback to the latest installer when updating fails."""
        should_open = dialog_manager.show_yes_no_dialog(
            "Update Failed",
            "Automatic updating failed.\n\n"
            "Would you like to download the latest KeyQuest setup program instead?",
            yes_label="Download Setup",
            no_label="Not Now",
        )
        if not should_open:
            return

        try:
            webbrowser.open(INSTALLER_DOWNLOAD_URL)
            self.speech.say("Opening the KeyQuest setup download.", priority=True)
        except Exception as e:
            self.speech.say(f"Unable to open the KeyQuest setup download. {e}", priority=True)

    def _record_update_error(self, summary: str, tb_str: str = ""):
        """Persist updater failures to the local log file."""
        error_logging.log_message("Updater Error", summary, tb_str=tb_str)

    def _record_update_event(self, message: str):
        """Persist updater progress milestones to the local log file."""
        error_logging.log_message("Updater", message)

    def _copy_error_log_with_feedback(self, title: str = "Error Log") -> bool:
        """Copy the local error log to the clipboard and report the result accessibly."""
        log_path = error_logging.touch_log_file()
        copied = error_logging.copy_log_to_clipboard()
        if copied:
            self.speech.say("Error log copied to clipboard.", priority=True)
            dialog_manager.show_info_dialog(
                title,
                "KeyQuest saved the local error log and copied it to the clipboard.\n\n"
                f"Log location:\n{log_path}",
            )
            return True

        self.speech.say("Unable to copy the error log to clipboard.", priority=True)
        dialog_manager.show_info_dialog(
            title,
            "KeyQuest saved the local error log, but could not copy it to the clipboard automatically.\n\n"
            f"Log location:\n{log_path}",
        )
        return False

    def _offer_update_failure_recovery(self, summary: str, tb_str: str = ""):
        """Offer recovery actions after an updater error."""
        log_path = error_logging.touch_log_file()
        self._record_update_error(summary, tb_str=tb_str)
        self._update_error_message = f"{summary} Local log saved to {log_path}."
        self._copy_error_log_with_feedback(title="Update Error")
        self._offer_installer_download_after_update_failure()

    def _handle_about_select(self, item):
        item_id = item.get("id", "")
        if item_id == "website":
            self.speech.say("Opening webfriendlyhelp dot com.", priority=True)
            try:
                webbrowser.open("https://webfriendlyhelp.com", new=2)
            except Exception:
                self.speech.say("Unable to open website.", priority=True)
            return
        if item_id == "donate":
            self.speech.say("Opening the KeyQuest donation page.", priority=True)
            try:
                webbrowser.open(DONATE_URL, new=2)
            except Exception:
                self.speech.say("Unable to open donation page.", priority=True)
            return
        if item_id == "back":
            self._return_to_main_menu()
            return
        self.speech.say(item.get("speak", item.get("display", "")), priority=True)

    def _handle_option_change(self, option_index, old_value, new_value):
        """Handle option value change."""
        option_name = self.options_menu.options[option_index]["name"]

        if option_name == "speech_mode":
            self.apply_speech_mode()
            # Apply TTS settings when switching to TTS mode
            if new_value == 'tts':
                self.apply_tts_settings()
        elif option_name == "typing_sound_intensity":
            self.apply_typing_sound_intensity()
        elif option_name == "tts_rate":
            self.apply_tts_settings()
        elif option_name == "tts_volume":
            self.apply_tts_settings()
        elif option_name == "tts_voice":
            self.apply_tts_settings()
        elif option_name == "auto_update_check":
            self.save_progress()
        elif option_name == "auto_start_next_lesson":
            self.save_progress()
        elif option_name == "visual_theme":
            self.apply_visual_theme()
        elif option_name == "sentence_language":
            print(f"Language changed from {old_value} to {new_value}")
            self.practice_sentences = sentences_manager.load_practice_sentences(new_value)
            print(f"Reloaded {len(self.practice_sentences)} practice sentences in {new_value}")
            if self.practice_sentences:
                print(f"First sentence: {self.practice_sentences[0]}")
                print(f"Last sentence: {self.practice_sentences[-1]}")
        elif option_name == "font_scale":
            self._rebuild_fonts()

    def _quit_app(self):
        """Quit the application."""
        try:
            screen_w, screen_h = self._screen_size()
            self.screen.fill(BG)
            goodbye_font = pygame.font.SysFont(FONT_NAME, 56)
            goodbye_surface = goodbye_font.render("Goodbye!", True, FG)
            goodbye_rect = goodbye_surface.get_rect(center=(screen_w // 2, screen_h // 2))
            self.screen.blit(goodbye_surface, goodbye_rect)
            pygame.display.flip()
        except Exception:
            pass

        self.speech.say("Goodbye.", priority=True, protect_seconds=1.2, interrupt=False)
        pygame.time.wait(900)
        self.speech.shutdown()
        pygame.quit()
        import sys
        sys.exit(0)

    def _return_to_main_menu(self):
        """Return to main menu (preserves last position)."""
        self.state.mode = "MENU"
        # Don't reset index - preserve user's last position
        # Wrap announce in try/except in case called immediately after wx dialog
        # (pygame/wx event loop conflict can cause issues)
        try:
            self.main_menu.announce_current()
        except Exception as e:
            # If announcement fails (e.g., after wx dialog), log but don't crash
            print(f"Warning: Menu announcement failed: {e}")
            # Will be announced on next user interaction anyway
        self.updates.begin_pending_update_if_ready()
        # Trigger a fresh background update check each time the user reaches
        # the main menu, but no more often than once per hour.
        self.updates.maybe_check_from_main_menu(_UPDATE_MENU_RECHECK_MIN_S)

    def _return_to_main_menu_and_save(self):
        """Return to main menu and save progress."""
        self.save_progress()
        self._return_to_main_menu()

    def _get_lesson_item_text(self, lesson_num: int) -> str:
        """Get display text for a lesson menu item with star rating.

        Args:
            lesson_num: Lesson number

        Returns:
            Formatted lesson text with stars if earned
        """
        lesson_name = lesson_manager.LESSON_NAMES[lesson_num]
        stars = self.state.settings.lesson_stars.get(lesson_num, 0)

        if stars > 0:
            star_display = "*" * stars
            return f"Lesson {lesson_num}: {lesson_name} {star_display}"
        else:
            return f"Lesson {lesson_num}: {lesson_name}"

    def _get_lesson_menu_announcement(self):
        """Get lesson menu initial announcement."""
        unlocked = sorted(list(self.state.settings.unlocked_lessons))
        if unlocked:
            first_lesson = unlocked[0]
            lesson_name = lesson_manager.LESSON_NAMES[first_lesson]
            return menu_handler.build_lesson_menu_announcement(lesson_name)
        return "Lesson menu. No lessons available."

    def _get_games_menu_announcement(self):
        """Get games menu initial announcement."""
        if self.games:
            first_game = self.games[0]
            return menu_handler.build_games_menu_announcement(first_game.NAME, first_game.DESCRIPTION)
        return "Games menu. No games available."

    def _get_options_menu_announcement(self):
        """Get options menu initial announcement."""
        options = menu_handler.get_options_items(self.state.settings)
        explanation = menu_handler.get_speech_mode_explanation(self.state.settings.speech_mode)
        return menu_handler.build_options_menu_announcement(options[0], explanation)

    def load_progress(self):
        """Load progress from file using ProgressManager."""
        loaded = self.progress_manager.load(self.state, len(lesson_manager.STAGE_LETTERS))
        # Apply loaded settings
        self.apply_speech_mode()
        self.apply_typing_sound_intensity()
        self.apply_tts_settings()
        self.apply_visual_theme()
        if loaded is False:
            log_path = error_logging.touch_log_file()
            copied = error_logging.copy_log_to_clipboard()
            clipboard_note = (
                "The error log was also copied to the clipboard."
                if copied
                else "KeyQuest could not copy the error log to the clipboard automatically."
            )
            self.show_info_dialog(
                "Progress Not Loaded",
                "KeyQuest could not load your saved progress and has started with default settings.\n\n"
                "Your previous progress file may be missing or corrupted.\n\n"
                f"Details were written to:\n{log_path}\n\n"
                f"{clipboard_note}",
            )

    def save_progress(self):
        """Save progress to file using ProgressManager."""
        self.progress_manager.save(self.state)

    def check_and_update_streak(self):
        """Check and update the daily practice streak."""
        prev_streak = self.state.settings.current_streak
        prev_date = self.state.settings.last_practice_date

        milestone = streak_manager.check_and_update_streak(self.state.settings)

        if milestone is not None:
            self.audio.play_success()
            self.speech.say(
                f"Streak milestone! Day {milestone} of your typing streak! Keep it up!",
                priority=True,
                protect_seconds=3.0,
            )

        if (
            self.state.settings.current_streak != prev_streak
            or self.state.settings.last_practice_date != prev_date
        ):
            self.save_progress()

    def get_streak_announcement(self):
        """Get the current streak announcement for the menu."""
        return streak_manager.get_streak_announcement(self.state.settings)

    def _backend_label(self) -> str:
        if self.speech.backend == "tolk":
            return "Screen Reader"
        if self.speech.backend == "tts":
            return "TTS"
        return "No Speech"


    def show_results_dialog(self, results_text: str, title: str = "Results"):
        """Show results in an accessible dialog (uses universal dialog system)."""
        dialog_manager.show_results_dialog(title, results_text)

    def show_guided_results_dialog(
        self,
        results_text: str,
        *,
        title: str,
        enter_target: str = "continue to your choices",
    ) -> None:
        """Show a results dialog with keyboard reading instructions at the top."""
        nav_instruction = f"Press Enter to {enter_target}."
        intro = f"Use Up and Down arrows to read these results.\n{nav_instruction}"
        content = f"{intro}\n\n{results_text}\n\n{nav_instruction}"
        self.show_results_dialog(content, title=title)

    def _configure_results_menu(self, title: str, body: str, options: list[str]) -> None:
        """Populate the on-screen results menu shown after dialogs close."""
        self.state.mode = "RESULTS"
        self.state.results_title = title
        self.state.results_instructions = (
            "Use Up and Down arrows to review choices. Press Enter or Space to select. Press Escape for the main menu."
        )
        self.state.results_text = body
        self.state.results_options = options
        self.state.results_index = 0

    def _announce_results_menu(self) -> None:
        """Announce the results menu title, instructions, and current choice."""
        option = ""
        if self.state.results_options:
            option = self.state.results_options[self.state.results_index]
        message = (
            f"{self.state.results_title}. {self.state.results_instructions} "
            f"Current choice: {option}."
        )
        self.speech.say(message, priority=True, protect_seconds=3.0)

    def show_info_dialog(self, title: str, content: str):
        """Show informational content in an accessible dialog (uses universal dialog system)."""
        dialog_manager.show_info_dialog(title, content)

    def _start_startup_update_check_if_enabled(self):
        self.updates.start_startup_update_check_if_enabled()

    def start_update_check(self, manual: bool):
        self.updates.start_update_check(manual)

    def _begin_pending_update_if_ready(self):
        """Start a deferred update once the user is at the main menu and idle long enough."""
        if self.state.mode != "MENU":
            return
        if not self._pending_update_release:
            return
        if time.monotonic() - self._last_user_activity < _UPDATE_IDLE_INSTALL_S:
            return  # still within the activity window — check again later

        payload = self._pending_update_release
        self._pending_update_release = None
        self._record_update_event(
            f"User idle {_UPDATE_IDLE_INSTALL_S // 60} min. Resuming deferred update for version {payload.get('version', 'unknown')}."
        )
        self._begin_update_download(payload)

    def _begin_update_download(self, payload: dict):
        """Start downloading a discovered installer update."""
        if self.state.mode == "UPDATING":
            return

        version = payload["version"]
        asset = payload["asset"]
        download_url = str(asset.get("browser_download_url") or "")
        self.state.mode = "UPDATING"
        self._update_downloaded_bytes = 0
        self._update_total_bytes = int(asset.get("size", 0) or 0)
        self._update_status = (
            f"Update available: KeyQuest {version}. Downloading and installing now. "
            "Keyboard and mouse input are disabled in KeyQuest during the update."
        )
        self.speech.say(
            f"Update available. Downloading and installing KeyQuest version {version} now. "
            "KeyQuest input is disabled during the update.",
            priority=True,
            protect_seconds=3.5,
        )
        self._record_update_event(
            f"Starting update download for version {version}. "
            f"Asset: {asset.get('name', 'unknown')}. URL: {download_url or 'missing'}."
        )

        self._update_download_thread = threading.Thread(
            target=self._download_update_worker,
            args=(payload,),
            daemon=True,
        )
        self._update_download_thread.start()

    def _download_update_worker(self, payload: dict):
        """Worker that downloads the update installer."""
        try:
            version = payload["version"]
            asset = payload["asset"]
            release = payload.get("release", {})
            asset_name = str(asset.get("name") or "")
            download_url = asset.get("browser_download_url")
            if not download_url:
                raise RuntimeError("Release installer did not include a download URL.")

            destination = (
                update_manager.get_updates_dir() / update_manager.build_portable_zip_filename(version)
                if self._portable_update_mode
                else update_manager.get_updates_dir() / update_manager.build_installer_filename(version)
            )

            def _progress(downloaded: int, total: int):
                with self._update_lock:
                    self._update_downloaded_bytes = downloaded
                    self._update_total_bytes = total
                    if total > 0:
                        percent = int((downloaded / total) * 100)
                        self._update_status = f"Downloading update: {percent}% complete."
                    else:
                        self._update_status = f"Downloading update: {downloaded // 1024} KB received."

            installer_path = update_manager.download_file(
                download_url,
                destination,
                progress_callback=_progress,
            )

            sha256_asset = update_manager.select_sha256_asset(release, asset_name)
            if sha256_asset:
                self._record_update_event("Verifying download integrity via SHA-256.")
                expected_hash = update_manager.fetch_sha256_for_asset(sha256_asset)
                if expected_hash:
                    if not update_manager.verify_file_sha256(installer_path, expected_hash):
                        raise RuntimeError(
                            "Downloaded file did not match the expected SHA-256 hash. "
                            "The file may be corrupted. Please try again."
                        )
                    self._record_update_event("SHA-256 verification passed.")
                else:
                    self._record_update_event(
                        "SHA-256 sidecar asset found but could not be fetched. Skipping hash check."
                    )
            else:
                self._record_update_event("No SHA-256 sidecar asset in this release. Skipping hash check.")

            result = {"status": "downloaded", "version": version, "download_path": str(installer_path)}
        except Exception as e:
            result = {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

        with self._update_lock:
            self._update_download_result = result

    def _poll_update_work(self):
        """Process any completed update background work on the main thread."""
        check_result = None
        download_result = None
        with self._update_lock:
            if self._update_check_result is not None:
                check_result = self._update_check_result
                self._update_check_result = None
            if self._update_download_result is not None:
                download_result = self._update_download_result
                self._update_download_result = None

        if check_result is not None:
            self._handle_update_check_result(check_result)
        if download_result is not None:
            self._handle_update_download_result(download_result)

        now = time.monotonic()

        # Periodic background update check (every 4 hours while running).
        if (self._self_update_supported
                and self.state.mode != "UPDATING"
                and not (self._update_check_thread and self._update_check_thread.is_alive())
                and not (self._update_download_thread and self._update_download_thread.is_alive())
                and now - self._update_periodic_last_check >= _UPDATE_PERIODIC_INTERVAL_S):
            self.start_update_check(manual=False)

        if self._pending_update_release:
            self._begin_pending_update_if_ready()

    def _handle_update_check_result(self, result: dict):
        """Handle update-check completion."""
        status = result.get("status")
        manual = bool(result.get("manual"))

        if status == "up_to_date":
            self._update_status = "KeyQuest is up to date."
            self._record_update_event(f"Update check completed. No newer release was found than {__version__}.")
            if manual:
                self.speech.say("KeyQuest is up to date.", priority=True)
            return

        if status == "missing_asset":
            asset_kind = result.get("asset_kind", "update file")
            self._update_status = f"An update was found, but no {asset_kind} asset was attached to the release."
            self._record_update_event(
                f"Update check found version {result.get('version', 'unknown')}, "
                f"but no {asset_kind} asset was attached to the release."
            )
            if manual:
                self.speech.say(f"An update was found, but the release does not include the expected {asset_kind} yet.", priority=True)
            return

        if status == "error":
            self._update_error_message = result.get("message", "Unknown update error.")
            self._update_status = "Update check failed."
            self.state.mode = "MENU"
            if manual:
                self.speech.say(f"Update check failed. {self._update_error_message}", priority=True)
                self._offer_update_failure_recovery(
                    self._update_error_message,
                    tb_str=result.get("traceback", ""),
                )
            else:
                self._record_update_error(
                    self._update_error_message,
                    tb_str=result.get("traceback", ""),
                )
            return

        if status != "update_available":
            return

        self._record_update_event(
            f"Update available: current version {__version__}, new version {result.get('version', 'unknown')}."
        )
        idle_s = time.monotonic() - self._last_user_activity
        if self.state.mode == "MENU" and idle_s >= _UPDATE_IDLE_INSTALL_S:
            self._begin_update_download(result)
            return

        self._record_update_event(
            f"Update to version {result.get('version', 'unknown')} deferred "
            f"(mode={self.state.mode}, idle={int(idle_s)}s). "
            "Will install when at main menu and idle."
        )
        self._pending_update_release = result
        self._pending_update_manual = manual

    def _handle_update_download_result(self, result: dict):
        """Handle update download completion."""
        status = result.get("status")
        if status == "error":
            self._update_error_message = result.get("message", "Unknown update download error.")
            self._update_status = "Update download failed."
            self.state.mode = "MENU"
            self.speech.say(f"Update download failed. {self._update_error_message}", priority=True)
            self._offer_update_failure_recovery(
                self._update_error_message,
                tb_str=result.get("traceback", ""),
            )
            self.main_menu.announce_current()
            return

        if status == "downloaded":
            self._record_update_event(
                f"Update download finished for version {result.get('version', 'unknown')}. "
                f"Staged file: {result.get('download_path', '')}"
            )
            self._launch_downloaded_update(result["download_path"], result["version"])

    def _launch_downloaded_update(self, download_path: str, version: str):
        """Launch the correct update handoff and then exit the app."""
        app_exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.join(get_app_dir(), "KeyQuest.exe")
        if self._portable_update_mode:
            launcher_path = update_manager.create_portable_update_launcher(
                zip_path=Path(download_path),
                app_dir=get_app_dir(),
                app_exe_path=app_exe_path,
                current_pid=os.getpid(),
            )
        else:
            launcher_path = update_manager.create_update_launcher(
                installer_path=Path(download_path),
                app_dir=get_app_dir(),
                app_exe_path=app_exe_path,
                current_pid=os.getpid(),
            )

        self._record_update_event(
            f"Prepared update launcher for version {version}. "
            f"Downloaded file: {download_path}. Launcher: {launcher_path}."
        )

        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            subprocess.Popen(
                ["cmd", "/c", str(launcher_path)],
                creationflags=creationflags,
                close_fds=True,
                startupinfo=startupinfo,
            )
        except Exception as e:
            self.state.mode = "MENU"
            self._update_status = "Unable to launch the updater."
            self.speech.say(f"Unable to launch the update helper. {e}", priority=True)
            self._record_update_error(
                f"Unable to launch the update helper for version {version}. {e}",
                tb_str=traceback.format_exc(),
            )
            self.main_menu.announce_current()
            return

        action_text = "Installing" if not self._portable_update_mode else "Applying portable update for"
        self._update_status = f"{action_text} KeyQuest {version}. KeyQuest will restart automatically."
        self._record_update_event(
            f"Update helper launched for version {version}. "
            f"KeyQuest will now exit and wait for the launcher to install and restart the app."
        )
        self.save_progress()
        self.speech.say(
            f"{action_text} KeyQuest version {version}. KeyQuest will restart automatically.",
            priority=True,
            protect_seconds=2.0,
        )
        pygame.time.wait(750)
        pygame.quit()
        sys.exit(0)

    def show_badge_notifications(self):
        """Show any pending badge unlock notifications."""
        notifications.show_badge_notifications(self)

    def show_level_up_notification(self, xp_result: dict):
        """Show level-up notification.

        Args:
            xp_result: Result from xp_manager.award_xp with level info
        """
        notifications.show_level_up_notification(self, xp_result)

    def show_quest_notifications(self):
        """Show any pending quest completion notifications."""
        notifications.show_quest_notifications(self)

    def apply_pet_session_progress(self, recent_performance: dict, xp_amount: int) -> dict:
        """Update pet mood/xp from session performance and announce key changes."""
        result = pet_manager.apply_session_pet_progress(
            self.state.settings,
            recent_performance=recent_performance,
            xp_amount=xp_amount,
        )
        if not result.get("has_pet"):
            return result

        pet_status = pet_manager.get_pet_status(self.state.settings)
        pet_name = pet_status.get("pet_name", "Your pet")

        if result.get("evolved"):
            stage_name = result.get("stage_name") or f"stage {result['new_stage']}"
            self.audio.play_pet_evolve()
            self.speech.say(
                f"{pet_name} evolved to {stage_name}! {result.get('summary', '')}",
                priority=True,
                protect_seconds=2.0,
            )
        elif result.get("mood_changed"):
            self.audio.play_pet_sound(self.state.settings.pet_type)
            self.speech.say(
                f"{pet_name} is feeling {result['mood']}. {result['mood_message']} {result.get('summary', '')}",
                priority=True,
                protect_seconds=2.0,
            )

        return result

    def handle_game_session_complete(self, game, session_stats: Optional[dict] = None) -> None:
        """Apply cross-system updates when any game session ends.

        Games report their metrics through BaseGame.show_game_results(). Future games
        only need to call that method with optional session_stats.
        """
        stats = session_stats or {}
        accuracy = float(stats.get("accuracy", 80.0))
        if accuracy < 0:
            accuracy = 0.0
        if accuracy > 100:
            accuracy = 100.0

        duration_minutes = float(stats.get("session_duration_minutes", 1.0))
        if duration_minutes < 0:
            duration_minutes = 0.0

        game_xp = int(stats.get("pet_xp", 12))
        if game_xp <= 0:
            game_xp = 12
        coins_earned = currency_manager.award_coins(self.state.settings, "game_played")

        pet_result = self.apply_pet_session_progress(
            recent_performance={
                "new_best_wpm": False,
                "new_best_accuracy": False,
                "accuracy": accuracy,
                "session_duration": duration_minutes,
                "streak_broken": False,
            },
            xp_amount=game_xp,
        )
        dashboard_manager.record_session(
            self.state.settings,
            {
                "type": "game",
                "summary": getattr(game, "NAME", "Game"),
                "accuracy": accuracy,
                "duration": duration_minutes * 60.0,
                "earned": (
                    f"Coins +{coins_earned}, Pet XP +{pet_result.get('xp_awarded', 0)}"
                    if pet_result.get("has_pet")
                    else f"Coins +{coins_earned}"
                ),
            },
        )
        reward_bits = []
        if coins_earned:
            reward_bits.append(currency_manager.get_coin_announcement("game_played", coins_earned))
        if pet_result.get("has_pet"):
            reward_bits.append(f"Pet status: {pet_result.get('summary', '')}")
        if reward_bits:
            self.speech.say(" ".join(reward_bits), priority=True, protect_seconds=2.5)
        self.save_progress()

    def show_badge_viewer(self):
        """Show all earned and locked badges."""
        progress_views.show_badge_viewer(self)

    def show_quest_viewer(self):
        """Show active and completed quests."""
        progress_views.show_quest_viewer(self)

    def show_progress_dashboard(self):
        """Show comprehensive progress dashboard."""
        progress_views.show_progress_dashboard(self)

    def show_practice_log(self):
        """Show recent practice history."""
        progress_views.show_practice_log(self)

    def show_daily_challenge(self):
        """Show today's daily challenge."""
        progress_views.show_daily_challenge(self)

    def show_key_performance_report(self):
        """Show keyboard performance analytics."""
        progress_views.show_key_performance_report(self)

    # ==================== SHOP ====================

    def show_shop(self, categories: Optional[List[str]] = None, title: str = "Shop"):
        """Show shop interface for purchasing items."""
        shop_mode.show_shop(self, categories=categories, title=title)

    def handle_shop_input(self, event, mods):
        """Handle shop navigation and purchases."""
        shop_mode.handle_shop_input(self, event, mods)

    def _announce_shop_item(self, item_id: str):
        """Announce a shop item with details."""
        shop_mode.announce_shop_item(self, item_id)

    def _purchase_shop_item(self, item_id: str):
        """Attempt to purchase a shop item."""
        shop_mode.purchase_shop_item(self, item_id)

    # ==================== PET ====================

    def show_pet(self):
        """Show pet interface."""
        pet_mode.ensure_pet_ui_state(self)
        pet_mode.show_pet(self)

    def handle_pet_input(self, event, mods):
        """Handle pet navigation and interactions."""
        pet_mode.ensure_pet_ui_state(self)
        pet_mode.handle_pet_input(self, event, mods)

    def _announce_pet_type(self, pet_type: str):
        """Announce a pet type with description."""
        pet_mode.announce_pet_type(self, pet_type)

    def _handle_pet_action(self, action: str):
        """Handle pet actions."""
        pet_mode.handle_pet_action(self, action)

    # ==================== FREE PRACTICE MODE ====================

    def start_free_practice_setup(self):
        """Start Free Practice mode setup - allows practice without affecting progress."""
        unlocked_lessons = sorted(
            lesson_num
            for lesson_num in self.state.settings.unlocked_lessons
            if lesson_num < len(lesson_manager.STAGE_LETTERS)
        )
        if not unlocked_lessons:
            self.speech.say("No keys learned yet. Complete the tutorial first.", priority=True, protect_seconds=2.0)
            self._return_to_main_menu()
            return

        learned_keys = set()
        for lesson_num in unlocked_lessons:
            learned_keys.update(lesson_manager.STAGE_LETTERS[lesson_num])

        free_practice = self.state.free_practice
        free_practice.available_lessons = unlocked_lessons
        free_practice.lesson_index = 0
        free_practice.available_keys = learned_keys
        free_practice.selected_lesson = unlocked_lessons[0]
        free_practice.selected_keys = set().union(*lesson_manager.STAGE_LETTERS[: unlocked_lessons[0] + 1])
        free_practice.in_session = False

        self.state.mode = "FREE_PRACTICE_READY"
        self._announce_free_practice_choice(priority=True)

    def _announce_free_practice_choice(self, priority: bool = False) -> None:
        free_practice = self.state.free_practice
        if not free_practice.available_lessons:
            return

        lesson_num = free_practice.available_lessons[free_practice.lesson_index]
        lesson_name = (
            lesson_manager.LESSON_NAMES[lesson_num]
            if lesson_num < len(lesson_manager.LESSON_NAMES)
            else f"Lesson {lesson_num}"
        )
        key_count = len(set().union(*lesson_manager.STAGE_LETTERS[: lesson_num + 1]))
        self.speech.say(
            f"Free practice setup. Lesson {lesson_num}. {lesson_name}. "
            f"Practice keys through this lesson, {key_count} keys total. "
            "Use Up and Down arrows to choose a lesson. Press Enter or Space to start. Escape returns to the main menu.",
            priority=priority,
            protect_seconds=3.0 if priority else 0.0,
        )

    def _set_free_practice_lesson(self, lesson_num: int) -> None:
        free_practice = self.state.free_practice
        free_practice.selected_lesson = lesson_num
        free_practice.selected_keys = set().union(*lesson_manager.STAGE_LETTERS[: lesson_num + 1])

    def start_free_practice(self):
        """Start the free practice session."""
        self.state.mode = "FREE_PRACTICE"
        self.state.free_practice.in_session = True

        # Initialize lesson state for practice (reuse lesson mechanics)
        lesson = self.state.lesson
        lesson.stage = -1  # Flag for free practice (negative means no progress saving)
        lesson.tracker = state_manager.AdaptiveTracker()
        lesson.index = 0
        lesson.typed = ""
        lesson.use_words = True
        lesson.review_mode = False
        lesson.start_time = time.time()

        # Build batch with selected keys
        self.build_free_practice_batch()

        # Announce first word with instructions (like lessons do)
        target = lesson.batch_words[lesson.index]
        speakable = self._make_speakable(target)
        self.speech.say(
            f"Free practice. Control Space repeats. Type {speakable}",
            priority=True,
            protect_seconds=3.0,
        )

    def build_free_practice_batch(self):
        """Build a practice batch using selected keys."""
        lesson = self.state.lesson
        keys = list(self.state.free_practice.selected_keys)

        if not keys:
            keys = ['a', 's', 'd', 'f']  # Fallback to home row

        # Use lesson manager's word building logic
        lesson.batch_words = lesson_manager.generate_words_from_keys(keys, count=15, use_real_words=True)
        lesson.batch_instructions = []

    def handle_free_practice_ready_input(self, event, mods):
        """Handle input in Free Practice ready state."""
        free_practice = self.state.free_practice
        lessons = free_practice.available_lessons

        if not lessons:
            self._return_to_main_menu()
            return

        if event.key == pygame.K_UP:
            free_practice.lesson_index = menu_handler.navigate_up(free_practice.lesson_index, len(lessons))
            self._announce_free_practice_choice()
        elif event.key == pygame.K_DOWN:
            free_practice.lesson_index = menu_handler.navigate_down(free_practice.lesson_index, len(lessons))
            self._announce_free_practice_choice()
        elif event.key == pygame.K_HOME:
            free_practice.lesson_index = menu_handler.navigate_first(len(lessons))
            self._announce_free_practice_choice()
        elif event.key == pygame.K_END:
            free_practice.lesson_index = menu_handler.navigate_last(len(lessons))
            self._announce_free_practice_choice()
        elif event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
            self._announce_free_practice_choice(priority=True)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            lesson_num = lessons[free_practice.lesson_index]
            self._set_free_practice_lesson(lesson_num)
            self.start_free_practice()
        elif event.key == pygame.K_ESCAPE:
            self.state.free_practice.in_session = False
            self._return_to_main_menu()

    def end_free_practice(self):
        """End free practice session and show results."""
        lesson = self.state.lesson
        lesson.end_time = time.time()

        # Calculate statistics (but don't save to progress)
        duration = lesson.end_time - lesson.start_time
        accuracy = lesson.tracker.overall_accuracy() * 100
        wpm = lesson.tracker.calculate_wpm(duration)
        total_correct = lesson.tracker.total_correct
        total_attempts = lesson.tracker.total_attempts
        total_errors = total_attempts - total_correct
        minutes = duration / 60.0 if duration > 0 else 0.0
        gross_wpm = ((total_attempts / 5.0) / minutes) if minutes > 0 else 0.0

        # Format results
        results_text = (
            f"Accuracy: {accuracy:.0f}%\n"
            f"Corrected Words Per Minute: {wpm:.1f}\n"
            f"Total Words Per Minute: {gross_wpm:.1f}\n"
            f"Correct: {total_correct}\n"
            f"Errors: {total_errors}\n"
            f"Time: {duration:.1f} seconds\n\n"
            f"Results not saved (practice mode)."
        )

        # Show results
        self.audio.play_victory()
        self.show_guided_results_dialog(
            f"Free Practice Complete!\n\n{results_text}",
            title="Free Practice Results",
            enter_target="continue to your choices",
        )

        self.state.free_practice.in_session = False
        self.state.results_action = "free_practice"
        self._configure_results_menu(
            title="Free Practice Complete",
            body=results_text,
            options=[
                "Start free practice again",
                "Return to main menu",
            ],
        )
        self._announce_results_menu()

    # =========================================================

    def _make_speakable(self, text: str) -> str:
        """Convert text to speakable form for screen readers."""
        stage = getattr(self.state.lesson, "stage", 0)
        natural_words = lesson_manager.get_stage_natural_words(stage)
        return speech_format.spell_text_for_typing_instruction(text, natural_words=natural_words)

    def run(self):
        # Draw first frame before speaking (helps with initialization)
        self.draw()
        pygame.display.flip()

        # Arm a delayed startup menu announcement so screen reader title
        # announcement can finish first.
        pygame.time.set_timer(self._startup_menu_event, 1800)
        self._startup_menu_armed = True

        while True:
            dt = self.clock.tick(60) / 1000.0  # Delta time in seconds
            self._refresh_auto_speech_backend()
            self.updates.poll_update_work()
            for event in pygame.event.get():
                try:
                    self.handle_event(event)
                except Exception as e:
                    error_logging.log_exception(e)
                    raise

            # Update game logic
            if self.state.mode == "GAME" and self.current_game:
                self.current_game.update(dt)

            self.draw()
            pygame.display.flip()

    def _refresh_auto_speech_backend(self):
        """Auto mode: keep backend in sync with screen reader runtime state."""
        now = time.time()
        if now - self._last_speech_backend_check < 1.0:
            return
        self._last_speech_backend_check = now

        if self.state.settings.speech_mode != "auto":
            return

        previous_backend = self.speech.backend
        if not self.speech.refresh_backend(self.state.settings.speech_mode):
            return

        self.state.backend_label = self._backend_label()

        if self.speech.backend == "tts":
            self.speech.say(
                "Screen reader not detected. Switched to text to speech.",
                priority=True,
                protect_seconds=1.5,
                interrupt=True,
            )
        elif self.speech.backend == "tolk" and previous_backend != "tolk":
            self.speech.say(
                "Screen reader detected. Switched to screen reader.",
                priority=True,
                protect_seconds=1.5,
                interrupt=True,
            )

    def handle_event(self, event):
        if self.state.mode == "UPDATING":
            if event.type == self._startup_menu_event:
                pygame.time.set_timer(self._startup_menu_event, 0)
                self._startup_menu_armed = False
            return
        if event.type == pygame.QUIT:
            self._quit_app()
        if event.type == pygame.VIDEORESIZE:
            self._resize_window(event.w, event.h)
            return
        if event.type == self._startup_menu_event:
            pygame.time.set_timer(self._startup_menu_event, 0)
            self._startup_menu_armed = False
            if self.state.mode == "MENU":
                self.say_menu(on_startup=True)
            return
        if event.type == pygame.KEYDOWN:
            if self._startup_menu_armed:
                pygame.time.set_timer(self._startup_menu_event, 0)
                self._startup_menu_armed = False
            mods = pygame.key.get_mods()
            if event.key == pygame.K_ESCAPE and self._handle_escape_shortcut():
                return
            if event.key != pygame.K_ESCAPE:
                self.escape_guard.reset()
                self._escape_remaining = 0
            if self.state.mode == "MENU":
                self.handle_menu_input(event, mods)
            elif self.state.mode == "KEYBOARD_EXPLORER":
                self.handle_keyboard_explorer_input(event, mods)
            elif self.state.mode == "LESSON_MENU":
                self.handle_lesson_menu_input(event)
            elif self.state.mode == "OPTIONS":
                self.handle_options_input(event)
            elif self.state.mode == "LESSON_INTRO":
                self.handle_lesson_intro_input(event, mods)
            elif self.state.mode == "TUTORIAL":
                self.handle_tutorial_input(event, mods)
            elif self.state.mode == "LESSON":
                self.handle_lesson_input(event, mods)
            elif self.state.mode == "TEST_SETUP":
                self.handle_test_setup_input(event)
            elif self.state.mode == "TEST":
                self.handle_test_input(event, mods)
            elif self.state.mode == "PRACTICE_SETUP":
                self.handle_practice_setup_input(event, mods)
            elif self.state.mode == "PRACTICE":
                self.handle_practice_input(event, mods)
            elif self.state.mode == "RESULTS":
                self.handle_results_input(event, mods)
            elif self.state.mode == "GAMES_MENU":
                self.handle_games_menu_input(event, mods)
            elif self.state.mode == "SHOP":
                self.handle_shop_input(event, mods)
            elif self.state.mode == "PET":
                self.handle_pet_input(event, mods)
            elif self.state.mode == "LEARN_SOUNDS_MENU":
                self.handle_learn_sounds_menu_input(event, mods)
            elif self.state.mode == "ABOUT":
                self.handle_about_input(event, mods)
            elif self.state.mode == "GAME":
                self.handle_game_input(event, mods)
            elif self.state.mode == "FREE_PRACTICE_READY":
                self.handle_free_practice_ready_input(event, mods)
            elif self.state.mode == "FREE_PRACTICE":
                self.handle_lesson_input(event, mods)  # Reuse lesson input handling

    def _escape_policy(self):
        """Return escape handling policy for current mode, or None."""
        mode = self.state.mode
        if mode == "KEYBOARD_EXPLORER":
            return {
                "context": "KEYBOARD_EXPLORER",
                "required_presses": 3,
                "action": "menu",
                "noun": "exit",
            }

        if mode == "PRACTICE":
            return {
                "context": "PRACTICE",
                "required_presses": 3,
                "action": "finish_practice",
                "noun": "finish",
            }

        active_modes = {
            "LESSON_INTRO",
            "TUTORIAL",
            "LESSON",
            "TEST",
            "FREE_PRACTICE",
            "FREE_PRACTICE_READY",
        }
        if mode in active_modes:
            return {
                "context": mode,
                "required_presses": 3,
                "action": "menu",
                "noun": "exit",
            }
        if mode == "GAME" and self.current_game:
            game_mode = getattr(self.current_game, "mode", "")
            if game_mode not in ("MENU", "RESULTS"):
                game_name = getattr(self.current_game, "NAME", "Game")
                return {
                    "context": f"{mode}:{game_name}:{game_mode}",
                    "required_presses": 3,
                    "action": "menu",
                    "noun": "exit",
                }
        return None

    def _handle_escape_shortcut(self) -> bool:
        """Handle configured Escape shortcuts; return True when consumed."""
        policy = self._escape_policy()
        if not policy:
            self.escape_guard.reset()
            self._escape_remaining = 0
            return False

        completed, remaining = self.escape_guard.register_escape(
            context=policy["context"],
            required_presses=policy["required_presses"],
        )
        if not completed:
            self._escape_remaining = remaining
            self._escape_noun = policy["noun"]
            self.speech.say(
                f"Escape. Press {remaining} more time{'s' if remaining != 1 else ''} to {policy['noun']}.",
                priority=True,
            )
            return True

        # Sequence complete — clear the visual counter.
        self._escape_remaining = 0
        self._escape_noun = ""

        if policy["action"] == "finish_practice":
            self.finish_practice()
            return True

        self.current_game = None
        self.state.mode = "MENU"
        self.speech.say("Exiting to main menu.", priority=True)
        self.say_menu()
        return True

    def _screen_size(self) -> tuple[int, int]:
        return self.screen.get_size()

    def _resize_window(self, width: int, height: int) -> None:
        min_width = max(800, app_config.SCREEN_W)
        min_height = max(600, app_config.SCREEN_H)
        self.screen = pygame.display.set_mode(
            (max(min_width, width), max(min_height, height)),
            pygame.RESIZABLE,
        )

    def _maximize_window(self) -> None:
        try:
            from pygame._sdl2.video import Window

            window = Window.from_display_module()
            if window is not None:
                window.maximize()
        except Exception:
            pass

    # ==================== MENU ====================
    def say_menu(self, on_startup: bool = False):
        """Announce the main menu."""
        if on_startup:
            item = self.main_menu.get_current_item()
            if item is not None:
                self.speech.say(
                    self.main_menu.get_item_text(item),
                    priority=False,
                    interrupt=False,
                )
            return
        self.main_menu.announce_menu()

    def handle_menu_input(self, event, mods):
        """Handle main menu input."""
        if event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
            self.say_menu()
        else:
            self.main_menu.handle_input(event, mods)

    # ==================== LESSON MENU ====================
    def show_lesson_menu(self):
        """Show lesson selection menu."""
        self.state.mode = "LESSON_MENU"
        self.lesson_menu.reset_index()
        self.lesson_menu.announce_menu()

    def handle_lesson_menu_input(self, event):
        """Handle lesson menu navigation."""
        self.lesson_menu.handle_input(event)

    # ==================== GAMES MENU ====================
    def show_games_menu(self):
        """Show games selection menu."""
        self.state.mode = "GAMES_MENU"
        self.games_menu.reset_index()
        self.games_menu.announce_menu()

    def handle_games_menu_input(self, event, mods):
        """Handle games menu navigation."""
        if event.key == pygame.K_h:
            game = self.games_menu.get_current_item()
            if game:
                self.speech.say(game.HOTKEYS, priority=True)
        else:
            self.games_menu.handle_input(event, mods)

    # ==================== LEARN SOUNDS MENU ====================
    def show_learn_sounds_menu(self):
        """Show learn sounds menu."""
        learn_sounds_mode.show_learn_sounds_menu(self)

    def handle_learn_sounds_menu_input(self, event, mods):
        """Handle learn sounds menu navigation."""
        learn_sounds_mode.handle_learn_sounds_menu_input(self, event, mods)

    def _play_sound_demo(self, sound_item):
        """Play a sound demonstration."""
        sound_demo.play_sound_demo(self.audio, sound_item["sound"])

    # ==================== ABOUT MENU ====================
    def show_about_menu(self):
        self.state.mode = "ABOUT"
        self.about_menu.reset_index()
        self.about_menu.announce_menu()

    def handle_about_input(self, event, mods):
        self.about_menu.handle_input(event, mods)

    def start_game(self, game_index):
        """Start a game."""
        self.current_game = self.games[game_index]
        self.state.mode = "GAME"
        self.game_time = time.time()
        self.current_game.start()

    def handle_game_input(self, event, mods):
        """Handle game input."""
        if self.current_game:
            result = self.current_game.handle_input(event, mods)
            if result == "GAMES_MENU":
                self.current_game = None
                self.show_games_menu()

    # ==================== OPTIONS MENU ====================
    def show_options_menu(self):
        """Show options menu."""
        self.state.mode = "OPTIONS"
        self.options_menu.reset_index()
        self.options_menu.announce_menu()

    def handle_options_input(self, event):
        """Handle options menu navigation and changes."""
        self.options_menu.handle_input(event)

    def apply_speech_mode(self):
        """Apply the selected speech mode and switch backends accordingly."""
        self.speech.apply_mode(self.state.settings.speech_mode)
        self.state.backend_label = self._backend_label()

    def apply_typing_sound_intensity(self):
        """Apply typing sound intensity from settings to audio manager."""
        self.audio.set_typing_sound_intensity(self.state.settings.typing_sound_intensity)

    def apply_tts_settings(self):
        """Apply TTS settings from state to speech engine."""
        self.speech.apply_tts_settings(
            rate=self.state.settings.tts_rate,
            volume=self.state.settings.tts_volume,
            voice_id=self.state.settings.tts_voice
        )

    def apply_visual_theme(self):
        """Apply the selected visual theme."""
        global BG, FG, ACCENT, HILITE
        theme = self.state.settings.visual_theme

        BG, FG, ACCENT, HILITE = theme_manager.get_theme_colors(theme)

    def _rebuild_fonts(self):
        """Recreate fonts at the user-selected (or DPI-auto) scale factor.

        Called once at startup (after load_progress) and whenever the
        Font Size option is changed.  Updates self.*_font and pushes the
        new font objects into every game object so they don't keep stale
        references.
        """
        self.title_font, self.text_font, self.small_font = font_manager.build_fonts(
            self.state.settings.font_scale
        )
        # Propagate to game objects that cache fonts at construction time.
        for game in self.games:
            game.title_font = self.title_font
            game.text_font = self.text_font
            game.small_font = self.small_font

    # ==================== TUTORIAL (IMPROVED) ====================
    def start_tutorial(self):
        self.state.mode = "TUTORIAL"
        t = self.state.tutorial
        t.phase = 1
        t.sequence = []
        t.counts_done = Counter()
        t.target_counts = {}
        t.key_errors = Counter()
        t.total_attempts = 0
        t.total_correct = 0
        t.phase_attempts = 0
        t.phase_correct = 0
        t.phase_mistakes = 0
        t.adaptive_mode = "normal"
        t.in_intro = False
        t.intro_items = []
        t.intro_index = 0
        t.guidance_message = ""
        t.hint_message = ""

        self._enter_tutorial_intro(1)

    def _start_tutorial_phase(self, phase: int):
        """Initialize a tutorial phase using adaptive pacing."""
        t = self.state.tutorial
        t.phase = phase
        t.phase_attempts = 0
        t.phase_correct = 0
        t.phase_mistakes = 0
        t.sequence, t.target_counts = tutorial_data.build_phase_sequence(
            phase=phase,
            mode=t.adaptive_mode,
            key_errors=t.key_errors,
        )
        random.shuffle(t.sequence)
        t.index = 0
        t.in_intro = False
        t.intro_items = []
        t.intro_index = 0

    def _finish_tutorial_phase(self):
        """Record phase performance and update adaptive mode for the next phase."""
        t = self.state.tutorial
        if t.phase_attempts <= 0:
            accuracy = 1.0
        else:
            accuracy = t.phase_correct / t.phase_attempts
        t.adaptive_mode = tutorial_data.next_mode_from_performance(accuracy, t.phase_mistakes)

    def _enter_tutorial_intro(self, phase: int):
        """Enter phase intro where user can review key locations before starting."""
        t = self.state.tutorial
        t.phase = phase
        t.in_intro = True
        t.intro_items = tutorial_data.get_intro_items_for_phase(phase)
        t.intro_index = 0

        phase_names = {
            1: "Space bar",
            2: "Arrow keys",
            3: "Enter",
            4: "Control",
            5: "Mixed review",
        }
        phase_title = phase_names.get(phase, "Next keys")
        if t.intro_items:
            key_name, desc = t.intro_items[t.intro_index]
            key_friendly = tutorial_data.FRIENDLY.get(key_name, key_name)
            self.speech.say(
                f"{phase_title} tutorial. Review the key location before practice starts. "
                f"Item {t.intro_index + 1} of {len(t.intro_items)}. {key_friendly}. {desc} "
                f"Use Up and Down arrows to review each instruction. Press Enter or Space when you are ready to start practice.",
                priority=True,
                protect_seconds=4.0,
            )

    def load_tutorial_prompt(self):
        t = self.state.tutorial

        if t.index >= len(t.sequence):
            self._finish_tutorial_phase()
            if t.phase == 1:
                self._enter_tutorial_intro(2)
                return
            elif t.phase == 2:
                self._enter_tutorial_intro(3)
                return
            elif t.phase == 3:
                self._enter_tutorial_intro(4)
                return
            elif t.phase == 4:
                self._enter_tutorial_intro(5)
                return
            else:
                # Tutorial complete - play victory sound and show results
                self.audio.play_victory()

                # Create results summary
                t = self.state.tutorial
                results_text = results_formatter.ResultsFormatter.format_tutorial_results(
                    counts_done=t.counts_done,
                    friendly_names=tutorial_data.FRIENDLY
                )

                # Show results dialog (blocks until OK is pressed)
                self.show_results_dialog(results_text)

                # Return to menu after dialog closes
                self.state.mode = "MENU"
                self.say_menu()
                return

        name, key = t.sequence[t.index]
        t.required_name = name
        t.required_key = key
        self.speech.say(f"Press {tutorial_data.FRIENDLY[name]}", priority=True, protect_seconds=2.0)

    def handle_tutorial_input(self, event, mods):
        tutorial_mode.handle_tutorial_input(self, event, mods)

    # ==================== KEYBOARD EXPLORER ====================
    def start_keyboard_explorer(self):
        """Start keyboard explorer mode - pressure-free key exploration."""
        self.state.mode = "KEYBOARD_EXPLORER"
        self.keyboard_explorer_first_key = True  # Flag to skip the menu selection key
        self.speech.say(
            "Keyboard Explorer. Press any key to hear its name and location. No timing, no scoring, no pressure. Press Escape three times to return to the menu.",
            priority=True, protect_seconds=3.0
        )

    def handle_keyboard_explorer_input(self, event, mods):
        """Handle input in keyboard explorer mode."""
        keyboard_explorer.handle_keyboard_explorer_input(self, event, mods)

    # ==================== LESSON INTRO ====================
    def start_lesson(self, lesson_num=None):
        """Begin lesson - show intro screen first if lesson has key locations."""
        # Use provided lesson number or current lesson from settings
        if lesson_num is None:
            lesson_num = self.state.settings.current_lesson

        stage = max(0, min(lesson_num, len(lesson_manager.STAGE_LETTERS) - 1))
        self.state.settings.current_lesson = stage

        # Check if this lesson has an intro (key location descriptions)
        if stage in lesson_manager.KEY_LOCATIONS:
            self.show_lesson_intro(stage)
        else:
            self.begin_lesson_practice(stage)

    def show_lesson_intro(self, lesson_num):
        """Show lesson intro screen with key location and finding instructions."""
        lesson_intro_mode.show_lesson_intro(self, lesson_num)

    def repeat_lesson_intro(self):
        """Repeat the lesson intro information."""
        lesson_intro_mode.repeat_lesson_intro(self)

    def handle_lesson_intro_input(self, event, mods):
        """Handle key presses during lesson intro - looking for new keys."""
        lesson_intro_mode.handle_lesson_intro_input(self, event, mods)

    # ==================== LESSON (ADAPTIVE) ====================
    def begin_lesson_practice(self, lesson_num):
        """Begin the actual lesson practice after intro."""
        self.state.mode = "LESSON"
        self.state.results_action = ""

        stage = max(0, min(lesson_num, len(lesson_manager.STAGE_LETTERS) - 1))
        self.state.lesson = state_manager.LessonState(stage=stage)
        self.state.settings.current_lesson = stage

        # Use words from the start - we have content for all lessons now
        self.state.lesson.use_words = True

        self.build_lesson_batch()

        lesson = self.state.lesson
        target = lesson.batch_words[lesson.index]

        # Check if this is a special key lesson
        if lesson.batch_instructions:
            # Special key lesson - use the instruction
            instruction = lesson.batch_instructions[lesson.index]
            self.speech.say(
                f"Lesson practice. Control Space repeats. Escape returns to the main menu. {instruction}",
                priority=True,
                protect_seconds=4.5,
            )
        else:
            # Regular lesson - build character-by-character description for first prompt
            speakable = self._make_speakable(target)

            self.speech.say(
                f"Lesson practice. Control Space repeats. Escape returns to the main menu. Type {speakable}",
                priority=True,
                protect_seconds=4.5,
            )

    def build_lesson_batch(self):
        lesson_mode.build_lesson_batch(self)

    def lesson_prompt(self):
        lesson_mode.lesson_prompt(self)

    def next_lesson_item(self):
        lesson_mode.next_lesson_item(self)

    def extend_lesson_practice(self):
        lesson_mode.extend_lesson_practice(self)

    def check_and_inject_adaptive_content(self):
        lesson_mode.check_and_inject_adaptive_content(self)

    def calculate_lesson_stars(self, lesson_num: int, accuracy: float, wpm: float) -> int:
        return lesson_mode.calculate_lesson_stars(lesson_num, accuracy, wpm)

    def evaluate_lesson_performance(self):
        """Delegate lesson-completion handling to lesson_mode."""
        lesson_mode.evaluate_lesson_performance(self)
        return

    def current_word(self):
        return self.state.lesson.batch_words[self.state.lesson.index]

    def handle_lesson_input(self, event, mods):
        lesson_mode.handle_lesson_input(self, event, mods)

    def process_lesson_typing(self, event):
        lesson_mode.process_lesson_typing(self, event)

    def provide_key_guidance(self, pressed, target_text, matched_prefix=""):
        """Provide short, directional guidance based on spatial position."""
        lesson = self.state.lesson

        if not target_text:
            target_text = ""
        remaining_text = target_text[len(matched_prefix):] if matched_prefix else target_text
        target_key = remaining_text[0] if remaining_text else ""

        # Get directional hint based on key positions
        hint = lesson_manager.get_directional_hint(pressed, target_key) if target_key else "Try again."
        speakable_target = self._make_speakable(remaining_text)

        # Store for visual display - short and helpful
        lesson.guidance_message = f"Type {speakable_target}"
        lesson.hint_message = hint

        # Say target and directional hint
        self.speech.say(f"Type {speakable_target}, {hint}", priority=True, protect_seconds=2.0)

    # ==================== SPEED TEST ====================
    def start_test(self):
        """Start speed test - ask for duration first."""
        test_modes.start_test(self)

    def handle_test_setup_input(self, event):
        """Handle duration input for speed test - user types any number."""
        test_modes.handle_test_setup_input(self, event)

    def begin_test_typing(self):
        """Start the actual typing test after duration is selected."""
        test_modes.begin_test_typing(self)

    def load_next_sentence(self):
        test_modes.load_next_sentence(self)

    def finish_test(self):
        test_modes.finish_test(self)

    def handle_test_input(self, event, mods):
        test_modes.handle_test_input(self, event, mods)

    def process_test_typing(self, event):
        test_modes.process_test_typing(self, event)

    def speak_test_remaining(self):
        test_modes.speak_test_remaining(self)

    # ==================== SENTENCE PRACTICE ====================
    def start_practice(self):
        """Open sentence practice setup."""
        test_modes.start_practice(self)

    def handle_practice_setup_input(self, event, mods):
        """Handle sentence practice setup mode input."""
        test_modes.handle_practice_setup_input(self, event, mods)

    def load_next_practice_sentence(self):
        """Load next sentence for practice mode."""
        test_modes.load_next_practice_sentence(self)

    def finish_practice(self):
        """Finish sentence practice and show results."""
        test_modes.finish_practice(self)

    def handle_practice_input(self, event, mods):
        """Handle input during sentence practice mode."""
        test_modes.handle_practice_input(self, event, mods)

    def process_practice_typing(self, event):
        """Process typing for sentence practice - same as speed test."""
        test_modes.process_practice_typing(self, event)

    def speak_practice_remaining(self):
        """Speak remaining text for sentence practice."""
        test_modes.speak_practice_remaining(self)

    # ==================== RESULTS ====================
    def handle_results_input(self, event, mods):
        if event.key == pygame.K_ESCAPE:
            self.state.mode = "MENU"
            self.state.results_action = ""
            self.state.free_practice.selected_keys = set()
            self.say_menu()
        elif event.key == pygame.K_UP:
            if self.state.results_options:
                self.state.results_index = menu_handler.navigate_up(
                    self.state.results_index,
                    len(self.state.results_options),
                )
                self.speech.say(self.state.results_options[self.state.results_index], priority=True)
        elif event.key == pygame.K_DOWN:
            if self.state.results_options:
                self.state.results_index = menu_handler.navigate_down(
                    self.state.results_index,
                    len(self.state.results_options),
                )
                self.speech.say(self.state.results_options[self.state.results_index], priority=True)
        elif event.key == pygame.K_HOME:
            if self.state.results_options:
                self.state.results_index = menu_handler.navigate_first(len(self.state.results_options))
                self.speech.say(self.state.results_options[self.state.results_index], priority=True)
        elif event.key == pygame.K_END:
            if self.state.results_options:
                self.state.results_index = menu_handler.navigate_last(len(self.state.results_options))
                self.speech.say(self.state.results_options[self.state.results_index], priority=True)
        elif event.key == pygame.K_SPACE:
            self._activate_results_choice()
        elif event.key == pygame.K_RETURN:
            self._activate_results_choice()

    def _activate_results_choice(self) -> None:
        """Execute the currently highlighted results menu option."""
        if not self.state.results_options:
            return

        choice = self.state.results_options[self.state.results_index]

        if choice.startswith("Start next lesson"):
            self.save_progress()
            self.start_lesson(self.state.results_next_lesson)
        elif choice.startswith("Try "):
            self.state.lesson.review_mode = False
            self.save_progress()
            retry = getattr(self.state, "results_retry_lesson", self.state.results_next_lesson)
            self.begin_lesson_practice(retry)
        elif choice.startswith("Start free practice again"):
            self.start_free_practice()
        elif choice.startswith("Return to main menu"):
            self.state.free_practice.selected_keys = set()
            self._return_to_main_menu_and_save()
        elif choice.startswith("Start speed test again"):
            self.start_test()
        elif choice.startswith("Start sentence practice again"):
            self.start_practice()
        else:
            self._return_to_main_menu_and_save()

    # ==================== DRAWING ====================
    def trigger_flash(self, color: tuple, duration: float = 0.12) -> None:
        """Schedule a brief color overlay for visual keystroke feedback.

        The overlay mirrors success/error tones and fades quickly enough to
        be triggered on every keystroke.
        """
        self._flash.trigger(color, duration)

    def draw(self):
        self.screen.fill(BG)
        if self.state.mode == "MENU":
            self.draw_menu()
        elif self.state.mode == "KEYBOARD_EXPLORER":
            self.draw_keyboard_explorer()
        elif self.state.mode == "LESSON_MENU":
            self.draw_lesson_menu()
        elif self.state.mode == "OPTIONS":
            self.draw_options()
        elif self.state.mode == "LESSON_INTRO":
            self.draw_lesson_intro()
        elif self.state.mode == "TUTORIAL":
            self.draw_tutorial()
        elif self.state.mode == "LESSON":
            self.draw_lesson()
        elif self.state.mode == "TEST_SETUP":
            self.draw_test_setup()
        elif self.state.mode == "TEST":
            self.draw_test()
        elif self.state.mode == "PRACTICE_SETUP":
            self.draw_practice_setup()
        elif self.state.mode == "PRACTICE":
            self.draw_practice()
        elif self.state.mode == "RESULTS":
            self.draw_results()
        elif self.state.mode == "GAMES_MENU":
            self.draw_games_menu()
        elif self.state.mode == "SHOP":
            self.draw_shop()
        elif self.state.mode == "PET":
            self.draw_pet()
        elif self.state.mode == "LEARN_SOUNDS_MENU":
            self.draw_learn_sounds_menu()
        elif self.state.mode == "ABOUT":
            self.draw_about()
        elif self.state.mode == "UPDATING":
            self.draw_updating()
        elif self.state.mode == "GAME":
            self.draw_game()
        elif self.state.mode == "FREE_PRACTICE_READY":
            self.draw_free_practice_ready()
        elif self.state.mode == "FREE_PRACTICE":
            self.draw_lesson()  # Reuse lesson drawing

        screen_w, screen_h = self._screen_size()

        # Escape press counter — shown while user is mid-sequence (visual complement to speech).
        if self._escape_remaining > 0:
            presses = self._escape_remaining
            noun = self._escape_noun
            msg = (
                f"Escape: {presses} more press{'es' if presses != 1 else ''} to {noun}"
            )
            esc_surf, _ = self.small_font.render(msg, ACCENT)
            self.screen.blit(esc_surf, (screen_w // 2 - esc_surf.get_width() // 2, 6))

        # Render keystroke flash overlay last so it appears above all content.
        if self._flash.is_active():
            from ui.a11y import draw_keystroke_flash
            draw_keystroke_flash(self.screen, self._flash.color, self._flash.current_alpha(), screen_w, screen_h)

    def draw_menu(self):
        screen_w, screen_h = self._screen_size()
        streak_text = ""
        if self.state.settings.current_streak > 0:
            streak_text = self.get_streak_announcement()

        draw_main_menu(
            screen=self.screen,
            title_font=self.title_font,
            small_font=self.small_font,
            menu_items=self.state.menu_items,
            current_index=self.main_menu.current_index,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            unlocked_count=len(self.state.settings.unlocked_lessons),
            total_count=len(lesson_manager.STAGE_LETTERS),
            streak_text=streak_text,
        )

    def draw_lesson_menu(self):
        """Draw the lesson selection menu."""
        screen_w, screen_h = self._screen_size()
        draw_lesson_menu(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            unlocked_lessons=sorted(list(self.state.settings.unlocked_lessons)),
            lesson_names=lesson_manager.LESSON_NAMES,
            current_index=self.lesson_menu.current_index,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
        )

    def draw_games_menu(self):
        """Draw the games selection menu."""
        screen_w, screen_h = self._screen_size()
        draw_games_menu(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            games=self.games,
            current_index=self.games_menu.current_index,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
        )

    def draw_learn_sounds_menu(self):
        screen_w, screen_h = self._screen_size()
        draw_learn_sounds_menu(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            sound_items=self.sound_items,
            current_index=self.sounds_menu.current_index,
        )

    def draw_about(self):
        screen_w, screen_h = self._screen_size()
        title_surf, _ = self.title_font.render("About", HILITE)
        self.screen.blit(title_surf, (screen_w // 2 - title_surf.get_width() // 2, 40))

        version_surf, _ = self.small_font.render(f"KeyQuest {__version__}", ACCENT)
        self.screen.blit(version_surf, (screen_w // 2 - version_surf.get_width() // 2, 84))

        subtitle = "Web Friendly Help LLC"
        subtitle_surf, _ = self.text_font.render(subtitle, FG)
        self.screen.blit(subtitle_surf, (screen_w // 2 - subtitle_surf.get_width() // 2, 116))

        y = 180
        for idx, item in enumerate(self.about_items):
            selected = idx == self.about_menu.current_index
            prefix = "> " if selected else "  "
            text = f"{prefix}{item['display']}"
            color = HILITE if selected else FG
            surf, _ = self.text_font.render(text, color)
            rect = surf.get_rect(topleft=(80, y))
            if selected:
                from ui.a11y import draw_action_emphasis, draw_active_panel, draw_focus_frame
                draw_active_panel(self.screen, rect, ACCENT, FG)
                draw_focus_frame(self.screen, rect, HILITE, ACCENT)
                draw_action_emphasis(self.screen, rect, HILITE)
            self.screen.blit(surf, rect)
            y += 52

        from ui.a11y import draw_controls_hint
        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Enter select; Esc back",
            screen_w=screen_w,
            y=screen_h - 50,
            accent=ACCENT,
        )

    def draw_updating(self):
        screen_w, screen_h = self._screen_size()
        draw_updating_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            wrap_text=self._wrap_text,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            status_text=self.updates.update_status,
            downloaded_bytes=self.updates.update_downloaded_bytes,
            total_bytes=self.updates.update_total_bytes,
        )

    def draw_shop(self):
        """Draw the shop interface."""
        screen_w, screen_h = self._screen_size()
        draw_shop(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            settings=self.state.settings,
            shop_title=getattr(self, "shop_title", "Shop"),
            shop_view=self.shop_view,
            shop_categories=self.shop_categories,
            shop_category_index=self.shop_category_index,
            shop_item_index=self.shop_item_index,
        )

    def draw_pet(self):
        """Draw the pet interface."""
        pet_mode.ensure_pet_ui_state(self)
        screen_w, screen_h = self._screen_size()
        draw_pet(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            settings=self.state.settings,
            pet_view=self.pet_view,
            pet_types=self.pet_types,
            pet_choose_index=self.pet_choose_index,
            pet_options=self.pet_options,
            pet_menu_index=self.pet_menu_index,
        )

    def draw_game(self):
        """Draw the active game."""
        if self.current_game:
            self.current_game.draw()

    def draw_options(self):
        """Draw the options menu."""
        screen_w, screen_h = self._screen_size()
        options = [opt["get_text"]() for opt in self.options_menu.options]
        draw_options(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            options=options,
            current_index=self.options_menu.current_index,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
        )

    def draw_lesson_intro(self):
        screen_w, screen_h = self._screen_size()
        intro = self.state.lesson_intro
        lesson_num = intro.lesson_num

        lesson_name = (
            lesson_manager.LESSON_NAMES[lesson_num]
            if lesson_num < len(lesson_manager.LESSON_NAMES)
            else f"Lesson {lesson_num}"
        )

        info = lesson_manager.KEY_LOCATIONS.get(lesson_num)
        current_intro_heading = ""
        current_intro_text = ""
        intro_count = 0
        intro_index = 0
        if intro.intro_items:
            intro_count = len(intro.intro_items)
            intro_index = intro.intro_index
            current_intro_heading, current_intro_text = intro.intro_items[intro.intro_index]

        needed_keys = sorted(list(intro.required_keys - intro.keys_found))
        keys_to_find_display = phonetics.format_needed_keys_for_display(needed_keys) if needed_keys else ""
        keys_found_display = ", ".join(sorted([k.upper() for k in intro.keys_found])) if intro.keys_found else ""

        draw_lesson_intro_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            lesson_num=lesson_num,
            lesson_name=lesson_name,
            lesson_info=info,
            current_intro_heading=current_intro_heading,
            current_intro_text=current_intro_text,
            intro_index=intro_index,
            intro_count=intro_count,
            keys_to_find_display=keys_to_find_display,
            keys_found_display=keys_found_display,
        )

    def _wrap_text(self, text, max_width):
        return wrap_text(self.small_font, text, max_width, FG)

    def draw_keyboard_explorer(self):
        screen_w, screen_h = self._screen_size()
        draw_keyboard_explorer_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
        )

    def draw_tutorial(self):
        screen_w, screen_h = self._screen_size()
        draw_tutorial_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            wrap_text=self._wrap_text,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            focus_assist=self.state.settings.focus_assist,
            tutorial_state=self.state.tutorial,
            tutorial_data=tutorial_data,
        )

    def draw_lesson(self):
        screen_w, _screen_h = self._screen_size()
        lesson = self.state.lesson
        draw_lesson_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            wrap_text=self._wrap_text,
            lesson_state=lesson,
            target=self.current_word(),
            typed=lesson.typed,
            focus_assist=self.state.settings.focus_assist,
        )

    def draw_free_practice_ready(self):
        screen_w, screen_h = self._screen_size()
        draw_free_practice_ready_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            unlocked_lessons=self.state.free_practice.available_lessons,
            lesson_names=lesson_manager.LESSON_NAMES,
            current_index=self.state.free_practice.lesson_index,
            available_keys_count=len(self.state.free_practice.available_keys),
        )

    def draw_test_setup(self):
        """Draw the test duration selection screen."""
        screen_w, screen_h = self._screen_size()
        draw_test_setup_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            duration_input=self.state.test.duration_input,
            view=self.test_setup_view,
            topic_options=self.test_setup_topic_options,
            topic_index=self.test_setup_topic_index,
            focus_assist=self.state.settings.focus_assist,
        )

    def draw_practice_setup(self):
        """Draw sentence practice setup screen."""
        screen_w, screen_h = self._screen_size()
        draw_practice_setup_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            focus_assist=self.state.settings.focus_assist,
            view=self.practice_setup_view,
            menu_options=self.practice_setup_options,
            menu_index=self.practice_setup_index,
            topic_options=self.practice_topic_options,
            topic_index=self.practice_topic_index,
        )

    def draw_test(self):
        screen_w, screen_h = self._screen_size()
        t = self.state.test
        if t.running and t.start_time > 0:
            elapsed = time.time() - t.start_time
            remaining = max(0, t.duration_seconds - elapsed)

            # Auto-end test when time expires
            if elapsed >= t.duration_seconds:
                self.finish_test()
                return
        else:
            remaining = t.duration_seconds

        draw_test_screen(
            screen=self.screen,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            current_text=t.current,
            typed_text=t.typed,
            remaining_seconds=int(remaining),
            focus_assist=self.state.settings.focus_assist,
        )

    def draw_practice(self):
        """Draw sentence practice screen."""
        screen_w, screen_h = self._screen_size()
        t = self.state.test

        elapsed_seconds = (time.time() - t.start_time) if t.start_time > 0 else 0.0
        draw_practice_screen(
            screen=self.screen,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            current_text=t.current,
            typed_text=t.typed,
            elapsed_seconds=elapsed_seconds,
            sentences_completed=t.sentences_completed,
            focus_assist=self.state.settings.focus_assist,
        )

    def draw_results(self):
        screen_w, screen_h = self._screen_size()
        draw_results_screen(
            screen=self.screen,
            title_font=self.title_font,
            text_font=self.text_font,
            small_font=self.small_font,
            screen_w=screen_w,
            screen_h=screen_h,
            fg=FG,
            accent=ACCENT,
            hilite=HILITE,
            title=self.state.results_title or "Results",
            instructions=self.state.results_instructions,
            results_text=self.state.results_text,
            options=self.state.results_options,
            current_index=self.state.results_index,
            focus_assist=self.state.settings.focus_assist,
        )


def main():
    print("KeyQuest main() starting...")
    app = None
    try:
        print("Creating KeyQuestApp...")
        app = KeyQuestApp()
        print("Starting app.run()...")
        app.run()
        print("app.run() completed")
    except Exception as e:
        print(f"ERROR in main(): {e}")
        import traceback
        traceback.print_exc()
        error_logging.log_exception(e)
        summary = f"{type(e).__name__}: {e}"
        error_logging.log_message("Unexpected KeyQuest Error", summary)
        _offer_general_error_log_copy()
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")


if __name__ == "__main__":
    main()
