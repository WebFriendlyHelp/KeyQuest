"""Keyboard Explorer module for KeyQuest.

Provides detailed descriptions of keyboard keys for pressure-free exploration.
"""

import pygame

from modules import phonetics

# Comprehensive key descriptions with location and finger placement information
KEY_DESCRIPTIONS = {
    # Letter keys - Home row
    'a': "Letter A. Home row, left side. Left pinky finger. First key in the home row letter section.",
    's': "Letter S. Home row. Left ring finger. One key to the right of A.",
    'd': "Letter D. Home row. Left middle finger. Between S and F.",
    'f': "Letter F. Home row. Left index finger. It has a small bump you can feel. If your hand is lined up on F, your left pinky should land on A.",
    'j': "Letter J. Home row. Right index finger. It has a small bump you can feel. Use that bump to confirm your right hand is on home row.",
    'k': "Letter K. Home row. Right middle finger.",
    'l': "Letter L. Home row. Right ring finger.",
    ';': "Semicolon. Home row. Right pinky finger. Last key of the home row.",
    'g': "Letter G. Home row, center-left. Left index finger reaches right from F.",
    'h': "Letter H. Home row, center-right. Right index finger reaches left from J.",

    # Letter keys - Top row
    'q': "Letter Q. Top letter row, one row above the home row. Left pinky finger. First key in the top letter row.",
    'w': "Letter W. Top letter row, one row above the home row. Left ring finger. Above S.",
    'e': "Letter E. Top letter row, one row above the home row. Left middle finger. Above D.",
    'r': "Letter R. Top letter row, one row above the home row. Left index finger. Above F.",
    't': "Letter T. Top letter row, one row above the home row, center-left. Left index finger reaches right.",
    'y': "Letter Y. Top letter row, one row above the home row, center-right. Right index finger reaches left.",
    'u': "Letter U. Top letter row, one row above the home row. Right index finger. Above J.",
    'i': "Letter I. Top letter row, one row above the home row. Right middle finger. Above K.",
    'o': "Letter O. Top letter row, one row above the home row. Right ring finger. Above L.",
    'p': "Letter P. Top letter row, one row above the home row. Right pinky finger. Last key in the top letter row.",

    # Letter keys - Bottom row
    'z': "Letter Z. Bottom letter row, one row below the home row. Left pinky finger. First key in the bottom letter row.",
    'x': "Letter X. Bottom letter row, one row below the home row. Left ring finger. Below S.",
    'c': "Letter C. Bottom letter row, one row below the home row. Left middle finger. Below D.",
    'v': "Letter V. Bottom letter row, one row below the home row. Left index finger. Below F.",
    'b': "Letter B. Bottom letter row, one row below the home row, center-left. Left or right index finger.",
    'n': "Letter N. Bottom letter row, one row below the home row, center-right. Right index finger.",
    'm': "Letter M. Bottom letter row, one row below the home row. Right index finger. Below J.",
    ',': "Comma. Bottom letter row, one row below the home row. Right middle finger. Below K.",
    '.': "Period. Bottom letter row, one row below the home row. Right ring finger. Below L.",
    '/': "Forward slash. Bottom letter row, one row below the home row. Right pinky finger. Last key in the bottom letter row.",

    # Number keys
    '1': "Number 1. Top number row. Left pinky finger.",
    '2': "Number 2. Top number row. Left ring finger.",
    '3': "Number 3. Top number row. Left middle finger.",
    '4': "Number 4. Top number row. Left index finger.",
    '5': "Number 5. Top number row center. Left index finger reaches right.",
    '6': "Number 6. Top number row center. Right index finger reaches left.",
    '7': "Number 7. Top number row. Right index finger.",
    '8': "Number 8. Top number row. Right middle finger.",
    '9': "Number 9. Top number row. Right ring finger.",
    '0': "Number 0. Top number row. Right pinky finger.",

    # Punctuation and symbols
    "'": "Apostrophe. Right side, next to semicolon. Right pinky finger.",
    '-': "Minus or hyphen. Top row, right side. Right pinky finger.",
    '=': "Equals sign. Top row, far right. Right pinky finger.",
    '[': "Left bracket. Right side, above Enter. Right pinky finger.",
    ']': "Right bracket. Right side, above Enter. Right pinky finger.",
    '\\': "Backslash. Right side, above Enter. Right pinky finger.",
    '`': "Grave accent. Top left corner, above Tab. Left pinky finger.",
    '~': "Tilde. Top left corner, above Tab. Left pinky finger. Shift plus grave.",

    # Shifted number keys (symbols)
    '!': "Exclamation mark. Shift plus 1.",
    '@': "At sign. Shift plus 2.",
    '#': "Number sign or hashtag. Shift plus 3.",
    '$': "Dollar sign. Shift plus 4.",
    '%': "Percent sign. Shift plus 5.",
    '^': "Caret. Shift plus 6.",
    '&': "Ampersand. Shift plus 7.",
    '*': "Asterisk. Shift plus 8.",
    '(': "Left parenthesis. Shift plus 9.",
    ')': "Right parenthesis. Shift plus 0.",
    '_': "Underscore. Shift plus minus.",
    '+': "Plus sign. Shift plus equals.",
    '{': "Left brace. Shift plus left bracket.",
    '}': "Right brace. Shift plus right bracket.",
    '|': "Pipe or vertical bar. Shift plus backslash.",
    ':': "Colon. Shift plus semicolon.",
    '"': "Double quote. Shift plus apostrophe.",
    '<': "Less than. Shift plus comma.",
    '>': "Greater than. Shift plus period.",
    '?': "Question mark. Shift plus forward slash.",

    # Special keys
    'space': "Space bar. Large key at bottom center. Use thumbs.",
    'enter': "Enter key. Right side. Right pinky finger.",
    'return': "Enter key. Right side. Right pinky finger.",
    'tab': "Tab key. Left side, one row above the home row. Left pinky finger.",
    'backspace': "Backspace key. Deletes character to the left of cursor.",
    'delete': "Delete key. Deletes character to the right of cursor.",
    'escape': "Escape key. Top left corner of keyboard. Left pinky finger.",
    'capslock': "Caps Lock key. Left side, one row below Tab and left of A on the home row. Left pinky finger. Toggles capital letters.",
    'caps lock': "Caps Lock key. Left side, one row below Tab and left of A on the home row. Left pinky finger. Toggles capital letters.",

    # Navigation keys
    'insert': "Insert key. Toggles between insert and overwrite mode. Also used as the screen reader modifier key in JAWS and NVDA. Note: When NVDA or JAWS is running, the Insert key is captured by the screen reader and cannot be detected by other programs. Also Numpad 0 when Num Lock is off.",
    'home': "Home key. Moves cursor to beginning of line. Also Numpad 7 when Num Lock is off.",
    'end': "End key. Moves cursor to end of line. Also Numpad 1 when Num Lock is off.",
    'pageup': "Page Up key. Scrolls up one page. Also Numpad 9 when Num Lock is off.",
    'pagedown': "Page Down key. Scrolls down one page. Also Numpad 3 when Num Lock is off.",

    # Arrow keys
    'up': "Up arrow key. Bottom right area. Moves cursor up. Also Numpad 8 when Num Lock is off.",
    'down': "Down arrow key. Bottom right area. Moves cursor down. Also Numpad 2 when Num Lock is off.",
    'left': "Left arrow key. Bottom right area. Moves cursor left. Also Numpad 4 when Num Lock is off.",
    'right': "Right arrow key. Bottom right area. Moves cursor right. Also Numpad 6 when Num Lock is off.",

    # Function keys
    'f1': "F1 function key. Opens help in most programs. Windows key plus F1 opens Windows help.",
    'f2': "F2 function key. Renames selected file or folder in Windows Explorer.",
    'f3': "F3 function key. Opens search in many programs and web browsers. Shift plus F3 changes text case in Word.",
    'f4': "F4 function key. Opens address bar in browsers and Windows Explorer. Alt plus F4 closes active window.",
    'f5': "F5 function key. Refreshes web page in browsers. Starts slideshow in PowerPoint.",
    'f6': "F6 function key. Moves between panes in a program.",
    'f7': "F7 function key. Checks spelling in Microsoft Word.",
    'f8': "F8 function key. Used during Windows startup for safe mode options.",
    'f9': "F9 function key. Refreshes fields in Microsoft Word.",
    'f10': "F10 function key. Activates menu bar in many programs.",
    'f11': "F11 function key. Toggles full screen mode in web browsers.",
    'f12': "F12 function key. Opens Save As dialog in Microsoft Office. Opens developer tools in browsers.",

    # Modifier keys
    'shift': "Shift key. Both sides of keyboard. Hold to type capital letters and symbols.",
    'control': "Control key. Bottom left corner. Used with other keys for shortcuts. Control plus C copies, Control plus V pastes.",
    'ctrl': "Control key. Bottom left corner. Used with other keys for shortcuts. Control plus C copies, Control plus V pastes.",
    'alt': "Alt key. Bottom row, left of space bar. Opens menu bar or ribbon in many programs. Used with other keys for shortcuts.",
    'ralt': "Right Alt key. Bottom row, right side. Used with other keys for shortcuts.",
    'menu': "Applications key or context menu key. Opens right-click menu.",
    'windows': "Windows key. Opens Start menu on Windows.",
    'command': "Command key. Mac keyboard modifier.",
    # Note: Fn (Function) key is typically handled at hardware level and won't be detected
    # as a separate key press - it modifies other keys like F1-F12 at the keyboard level

    # Number pad keys
    'numpad0': "Numpad 0. Number pad, bottom row. When Num Lock is off, acts as Insert key.",
    'numpad1': "Numpad 1. Number pad, bottom left. When Num Lock is off, acts as End key.",
    'numpad2': "Numpad 2. Number pad, bottom center. When Num Lock is off, acts as Down Arrow key.",
    'numpad3': "Numpad 3. Number pad, bottom right. When Num Lock is off, acts as Page Down key.",
    'numpad4': "Numpad 4. Number pad, middle left. When Num Lock is off, acts as Left Arrow key.",
    'numpad5': "Numpad 5. Number pad, center. Has a small bump you can feel. When Num Lock is off, stays as numpad 5.",
    'numpad6': "Numpad 6. Number pad, middle right. When Num Lock is off, acts as Right Arrow key.",
    'numpad7': "Numpad 7. Number pad, top left. When Num Lock is off, acts as Home key.",
    'numpad8': "Numpad 8. Number pad, top center. When Num Lock is off, acts as Up Arrow key.",
    'numpad9': "Numpad 9. Number pad, top right. When Num Lock is off, acts as Page Up key.",
    'numpad_period': "Numpad period or decimal point.",
    'numpad_divide': "Numpad divide. Forward slash on number pad.",
    'numpad_multiply': "Numpad multiply. Asterisk on number pad.",
    'numpad_minus': "Numpad minus. Subtraction on number pad.",
    'numpad_plus': "Numpad plus. Addition on number pad.",
    'numpad_enter': "Numpad Enter. Confirms entry on number pad.",
    'numlock': "Num Lock key. Toggles number pad between numbers and navigation.",
    'scrolllock': "Scroll Lock key. Rarely used, changes scrolling behavior in some programs.",
    'printscreen': "Print Screen key. Captures screenshot.",
    'pause': "Pause or Break key. Used in some legacy programs.",
}

# Note: Screen reader commands are NOT implemented in keyboard explorer because screen readers
# (NVDA, JAWS) intercept the Insert key before the application can see it.
# This is by design - the Insert key is the screen reader's modifier key.
# Users should learn screen reader commands through the screen reader's own help system.

# Control key combinations - Common Windows keyboard shortcuts
CONTROL_KEY_SHORTCUTS = {
    'ctrl+a': "Control plus A. Selects all text or items in the current window.",
    'ctrl+b': "Control plus B. Applies bold formatting to selected text.",
    'ctrl+c': "Control plus C. Copies selected text or items to clipboard.",
    'ctrl+x': "Control plus X. Cuts selected text or items to clipboard.",
    'ctrl+v': "Control plus V. Pastes clipboard contents.",
    'ctrl+z': "Control plus Z. Undoes the previous action.",
    'ctrl+y': "Control plus Y. Redoes an undone action.",
    'ctrl+s': "Control plus S. Saves the current document or file.",
    'ctrl+p': "Control plus P. Opens print dialog.",
    'ctrl+f': "Control plus F. Opens find or search dialog.",
    'ctrl+h': "Control plus H. Opens find and replace dialog.",
    'ctrl+n': "Control plus N. Opens a new window or creates a new document.",
    'ctrl+o': "Control plus O. Opens an existing file.",
    'ctrl+w': "Control plus W. Closes the active window or tab.",
    'ctrl+t': "Control plus T. Opens a new tab in browser.",
    'ctrl+tab': "Control plus Tab. Switches to the next tab.",
    'ctrl+f4': "Control plus F4. Closes the active document window.",
    'ctrl+i': "Control plus I. Applies italic formatting to selected text.",
    'ctrl+u': "Control plus U. Applies underline formatting to selected text.",
    'ctrl+home': "Control plus Home. Moves cursor to the beginning of the document.",
    'ctrl+end': "Control plus End. Moves cursor to the end of the document.",
    'ctrl+left': "Control plus Left Arrow. Moves cursor one word to the left.",
    'ctrl+right': "Control plus Right Arrow. Moves cursor one word to the right.",
    'ctrl+up': "Control plus Up Arrow. Moves cursor to the beginning of the paragraph.",
    'ctrl+down': "Control plus Down Arrow. Moves cursor to the beginning of the next paragraph.",
    'ctrl+enter': "Control plus Enter. In email programs, sends the message. In forms, submits the form.",
    'ctrl+esc': "Control plus Escape. Opens the Start menu.",
}


def get_key_name(event, mods=None):
    """Get the friendly name for a pygame key event.

    Args:
        event: pygame KEYDOWN event
        mods: Optional modifier keys state (if None, will get from pygame)

    Returns:
        String name of the key pressed, with 'capital' prefix for uppercase letters
    """
    key = event.key

    # Get modifier state
    if mods is None:
        mods = pygame.key.get_mods()

    # Check for special keys first
    if key == pygame.K_SPACE:
        return 'space'
    elif key == pygame.K_RETURN:
        return 'enter'
    elif key == pygame.K_TAB:
        return 'tab'
    elif key == pygame.K_BACKSPACE:
        return 'backspace'
    elif key == pygame.K_DELETE:
        return 'delete'
    elif key == pygame.K_ESCAPE:
        return 'escape'
    elif key == pygame.K_CAPSLOCK:
        return 'capslock'
    elif key == pygame.K_INSERT:
        return 'insert'
    elif key == pygame.K_HOME:
        return 'home'
    elif key == pygame.K_END:
        return 'end'
    elif key == pygame.K_PAGEUP:
        return 'pageup'
    elif key == pygame.K_PAGEDOWN:
        return 'pagedown'
    elif key == pygame.K_UP:
        return 'up'
    elif key == pygame.K_DOWN:
        return 'down'
    elif key == pygame.K_LEFT:
        return 'left'
    elif key == pygame.K_RIGHT:
        return 'right'
    elif key == pygame.K_LSHIFT or key == pygame.K_RSHIFT:
        return 'shift'
    elif key == pygame.K_LCTRL or key == pygame.K_RCTRL:
        return 'control'
    elif key == pygame.K_LALT:
        return 'alt'
    elif key == pygame.K_RALT:
        return 'ralt'
    elif key == pygame.K_MENU:
        return 'menu'
    elif key == pygame.K_LSUPER or key == pygame.K_RSUPER:
        return 'windows'
    elif key == pygame.K_F1:
        return 'f1'
    elif key == pygame.K_F2:
        return 'f2'
    elif key == pygame.K_F3:
        return 'f3'
    elif key == pygame.K_F4:
        return 'f4'
    elif key == pygame.K_F5:
        return 'f5'
    elif key == pygame.K_F6:
        return 'f6'
    elif key == pygame.K_F7:
        return 'f7'
    elif key == pygame.K_F8:
        return 'f8'
    elif key == pygame.K_F9:
        return 'f9'
    elif key == pygame.K_F10:
        return 'f10'
    elif key == pygame.K_F11:
        return 'f11'
    elif key == pygame.K_F12:
        return 'f12'
    # Number pad keys - Note: When NumLock is OFF, these generate navigation key events instead
    # KP0 with NumLock OFF = Insert, KP1 = End, KP2 = Down, KP3 = PageDown
    # KP4 = Left, KP5 = KP5, KP6 = Right, KP7 = Home, KP8 = Up, KP9 = PageUp
    elif key == pygame.K_KP0:
        return 'numpad0'  # Or 'insert' when NumLock off, but pygame sends K_INSERT instead
    elif key == pygame.K_KP1:
        return 'numpad1'  # Or 'end' when NumLock off
    elif key == pygame.K_KP2:
        return 'numpad2'  # Or 'down' when NumLock off
    elif key == pygame.K_KP3:
        return 'numpad3'  # Or 'pagedown' when NumLock off
    elif key == pygame.K_KP4:
        return 'numpad4'  # Or 'left' when NumLock off
    elif key == pygame.K_KP5:
        return 'numpad5'  # Center key, has bump
    elif key == pygame.K_KP6:
        return 'numpad6'  # Or 'right' when NumLock off
    elif key == pygame.K_KP7:
        return 'numpad7'  # Or 'home' when NumLock off
    elif key == pygame.K_KP8:
        return 'numpad8'  # Or 'up' when NumLock off
    elif key == pygame.K_KP9:
        return 'numpad9'  # Or 'pageup' when NumLock off
    elif key == pygame.K_KP_PERIOD:
        return 'numpad_period'
    elif key == pygame.K_KP_DIVIDE:
        return 'numpad_divide'
    elif key == pygame.K_KP_MULTIPLY:
        return 'numpad_multiply'
    elif key == pygame.K_KP_MINUS:
        return 'numpad_minus'
    elif key == pygame.K_KP_PLUS:
        return 'numpad_plus'
    elif key == pygame.K_KP_ENTER:
        return 'numpad_enter'
    elif key == pygame.K_NUMLOCK:
        return 'numlock'
    elif key == pygame.K_SCROLLOCK:
        return 'scrolllock'
    elif key == pygame.K_PRINT:
        return 'printscreen'
    elif key == pygame.K_PAUSE:
        return 'pause'
    # Letter keys (a-z) - need explicit mapping for when modifiers are held
    elif key == pygame.K_a:
        return 'a'
    elif key == pygame.K_b:
        return 'b'
    elif key == pygame.K_c:
        return 'c'
    elif key == pygame.K_d:
        return 'd'
    elif key == pygame.K_e:
        return 'e'
    elif key == pygame.K_f:
        return 'f'
    elif key == pygame.K_g:
        return 'g'
    elif key == pygame.K_h:
        return 'h'
    elif key == pygame.K_i:
        return 'i'
    elif key == pygame.K_j:
        return 'j'
    elif key == pygame.K_k:
        return 'k'
    elif key == pygame.K_l:
        return 'l'
    elif key == pygame.K_m:
        return 'm'
    elif key == pygame.K_n:
        return 'n'
    elif key == pygame.K_o:
        return 'o'
    elif key == pygame.K_p:
        return 'p'
    elif key == pygame.K_q:
        return 'q'
    elif key == pygame.K_r:
        return 'r'
    elif key == pygame.K_s:
        return 's'
    elif key == pygame.K_t:
        return 't'
    elif key == pygame.K_u:
        return 'u'
    elif key == pygame.K_v:
        return 'v'
    elif key == pygame.K_w:
        return 'w'
    elif key == pygame.K_x:
        return 'x'
    elif key == pygame.K_y:
        return 'y'
    elif key == pygame.K_z:
        return 'z'
    # Number keys (0-9)
    elif key == pygame.K_0:
        return '0'
    elif key == pygame.K_1:
        return '1'
    elif key == pygame.K_2:
        return '2'
    elif key == pygame.K_3:
        return '3'
    elif key == pygame.K_4:
        return '4'
    elif key == pygame.K_5:
        return '5'
    elif key == pygame.K_6:
        return '6'
    elif key == pygame.K_7:
        return '7'
    elif key == pygame.K_8:
        return '8'
    elif key == pygame.K_9:
        return '9'
    else:
        # Fallback key name from pygame key map (helps with platform/keycode variations).
        key_label = pygame.key.name(key).strip().lower()
        normalized = key_label.replace("-", "").replace("_", "").replace(" ", "")
        if normalized == "capslock":
            return "capslock"

        # For other printable characters, try unicode
        if event.unicode:
            char = event.unicode
            # Check if it's a capital letter
            if char.isupper() and char.isalpha():
                return f'capital_{char.lower()}'
            else:
                return char.lower() if char.isalpha() else char
        else:
            return 'unknown'


def _prepend_phonetic_hint(description: str, key_name: str, *, capital: bool = False) -> str:
    """Place the phonetic cue immediately after the letter name when available."""
    hint = phonetics.phonetic_hint_for_key(key_name)
    if not hint:
        return description

    if capital:
        capital_hint = hint.replace(f"{key_name.upper()}, like", f"{key_name.upper()}, like")
        prefix = f"Capital {key_name.upper()}."
        return f"{prefix} {capital_hint}. {description}"

    prefix = f"Letter {key_name.upper()}."
    if description.startswith(prefix):
        remainder = description[len(prefix):].lstrip()
        return f"{prefix} {hint}. {remainder}"
    return f"{hint}. {description}"


def get_key_description(key_name, event=None):
    """Get the description for a key or key combination.

    Args:
        key_name: String name of the key
        event: Optional pygame key event for detecting modifier combinations

    Returns:
        Description string, or generic message if key not found
    """
    # Check for modifier key combinations if event provided
    if event is not None:
        # Get modifier state from event
        mods = event.mod
        ctrl_held = (mods & pygame.KMOD_CTRL) != 0
        alt_held = (mods & pygame.KMOD_ALT) != 0
        # Check for Control key combinations (allow Shift too, e.g., Ctrl+Shift+S)
        if ctrl_held and not alt_held:
            combo_key = f'ctrl+{key_name}'
            if combo_key in CONTROL_KEY_SHORTCUTS:
                return CONTROL_KEY_SHORTCUTS[combo_key]

        # Note: Insert key combinations are NOT checked because screen readers
        # (NVDA, JAWS) intercept Insert before the application can see it

    # Handle capital letters
    if key_name.startswith('capital_'):
        letter = key_name.replace('capital_', '')
        if letter in KEY_DESCRIPTIONS:
            return _prepend_phonetic_hint(KEY_DESCRIPTIONS[letter], letter, capital=True)
        else:
            return f"Capital {letter.upper()}."

    base_description = KEY_DESCRIPTIONS.get(key_name, "")
    described_text = _prepend_phonetic_hint(base_description, key_name) if base_description else ""

    # Add bump detection messages for special keys
    if key_name == 'f':
        return described_text + " Feel the bump and check where your pinky lands."
    elif key_name == 'j':
        return described_text + " Feel the bump to confirm home row."
    elif key_name == 'numpad5':
        return KEY_DESCRIPTIONS[key_name] + " Feel the bump?"

    if key_name in KEY_DESCRIPTIONS:
        return described_text
    else:
        return f"Key {key_name}. No description available."


def handle_keyboard_explorer_input(app, event, mods) -> None:
    if event.key == pygame.K_ESCAPE:
        app.state.mode = "MENU"
        app.say_menu()
        return

    if app.keyboard_explorer_first_key and event.key in (pygame.K_RETURN, pygame.K_SPACE):
        app.keyboard_explorer_first_key = False
        return

    app.keyboard_explorer_first_key = False

    key_name = get_key_name(event)
    description = get_key_description(key_name, event=event)
    app.speech.say(description, priority=True, protect_seconds=2.5)
    app.audio.beep_ok()
