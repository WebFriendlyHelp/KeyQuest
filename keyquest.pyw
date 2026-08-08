#!python3.11

import os
import shutil
import subprocess
import sys


def _show_startup_error_dialog(error_logging_module) -> None:
    """Report an early startup failure with the local log path and clipboard status."""
    log_path = error_logging_module.touch_log_file()
    copied = error_logging_module.copy_log_to_clipboard()
    lines = [
        "KeyQuest could not finish starting.",
        "",
        f"The details were written to:\n{log_path}",
        "",
    ]
    if copied:
        lines.append("The local error log was also copied to the clipboard.")
    else:
        lines.append("KeyQuest could not copy the local error log to the clipboard automatically.")

    try:
        from modules import dialog_manager

        dialog_manager.show_info_dialog("KeyQuest Startup Error", "\n".join(lines))
    except Exception:
        pass


if sys.version_info[:2] != (3, 11):
    launcher = shutil.which("pyw") or shutil.which("py")
    if launcher:
        script = os.path.abspath(__file__)
        try:
            subprocess.Popen([launcher, "-3.11", script, *sys.argv[1:]], close_fds=True)
            raise SystemExit(0)
        except Exception:
            pass

if "--version" in sys.argv:
    from modules.version import __version__
    print(__version__)
    sys.exit(0)

try:
    from modules.keyquest_app import main
except Exception as e:
    try:
        from modules import error_logging

        error_logging.log_exception(e)
        error_logging.log_message("KeyQuest Startup Error", f"{type(e).__name__}: {e}")
        _show_startup_error_dialog(error_logging)
    except Exception:
        pass
    raise


if __name__ == "__main__":
    # One copy at a time. Progress is saved as a whole document, last writer
    # wins, so two running copies silently overwrite each other's lessons, XP,
    # coins and pets. The lock waits a few seconds before giving up, because the
    # updater relaunches KeyQuest as the old copy is still exiting and refusing
    # to start in that window would strand the user right after an update.
    _instance_lock = None
    try:
        from modules.single_instance import InstanceLock, show_already_running_message

        _instance_lock = InstanceLock()
        if not _instance_lock.acquire():
            # A native message box, not the app's dialog helper: that one needs
            # a wx.App which does not exist this early, so it printed to a
            # console nobody sees and KeyQuest just failed to appear.
            show_already_running_message()
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        # Never let the duplicate check itself stop KeyQuest starting.
        _instance_lock = None

    try:
        main()
    finally:
        if _instance_lock is not None:
            _instance_lock.release()
