# Draft What's New entry for the next release

**This is a draft, not a live document.** At release time: set the correct day
name and date in the heading (`tools/release.ps1` validates the day name against
the date), confirm the version matches `modules/version.py`, paste the entry
below to the top of `docs/user/WHATS_NEW.md`, and delete this file.

Written in the register already established in that file: plain English, second
person, no file or function names, concrete about what the user will notice or
hear. Minor bump assumed, since the sentence handling is new capability rather
than only fixes.

---

## <Day> <Month> <Nth> 2026

Version 1.23.0

This update lets KeyQuest improve its sentence content without ever touching the
sentences you have written, changed, or deleted yourself.

- When an update includes new or corrected sentence files, KeyQuest now adds them
  to your Sentences folder for you. This works the same way whether you use the
  installed version or the portable version.
- Anything you have edited is kept exactly as you left it. If an update includes a
  newer version of a file you have changed, KeyQuest keeps yours and tells you how
  many of your files it left alone.
- If you delete a sentence file, it stays deleted. It will not come back with the
  next update, and the topic no longer appears in your practice or speed test
  menus.
- Sentence files you created yourself are never touched.
- There is a new Restore Default Sentences item on the main menu. It puts every
  sentence file back the way KeyQuest ships it, including any you deleted. It
  asks first, and tells you plainly that your changes to those files will be
  replaced.
- If your whole Sentences folder goes missing, KeyQuest puts the original files
  back and tells you it has done so, instead of leaving you with an empty topic
  list.
- Until now the portable version never received new sentence content at all, so
  those files only ever changed if you edited them.
- Fixed a problem that could stop an update from waiting for KeyQuest to close
  before it started replacing files. On computers with certain developer tools
  installed, an update could begin while KeyQuest was still running, which could
  make it fail or have to be undone. This is the underlying cause of the
  "waiting for Windows to release the old file" problem improved in 1.20.0.
- If an update cannot finish and KeyQuest restores your previous version, it now
  restores it exactly, rather than possibly leaving a mixture of old and new
  files behind.
- If an installer update fails partway, your saved progress and your sentence
  files are now put back before KeyQuest restarts.
- KeyQuest now stops rather than installing an update it could not confirm was
  genuine.
- A failed check for updates no longer interrupts you. Before, if KeyQuest could
  not reach the internet during its regular background check, it would return you
  to the Main Menu and open a message, even in the middle of a lesson or a game.
  Now it stays quiet unless you asked it to check.

---

## Notes for whoever writes the final version

- Lead with the sentence handling. It is the only genuinely new capability; the
  rest are reliability fixes, and this file's convention is that the summary
  sentence describes the headline.
- The wait-loop fix is worth a bullet even though it is invisible when it works,
  because 1.20.0 already told users about the symptom it causes. Tying the two
  together closes a loop already opened with them.
- Do not mention: the hash history, the deletion record file, batch-file path
  handling, the snapshot completeness marker, the test harness, or CI. None of it
  changes anything a user can observe.
- **Decided (owner, 2026-08-08): leave out** the caveat that a sentence file
  deleted *before* this version comes back one more time. It is true (there was
  no record of the deletion until now, and deleting it again sticks) but it is
  too much detail for a user-facing note. Do not re-raise it.
- Everything here is forward-only: it improves updates applied *from* this version
  onward, so a copy on 1.22.0 still uses the old updater for its next update.
  Previous entries have never mentioned this, so probably leave it out.
