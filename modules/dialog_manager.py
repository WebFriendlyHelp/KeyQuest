"""Universal dialog system for KeyQuest.

Centralizes all wxPython dialog creation and management for consistency
and accessibility across the application.
"""

import traceback
import sys
from modules import error_logging

try:
    import wx
    WX_AVAILABLE = True
except ImportError:
    WX_AVAILABLE = False
    print("wxPython not available - dialogs will print to console")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


def restore_pygame_focus():
    """Return keyboard focus to the pygame window after a modal wx dialog closes."""
    if not PYGAME_AVAILABLE:
        return

    try:
        pygame.event.clear()
        pygame.event.pump()
    except Exception as e:
        log_dialog_error("Pygame event cleanup", f"Failed to reset event queue: {e}", traceback.format_exc())

    if not sys.platform.startswith("win"):
        return

    try:
        if not pygame.display.get_init():
            return
        wm_info = pygame.display.get_wm_info() or {}
        hwnd = wm_info.get("window")
        if not hwnd:
            return

        import ctypes

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
    except Exception as e:
        log_dialog_error("Pygame focus restore", f"Failed to restore window focus: {e}", traceback.format_exc())


def log_dialog_error(error_type, error_msg, tb_str):
    """Log dialog errors to the main application log file."""
    error_logging.log_message(f"Dialog Error: {error_type}", error_msg, tb_str)


def show_dialog(
    title,
    content,
    dialog_type="info",
    close_on_enter=True,
    close_on_escape=True,
    close_on_space=False,
):
    """Show an accessible dialog box with read-only text content.

    This is the universal dialog function used throughout KeyQuest for:
    - Game results/scores
    - Speed test results
    - Practice results
    - Lesson results
    - Game info (How to Play, Controls, Description)
    - Any other informational content

    Args:
        title: Dialog window title
        content: Content to display in the text box
        dialog_type: Type of dialog ("info", "results") - currently just for documentation

    Returns:
        None - Blocks until user closes dialog
    """
    if not WX_AVAILABLE:
        # Fallback: print to console
        print(f"\n{'=' * 60}")
        print(f"{title}")
        print('=' * 60)
        print(content)
        print('=' * 60)
        return

    dlg = None
    try:
        # wx.App should already exist (created at application startup)
        # If not, something is wrong - log and fail gracefully
        wx_app = wx.App.Get()
        if not wx_app:
            error_msg = "wx.App not initialized - dialogs won't work"
            log_dialog_error("wx.App check", error_msg, "No traceback - app not initialized")
            print(f"ERROR: {error_msg}")
            print(f"\n{title}\n{content}")
            return

        # Create dialog with no parent
        try:
            dlg = wx.Dialog(None, title=title,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                           size=(600, 450))
        except Exception as e:
            log_dialog_error("wx.Dialog creation", f"Failed to create dialog: {e}", traceback.format_exc())
            raise

        # Create panel
        panel = wx.Panel(dlg)

        # Label so screen readers announce what this text area contains.
        content_label = wx.StaticText(panel, label=title)

        # Create read-only multiline text control
        text_ctrl = wx.TextCtrl(panel, value=content,
                               style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)

        # Set font based on dialog type
        if dialog_type == "results":
            # Monospace font for results (preserves alignment)
            font = wx.Font(11, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        else:
            # Default font for info
            font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        text_ctrl.SetFont(font)

        # Use a descriptive button label so screen reader users hear the action, not just "OK".
        ok_label = "Continue" if dialog_type == "results" else "OK"
        ok_btn = wx.Button(panel, wx.ID_OK, ok_label)
        if close_on_enter:
            ok_btn.SetDefault()

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(content_label, 0, wx.LEFT | wx.TOP | wx.RIGHT, 10)
        sizer.Add(text_ctrl, 1, wx.ALL | wx.EXPAND, 10)
        sizer.Add(ok_btn, 0, wx.ALL | wx.CENTER, 10)
        panel.SetSizer(sizer)

        # Move focus to text area so screen readers read content immediately.
        wx.CallAfter(text_ctrl.SetFocus)

        # Guard flag to prevent multiple EndModal calls (crash prevention)
        dialog_closing = [False]

        # Close dialog safely (called after event handler completes)
        def close_dialog():
            if not dialog_closing[0]:
                dialog_closing[0] = True
                try:
                    dlg.EndModal(wx.ID_OK)
                except Exception:
                    pass  # Dialog already closing

        # Bind Enter and Escape keys to close dialog
        def on_key(event):
            keycode = event.GetKeyCode()
            should_close = False
            if close_on_enter and keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                should_close = True
            elif close_on_escape and keycode == wx.WXK_ESCAPE:
                should_close = True
            elif close_on_space and keycode == wx.WXK_SPACE:
                should_close = True

            if should_close:
                # Use CallAfter to close dialog AFTER this event handler completes
                # This prevents crashes from trying to unbind events while they're executing
                wx.CallAfter(close_dialog)
                return  # Don't skip event - we handled it
            else:
                event.Skip()

        # Bind OK button to prevent multiple clicks causing crash
        def on_ok(event):
            # Use CallAfter to close dialog AFTER this event handler completes
            # This prevents crashes from trying to unbind events while they're executing
            wx.CallAfter(close_dialog)

        try:
            dlg.Bind(wx.EVT_CHAR_HOOK, on_key)
            ok_btn.Bind(wx.EVT_BUTTON, on_ok)
        except Exception as e:
            log_dialog_error("Event binding", f"Failed to bind events: {e}", traceback.format_exc())
            # Continue anyway - dialog may still work with mouse

        # CRITICAL CHANGE: Do NOT pump pygame events while wx dialog is modal
        # This was causing crashes - let wx have full control during ShowModal
        # We'll clear pygame events AFTER the dialog closes instead

        # Center dialog
        try:
            dlg.Centre()
        except Exception as e:
            log_dialog_error("Dialog centering", f"Failed to center dialog: {e}", traceback.format_exc())

        # Show modal - this blocks until user closes it
        # wx has FULL control during this time - no pygame event pumping
        try:
            dlg.ShowModal()
        except Exception as e:
            log_dialog_error("ShowModal", f"ShowModal failed: {e}", traceback.format_exc())
            raise

    except Exception as e:
        # Log exception and fallback to console
        error_msg = f"Dialog error: {type(e).__name__}: {e}"
        tb_str = traceback.format_exc()
        print(error_msg)
        print(f"\n{title}")
        print(content)
        log_dialog_error(f"show_dialog({title})", error_msg, tb_str)
    finally:
        # Always destroy dialog after ShowModal returns
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception as e:
                log_dialog_error("Dialog destroy", f"Failed to destroy dialog: {e}", traceback.format_exc())

        # Restore keyboard focus to the pygame window after the wx modal closes.
        restore_pygame_focus()


def show_info_dialog(title, content):
    """Show an informational dialog (How to Play, Controls, Description, etc.).

    Args:
        title: Dialog window title
        content: Content to display
    """
    show_dialog(title, content, dialog_type="info")


def show_yes_no_dialog(title, content, yes_label="Yes", no_label="No") -> bool:
    """Show a simple confirmation dialog and return True for Yes."""
    if not WX_AVAILABLE:
        print(f"\n{title}\n{content}")
        return False

    dlg = None
    try:
        wx_app = wx.App.Get()
        if not wx_app:
            error_msg = "wx.App not initialized - confirmation dialog won't work"
            log_dialog_error("wx.App check", error_msg, "No traceback - app not initialized")
            print(f"ERROR: {error_msg}")
            print(f"\n{title}\n{content}")
            return False

        dlg = wx.Dialog(
            None,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(600, 320),
        )
        panel = wx.Panel(dlg)

        # Label so screen readers announce what this text area contains.
        content_label = wx.StaticText(panel, label=title)

        text_ctrl = wx.TextCtrl(
            panel,
            value=content,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
        )
        text_ctrl.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        yes_btn = wx.Button(panel, wx.ID_YES, yes_label)
        no_btn = wx.Button(panel, wx.ID_NO, no_label)
        yes_btn.SetDefault()

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.Add(yes_btn, 0, wx.ALL, 6)
        button_row.Add(no_btn, 0, wx.ALL, 6)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(content_label, 0, wx.LEFT | wx.TOP | wx.RIGHT, 10)
        sizer.Add(text_ctrl, 1, wx.ALL | wx.EXPAND, 10)
        sizer.Add(button_row, 0, wx.ALL | wx.CENTER, 10)
        panel.SetSizer(sizer)

        # Move focus to text area so screen readers read content immediately.
        wx.CallAfter(text_ctrl.SetFocus)

        result_box = {"value": False}
        dialog_closing = [False]

        def finish(result_value):
            if dialog_closing[0]:
                return
            dialog_closing[0] = True
            result_box["value"] = result_value
            try:
                dlg.EndModal(wx.ID_YES if result_value else wx.ID_NO)
            except Exception:
                pass

        def on_key(event):
            keycode = event.GetKeyCode()
            if keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                # Respect whichever button currently has focus.
                focused = dlg.FindFocus()
                if focused is no_btn:
                    wx.CallAfter(finish, False)
                else:
                    wx.CallAfter(finish, True)
                return
            if keycode == wx.WXK_ESCAPE:
                wx.CallAfter(finish, False)
                return
            event.Skip()

        yes_btn.Bind(wx.EVT_BUTTON, lambda event: wx.CallAfter(finish, True))
        no_btn.Bind(wx.EVT_BUTTON, lambda event: wx.CallAfter(finish, False))
        dlg.Bind(wx.EVT_CHAR_HOOK, on_key)
        dlg.Centre()
        dlg.ShowModal()
        return result_box["value"]
    except Exception as e:
        error_msg = f"Confirmation dialog error: {type(e).__name__}: {e}"
        tb_str = traceback.format_exc()
        print(error_msg)
        print(f"\n{title}\n{content}")
        log_dialog_error(f"show_yes_no_dialog({title})", error_msg, tb_str)
        return False
    finally:
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception as e:
                log_dialog_error("Dialog destroy", f"Failed to destroy dialog: {e}", traceback.format_exc())
        restore_pygame_focus()


def show_results_dialog(
    title,
    content,
    close_on_enter=True,
    close_on_escape=True,
    close_on_space=False,
):
    """Show a results dialog (test results, game scores, lesson completion, etc.).

    Uses monospace font to preserve alignment of statistics.

    Args:
        title: Dialog window title
        content: Formatted results text
    """
    show_dialog(
        title,
        content,
        dialog_type="results",
        close_on_enter=close_on_enter,
        close_on_escape=close_on_escape,
        close_on_space=close_on_space,
    )
