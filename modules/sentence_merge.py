"""Merge newly shipped sentence files into the user's Sentences folder.

The problem this solves: users are actively invited to edit and add sentence
files (there is an "Open Sentences Folder" menu item), so an update must deliver
new and corrected content **without** ever discarding what they wrote.

Timestamps cannot do this.  ``robocopy /XO`` looks like the answer, but it cannot
distinguish "the user edited this" from "we shipped a newer one": a user who
installs in January and edits a file in February loses that edit to a build made
in March, because the shipped file is genuinely newer.

So the decision is made by *content* instead.  The updater sets aside the sentence
files that came with the release, and the next release is merged against that
baseline:

===========================  ==================================================
Situation                    Outcome
===========================  ==================================================
Not in the user's folder     Copied in.  New shipped content arrives.
Identical to the baseline    User never touched it, so it is updated.
Differs from the baseline    User edited it, so their copy is kept.
Not in the shipped set       A file the user created.  Never touched.
===========================  ==================================================

The merge runs here, in Python at startup, rather than in the update ``.bat``.
Batch cannot compare file contents without awkward ``certutil`` hashing, and
doing it here means the whole thing is unit-testable and behaves identically for
the installer and portable layouts.

This module is deliberately dependency-free (no pygame, no audio, no speech) so
it can be tested directly.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


SENTENCES_DIR_NAME = "Sentences"
# What shipped with the currently installed version.  Used as the baseline for
# the next merge; the user is never expected to look in here.
SHIPPED_DIR_NAME = "_sentences_shipped"
# Where the updater drops the incoming release's sentence files.
INCOMING_DIR_NAME = "_sentences_incoming"

_TEXT_SUFFIXES = {".txt"}


@dataclass
class MergeResult:
    """What the merge did, in terms a caller can report to the user."""

    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    kept_customized: list[str] = field(default_factory=list)
    baseline_created: bool = False
    ran: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated)

    def announcement(self) -> str:
        """A spoken summary, or an empty string when there is nothing to say.

        Deliberately plain ASCII with no symbols: this is read aloud.
        """
        parts: list[str] = []
        if self.added:
            count = len(self.added)
            parts.append(f"{count} new sentence {'file' if count == 1 else 'files'} added")
        if self.updated:
            count = len(self.updated)
            parts.append(f"{count} sentence {'file' if count == 1 else 'files'} updated")
        if self.kept_customized:
            count = len(self.kept_customized)
            parts.append(
                f"{count} of your customized {'file was' if count == 1 else 'files were'} kept unchanged"
            )
        if not parts:
            return ""
        if len(parts) == 1:
            body = parts[0]
        else:
            body = ", ".join(parts[:-1]) + ", and " + parts[-1]
        return f"Sentence content updated. {body[0].upper()}{body[1:]}."


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _sentence_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES
    )


def _same_content(left: Path, right: Path) -> bool:
    """Compare by content, ignoring line-ending differences.

    A user who opens a file in an editor that rewrites CRLF as LF has not
    meaningfully customized it, and should still receive corrections.
    """
    a, b = _read(left), _read(right)
    if a is None or b is None:
        return False
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def merge_sentences(app_dir: str | Path) -> MergeResult:
    """Merge any incoming shipped sentence files into the user's folder.

    Safe to call on every startup: with no incoming folder it does nothing but
    establish the baseline on first run.  Never raises; a failure to merge must
    not stop the app launching.
    """
    result = MergeResult()
    try:
        root = Path(app_dir)
        sentences = root / SENTENCES_DIR_NAME
        shipped = root / SHIPPED_DIR_NAME
        incoming = root / INCOMING_DIR_NAME

        # First run on an install that predates this feature: treat whatever is
        # there now as the baseline.  Assuming the user had customized
        # everything would mean they never receive another correction; assuming
        # they had customized nothing would let the next update overwrite edits
        # made before this version existed.  Recording the current state is the
        # only honest option.
        if not shipped.is_dir() and sentences.is_dir():
            try:
                shutil.copytree(sentences, shipped)
                result.baseline_created = True
            except OSError:
                return result

        if not incoming.is_dir():
            return result

        result.ran = True
        sentences.mkdir(parents=True, exist_ok=True)

        for incoming_file in _sentence_files(incoming):
            name = incoming_file.name
            live = sentences / name
            baseline = shipped / name
            try:
                if not live.exists():
                    shutil.copy2(incoming_file, live)
                    result.added.append(name)
                elif result.baseline_created:
                    # The baseline was manufactured from the live folder moments
                    # ago, so every file trivially "matches" it and carries no
                    # information about what actually shipped.  Trusting it here
                    # would overwrite every customization on the first run after
                    # this feature arrives.  Keep what is there; from the next
                    # update onward the baseline is real.
                    result.kept_customized.append(name)
                elif baseline.exists() and _same_content(live, baseline):
                    shutil.copy2(incoming_file, live)
                    result.updated.append(name)
                else:
                    # Either the user edited a file we shipped, or they created
                    # one whose name we have since started shipping.  Theirs.
                    result.kept_customized.append(name)
            except OSError:
                # One unreadable or locked file must not abandon the whole merge.
                continue

        # The incoming set becomes the baseline for next time, whether or not
        # every file was applied: it is a record of what we shipped, not of what
        # the user ended up with.
        try:
            if shipped.is_dir():
                shutil.rmtree(shipped, ignore_errors=True)
            shutil.copytree(incoming, shipped)
            shutil.rmtree(incoming, ignore_errors=True)
        except OSError:
            pass

        return result
    except Exception:
        return result
