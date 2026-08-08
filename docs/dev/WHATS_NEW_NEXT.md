# Draft What's New entry for the next release

**This is a draft, not a live document.** At release time: set the correct day
name and date in the heading (`tools/release.ps1` validates the day name against
the date), confirm the version matches `modules/version.py`, paste the entry
below to the top of `docs/user/WHATS_NEW.md`, and delete this file.

Written in the register already established in that file: plain English, second
person, no file or function names, and concrete about what the user will notice
or hear. Version below assumes a minor bump, since the sentence merge is a new
capability rather than only fixes.

---

## <Day> <Month> <Nth> 2026

Version 1.23.0

This update lets KeyQuest improve its sentence content without ever touching the
sentences you have written or changed yourself.

- When an update includes new or corrected sentence files, KeyQuest now adds them
  to your Sentences folder for you. This works the same way whether you use the
  installed version or the portable version.
- Anything you have edited is kept exactly as you left it. If an update includes a
  newer version of a file you have changed, KeyQuest keeps yours and tells you how
  many of your files it left alone.
- Sentence files you created yourself are never touched.
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
- KeyQuest now stops rather than installing an update it could not confirm was
  genuine.
- A failed check for updates no longer interrupts you. Before, if KeyQuest could
  not reach the internet during its regular background check, it would return you
  to the Main Menu and open a message, even in the middle of a lesson or a game.
  Now it stays quiet unless you asked it to check.
- Your saved progress and your sentence files continue to be kept safe across
  updates, including when an update has to be undone.

---

## Notes for whoever writes the final version

- Lead with the sentence merge. It is the only genuinely new capability here; the
  rest are reliability fixes, and the file's convention is that the summary
  sentence describes the headline.
- The `find` fix is worth a bullet even though it is invisible when it works,
  because 1.20.0 already told users about the symptom it causes. Tying the two
  together is honest and reassuring.
- Do not mention: the batch-file path handling, the snapshot completeness marker,
  the test harness, or CI. None of it changes anything a user can observe.
- Everything in this release is forward-only. It improves updates applied *from*
  this version onward, so a copy on 1.22.0 or earlier still uses the old updater
  for its next update. That is normal and has not been called out in previous
  entries, so probably leave it out unless you want to set expectations.
