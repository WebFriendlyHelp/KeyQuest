"""Bundle everything a bug report needs into one file the user can attach.

Why this is not a "send" button. A ``mailto:`` link cannot carry an attachment:
RFC 6068 does not define one and mail clients strip any attempt, and this
project has already been bitten by Outlook Classic mangling ``mailto`` fields
outright. So instead of pretending to send, KeyQuest writes one file, says
exactly where it is, puts the path on the clipboard, and opens the folder with
the file selected. Every one of those steps works in any mail client, and the
user is never left guessing what happened.

Kept free of pygame, wx and COM so it can be tested directly.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path

from modules import error_logging, speech_log
from modules.version import __version__

# Each log is tailed rather than truncated from the front: a fault is at the end
# of a log, not the start. Sized so the bundle stays comfortably attachable.
_MAX_LOG_BYTES = 200 * 1024

SUPPORT_EMAIL = "help@webfriendlyhelp.com"


def default_output_dir() -> Path:
    """Where to write the bundle. Downloads is findable and writable."""
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path.home()


def build_filename(timestamp: float | None = None) -> str:
    stamp = time.strftime("%Y-%m-%d-%H%M%S", time.localtime(timestamp))
    return f"KeyQuest-diagnostics-{stamp}.txt"


def _read_tail(path: str | os.PathLike, limit: int = _MAX_LOG_BYTES) -> tuple[str, bool]:
    """Return the last `limit` bytes of a text file, and whether it was trimmed."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            if size > limit:
                handle.seek(size - limit)
                handle.readline()  # drop the partial first line
                return handle.read(), True
            return handle.read(), False
    except OSError:
        return "", False


_SECTION_MARKER = "\n\n===== "

# Pasting into an email is the one-step route, so the clipboard gets the report
# itself rather than a path. Past this size a paste stops being reasonable, and
# the summary plus a pointer to the saved file is more use than a wall of log.
_CLIPBOARD_LIMIT = 60_000


def _section(title: str) -> str:
    return f"{_SECTION_MARKER}{title} =====\n"


def clipboard_text(report: str, filename: str) -> tuple[str, bool]:
    """What to put on the clipboard, and whether the logs had to be left out."""
    if len(report) <= _CLIPBOARD_LIMIT:
        return report, False

    summary = report.split(_SECTION_MARKER, 1)[0]
    summary += (
        "\n\nThe logs were too long to paste here. They are in the saved file, "
        f"{filename}, which you can attach instead.\n"
    )
    return summary, True


def build_report(speech_state: dict | None = None, settings: dict | None = None) -> str:
    """Assemble the diagnostics text.

    Pure: takes what it is told about the app rather than reaching into it, so
    the content can be asserted in a test without constructing an app.
    """
    lines = [
        "KeyQuest diagnostics",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"KeyQuest version: {__version__}",
        f"Frozen build: {bool(getattr(sys, 'frozen', False))}",
        f"Python: {platform.python_version()}",
        f"Windows: {platform.platform()}",
        f"Machine: {platform.machine()}",
    ]

    if speech_state:
        lines.append("")
        lines.append("Speech state:")
        for key, value in speech_state.items():
            lines.append(f"  {key}: {value}")

    if settings:
        lines.append("")
        lines.append("Relevant settings:")
        for key, value in settings.items():
            lines.append(f"  {key}: {value}")

    report = "\n".join(lines)

    error_path = error_logging.get_log_file_path()
    error_text, error_trimmed = _read_tail(error_path)
    report += _section("Error log")
    report += f"Path: {error_path}\n"
    if error_trimmed:
        report += "(trimmed to the most recent entries)\n"
    report += error_text if error_text.strip() else "(empty, which is normal)\n"

    speech_path = speech_log.get_log_path()
    speech_text, speech_trimmed = _read_tail(speech_path)
    report += _section("Speech log")
    report += f"Path: {speech_path}\n"
    if speech_text.strip():
        if speech_trimmed:
            report += "(trimmed to the most recent entries)\n"
        report += speech_text
    else:
        report += (
            "(not present. The speech log is off by default. Turn on Speech Log "
            "in Options, reproduce the problem, then create this file again.)\n"
        )

    return report


def write_report(
    text: str,
    output_dir: str | os.PathLike | None = None,
    timestamp: float | None = None,
) -> Path:
    """Write the report and return its path. Raises OSError on failure."""
    target_dir = Path(output_dir) if output_dir else default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / build_filename(timestamp)
    path.write_text(text, encoding="utf-8")
    return path


def describe_result(
    path: Path,
    clipboard_ok: bool,
    folder_ok: bool,
    clipboard_shortened: bool = False,
) -> str:
    """What to say to the user.

    Pasting is offered first because it is one keystroke, where attaching means
    leaving the app and working a file dialog. Names the file and folder rather
    than pointing at them, since "the window that just opened" tells a screen
    reader user nothing. A failed clipboard copy is stated, not left to be
    discovered when the paste comes up empty.
    """
    parts = []
    if clipboard_ok:
        if clipboard_shortened:
            parts.append(
                "A summary is on your clipboard, ready to paste into an email. "
                "The logs were too long to paste, so send the file as well."
            )
        else:
            parts.append(
                "The diagnostics are on your clipboard. Paste them into an "
                "email and that is all we need."
            )
    else:
        parts.append("KeyQuest could not use the clipboard.")

    parts.append(f"They are also saved as {path.name} in the {path.parent.name} folder.")
    if folder_ok:
        parts.append("That folder is now open with the file selected.")
    if not clipboard_ok:
        parts.append(f"The full path is {path}")
    parts.append(f"Send it to {SUPPORT_EMAIL}")
    return " ".join(parts)
