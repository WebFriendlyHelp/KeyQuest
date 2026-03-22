"""Base game class template for all KeyQuest games.

All games should inherit from this class to ensure consistent menu structure,
keyboard navigation, and accessibility features.
"""

from modules import dialog_manager
from ui.a11y import draw_controls_hint, draw_focus_frame
from ui.layout import center_x, get_footer_y, get_screen_size


class BaseGame:
    """Base class for all KeyQuest typing games.

    All games must implement:
    - NAME: Game name
    - DESCRIPTION: Short description
    - INSTRUCTIONS: How to play instructions (detailed)
    - HOTKEYS: Summary of keyboard controls

    And override these methods:
    - start_playing(): Initialize and start the actual game
    - handle_game_input(event, mods): Handle input during gameplay
    - update_game(dt): Update game logic each frame
    - draw_game(): Draw the game screen
    """

    # Game metadata (must be set by subclasses)
    NAME = "Game Name"
    DESCRIPTION = "Short game description"
    INSTRUCTIONS = "Detailed instructions"
    HOTKEYS = "Key summary"

    def __init__(
        self,
        screen,
        fonts,
        speech,
        play_sound_func,
        show_info_dialog_func,
        session_complete_callback=None,
    ):
        """Initialize base game components.

        Args:
            screen: Pygame display surface
            fonts: Dict with 'title_font', 'text_font', 'small_font'
            speech: Speech object for announcements
            play_sound_func: Function to play sound waves
            show_info_dialog_func: Function to show accessible info dialogs
        """
        self.screen = screen
        self.title_font = fonts['title_font']
        self.text_font = fonts['text_font']
        self.small_font = fonts['small_font']
        self.speech = speech
        self.play_sound = play_sound_func
        self.show_info_dialog = show_info_dialog_func  # For backwards compatibility
        self.on_session_complete = session_complete_callback

        # Universal dialog system (centralized)
        self.dialog_manager = dialog_manager

        # Menu state (common to all games)
        self.mode = "MENU"  # "MENU", "PLAYING"
        self.menu_items = ["Play Game", "Game Info", "Keyboard Controls", "Back to Games"]
        self.menu_index = 0

        # Colors (can be overridden by subclasses)
        self.BG = (0, 0, 0)
        self.FG = (255, 255, 255)
        self.ACCENT = (255, 200, 0)
        self.DANGER = (255, 50, 50)
        self.GOOD = (50, 255, 100)

    # ========== Menu Management (Implemented) ==========

    def start(self):
        """Show the game menu (called when game is selected)."""
        self.mode = "MENU"
        self.menu_index = 0
        self.say_game_menu()

    def say_game_menu(self):
        """Announce the game menu."""
        msg = f"{self.NAME} menu. {self.menu_items[self.menu_index]}. Use Up and Down arrows to navigate. Press Enter or Space to select. Press Escape to return to games menu."
        self.speech.say(msg, priority=True, protect_seconds=3.0)

    def handle_input(self, event, mods):
        """Route input to appropriate handler based on mode."""
        if self.mode == "MENU":
            return self.handle_menu_input(event, mods)
        elif self.mode == "PLAYING":
            return self.handle_game_input(event, mods)
        return None

    def handle_menu_input(self, event, mods):
        """Handle input in the game menu."""
        import pygame

        if event.key == pygame.K_ESCAPE:
            return "GAMES_MENU"
        elif event.key == pygame.K_SPACE and (mods & pygame.KMOD_CTRL):
            self.say_game_menu()
        elif event.key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % len(self.menu_items)
            self.speech.say(self.menu_items[self.menu_index])
        elif event.key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % len(self.menu_items)
            self.speech.say(self.menu_items[self.menu_index])
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = self.menu_items[self.menu_index]
            if choice == "Play Game":
                self.start_playing()
            elif choice == "Game Info":
                self.show_game_info()
            elif choice == "Keyboard Controls":
                self.show_controls()
            elif choice == "Back to Games":
                return "GAMES_MENU"
        return None

    def show_game_info(self):
        """Show combined game info (description + how to play) in accessible dialog.

        Override this method in your game to provide formatted info.
        Default implementation shows DESCRIPTION and INSTRUCTIONS in a single dialog.
        """
        content = f"""GAME INFO

{self.DESCRIPTION}

HOW TO PLAY

{self.INSTRUCTIONS}
"""
        self.show_info_dialog(f"{self.NAME} - Game Info", content)

    def show_controls(self):
        """Show keyboard controls screen in accessible dialog.

        Override this method in your game to provide formatted controls.
        Default implementation shows HOTKEYS in a dialog.
        """
        content = f"""KEYBOARD CONTROLS

{self.HOTKEYS}
"""
        self.show_info_dialog(f"{self.NAME} - Keyboard Controls", content)

    def show_game_results(self, results_content, session_stats=None):
        """Show game results/final score in an accessible dialog.

        This should be called when the game ends to show the player their
        final score, statistics, achievements, etc.

        Args:
            results_content: Formatted results text (preserve spacing/alignment)
            session_stats: Optional dict of gameplay metrics for app-wide progress systems

        Example:
            results = f\"\"\"GAME OVER

Final Score: {self.score}
High Score: {self.high_score}
Max Combo: {self.max_combo}

Great job!
\"\"\"
            self.show_game_results(results)
        """
        dialog_manager.show_results_dialog(
            f"{self.NAME} - Results",
            results_content,
            close_on_enter=False,
            close_on_escape=True,
            close_on_space=False,
        )
        if self.on_session_complete:
            self.on_session_complete(self, session_stats or {})

    # ========== Drawing (Implemented) ==========

    def draw(self):
        """Draw the appropriate screen based on mode."""
        self.screen.fill(self.BG)

        if self.mode == "MENU":
            self.draw_menu()
        elif self.mode == "PLAYING":
            self.draw_game()

    def _screen_size(self):
        """Return the current screen size, falling back to the legacy layout."""
        return get_screen_size(self.screen)

    def draw_menu(self):
        """Draw the game menu."""
        screen_w, screen_h = self._screen_size()
        # Title
        title_surf, _ = self.title_font.render(self.NAME, self.ACCENT)
        self.screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 80))

        # Menu items
        y = 200
        for idx, item in enumerate(self.menu_items):
            selected = idx == self.menu_index
            color = self.GOOD if selected else self.FG
            item_text = f"> {item}" if selected else f"  {item}"
            item_surf, _ = self.text_font.render(item_text, color)
            item_rect = item_surf.get_rect(topleft=(center_x(screen_w, item_surf.get_width()), y))
            self.screen.blit(item_surf, item_rect)
            if selected:
                draw_focus_frame(self.screen, item_rect, self.GOOD, self.ACCENT)
            y += 50

        # Controls hint
        draw_controls_hint(
            screen=self.screen,
            small_font=self.small_font,
            text="Up/Down navigate; Enter/Space select; Esc back",
            screen_w=screen_w,
            y=get_footer_y(screen_h),
            accent=self.FG,
        )

    # ========== Methods to Override ==========

    def start_playing(self):
        """Initialize and start the game. MUST BE IMPLEMENTED BY SUBCLASS."""
        raise NotImplementedError("Subclass must implement start_playing()")

    def handle_game_input(self, event, mods):
        """Handle input during gameplay. MUST BE IMPLEMENTED BY SUBCLASS.

        Should return None to continue playing, or "GAMES_MENU" to exit.
        Typically handles Escape to return to game menu.
        """
        raise NotImplementedError("Subclass must implement handle_game_input()")

    def update(self, dt):
        """Update game logic. SHOULD BE IMPLEMENTED BY SUBCLASS.

        Args:
            dt: Delta time in seconds since last frame
        """
        pass  # Optional - not all games need update logic

    def draw_game(self):
        """Draw the game screen. MUST BE IMPLEMENTED BY SUBCLASS."""
        raise NotImplementedError("Subclass must implement draw_game()")
