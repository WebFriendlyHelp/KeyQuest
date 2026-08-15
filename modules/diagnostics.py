"""Bundle everything a bug report needs into one file the user can attach.

Why this is not a "send" button. A ``mailto:`` link cannot carry an attachment:
RFC 6068 does not define one and mail clients strip any attempt, and this
project has already been bitten by Outlook Classic mangling ``mailto`` fields
outright. So instead of pretending to send, KeyQuest writes one file, puts the
report itself on the clipboard, says exactly where the file is, and offers to
open the folder with the file selected. Every one of those steps works in any
mail client, and the user is never left guessing what happened.

Kept free of pygame, wx and COM so it can be tested directly.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path
from typing import NamedTuple

from modules import error_logging, speech_log
from modules.version import __version__

# Each log is tailed rather than truncated from the front: a fault is at the end
# of a log, not the start. Sized so the bundle stays comfortably attachable.
_MAX_LOG_BYTES = 200 * 1024

SUPPORT_EMAIL = "help@webfriendlyhelp.com"


def _known_folder_downloads() -> Path | None:
    """Ask Windows where Downloads actually is, rather than guessing.

    ``Path.home() / "Downloads"`` is a guess, and on the owner's own machine it
    was the wrong one: OneDrive's Known Folder Move had moved Downloads to
    ``C:\\OneDrive\\Downloads``, so the guessed folder did not exist at all, the
    report landed in the home folder instead, and KeyQuest announced it as "the
    csm12 folder". Anyone with OneDrive folder backup switched on has that same
    layout, and they are not a rare case.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Downloads, {374DE290-123F-4565-9164-39C4925E467B}
        folder_id = _GUID(
            0x374DE290,
            0x123F,
            0x4565,
            (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
        )

        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long

        buffer = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None,
                                        ctypes.byref(buffer)) != 0:
            return None
        found = buffer.value
        ole32 = ctypes.windll.ole32
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree(buffer)
        if not found:
            return None
        path = Path(found)
        return path if path.is_dir() else None
    except Exception:
        return None


def default_output_dir() -> Path:
    """Where to write the bundle. The user's real Downloads, wherever that is."""
    downloads = _known_folder_downloads()
    if downloads is not None:
        return downloads
    guess = Path.home() / "Downloads"
    if guess.is_dir():
        return guess
    return Path.home()


def build_filename(timestamp: float | None = None) -> str:
    """A name someone can read back over the phone without spelling it out.

    The old name was ``KeyQuest-diagnostics-2026-08-15-132050.txt``. Six
    unbroken digits at the end is a wall of numbers to anyone reading it aloud
    or listening to it, and "diagnostics" is our word for it rather than
    theirs. Spaces are deliberate: this file exists to be found in a folder and
    attached to an email, not typed at a command line.
    """
    local = time.localtime(timestamp)
    hour = local.tm_hour % 12 or 12
    meridiem = "AM" if local.tm_hour < 12 else "PM"
    day = time.strftime("%Y-%m-%d", local)
    return f"KeyQuest problem report {day} at {hour}-{local.tm_min:02d} {meridiem}.txt"


def unique_path(path: Path) -> Path:
    """Never overwrite a report the user might still be about to send.

    The name is only accurate to the minute, so two reports in one minute would
    otherwise land on the same name and the first would be gone. Numbered the
    way Windows itself numbers a duplicate, since that is what people expect.
    """
    if not path.exists():
        return path
    for number in range(2, 100):
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path


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
    path = unique_path(target_dir / build_filename(timestamp))
    path.write_text(text, encoding="utf-8")
    return path


def describe_result(
    path: Path,
    clipboard_ok: bool,
    clipboard_shortened: bool = False,
) -> str:
    """What the user is told once the file is written.

    Pasting is offered first because it is one keystroke, where attaching means
    leaving the app and working a file dialog. This message covers the saving
    only, and never claims a folder was opened: that is a separate question the
    caller asks afterwards, so the two must not be written as one. A failed
    clipboard copy is stated rather than left to be discovered when the paste
    comes up empty.
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

    parts.append(f"They are also saved as {path.name} in your {path.parent.name} folder.")
    if not clipboard_ok:
        parts.append(f"The full path is {path}")
    parts.append(f"Send it to {SUPPORT_EMAIL}")
    return " ".join(parts)


class FolderQuestion(NamedTuple):
    title: str
    body: str
    yes_label: str
    no_label: str


def open_folder_question(path: Path, saved_message: str) -> FolderQuestion:
    """The question asked after the file is written, never before.

    Opening the folder is worth offering: Explorer's ``/select`` lands keyboard
    focus on the file itself, so attaching it to an email is then two
    keystrokes. But it is a question, not a default, because opening it takes
    the foreground and throws the user out of KeyQuest mid-task, which is the
    v1.26.0 focus bug in a different coat. Most people paste from the clipboard
    and never want the folder at all.

    The body repeats what was saved rather than leaving that to ``Speech.say``.
    Speaking it and then raising a dialog talks over itself: the screen reader
    reads the dialog on the focus change and cuts the spoken line off partway.
    The dialog is the one channel that is certain to be read, so the whole
    message goes in it.

    The buttons say what they do. "Yes" and "No" are only meaningful to someone
    who still has the question in their head, and by the time you have tabbed to
    the buttons the question has scrolled out of earshot.
    """
    folder = path.parent.name
    return FolderQuestion(
        title=f"Open the {folder} folder?",
        body=(
            f"{saved_message}\n\n"
            f"Do you want to open the {folder} folder with {path.name} "
            "selected, ready to attach to an email?\n"
            "KeyQuest stays open either way."
        ),
        yes_label=f"Open the {folder} folder",
        no_label="Stay in KeyQuest",
    )
