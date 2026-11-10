"""The startup-error message can appear when the app failed to import.

Fable review 2026-11-10, ui finding 10. keyquest.pyw's
_show_startup_error_dialog called dialog_manager.show_info_dialog, which needs
an existing wx.App; none exists when importing modules.keyquest_app has just
failed, so the helper printed to a console nobody has. It now uses the native
MessageBoxW, as single_instance does, which needs nothing initialised.

The function is lifted out of keyquest.pyw with the parser (importing the
script would start the app). MessageBoxW is patched, so no window opens.
"""

import ast
import ctypes
import os
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_function():
    path = os.path.join(ROOT, "keyquest.pyw")
    with open(path, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_show_startup_error_dialog")
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), namespace)
    return namespace["_show_startup_error_dialog"]


@unittest.skipUnless(os.name == "nt", "MessageBoxW is Windows only")
class TestStartupErrorDialog(unittest.TestCase):
    def test_uses_a_native_message_box(self):
        show = _load_function()
        fake_logging = types.SimpleNamespace(
            touch_log_file=lambda: r"C:\KQ\keyquest_error.log",
            copy_log_to_clipboard=lambda: False,
        )
        with mock.patch.object(ctypes.windll.user32, "MessageBoxW", return_value=1) as box:
            show(fake_logging)
        box.assert_called_once()
        text = box.call_args[0][1]
        self.assertIn("could not finish starting", text)
        self.assertIn("keyquest_error.log", text)


if __name__ == "__main__":
    unittest.main()
