# New in Key Quest

## Saturday March 21st 2026

Version 1.5.2

This update makes custom sentence files easier to manage.

- Any `.txt` file placed in the `Sentences` folder now appears as a practice topic, so users can add their own sentence sets without matching older hard-coded file names.
- When KeyQuest loads a sentence file, it now cleans the file into the same plain style used by the built-in sets.
- Cleanup keeps real language letters such as Spanish accents, while fixing common broken text encoding and removing emoji, duplicate lines, hidden characters, bullets, odd spacing, and similar copy-and-paste noise.
- The user guide now explains more clearly that users can either add new sentence files or edit the existing sentence files in the `Sentences` folder.

## Thursday March 19th 2026

Version 1.5.1

This update makes lesson guidance, game feedback, and large-text layouts easier to follow.

- Home-row lessons and Keyboard Explorer now mention the F and J bumps more directly, including the cue that if your left hand is lined up on F, your pinky should land on A.
- Lesson intros can now be reviewed with Up and Down arrows so screen reader users do not have to hear the whole intro in one long block.
- Free Practice now lets you choose from your unlocked lessons first.
- The About screen and guide now include a direct donation link for KeyQuest.
- The app window can be resized and tries to maximize on startup, which helps larger text stay visible.
- Menus and current game screens now do a better job of using the live window size instead of older fixed-size layout assumptions.
- Unexpected app and startup errors now save the local log, try to copy it to the clipboard automatically, and report the result with accessible dialogs instead of relying on console output.
- The GitHub project page now does a better job of pointing new visitors to downloads, the full guide, recent changes, and contributor notes.
- Release automation now waits for GitHub to finish publishing the release, so a shipped update is less likely to stop at a pushed tag with no visible downloads.
- The guide, repo page, and About screen now say more clearly that official KeyQuest builds come from the GitHub Releases page and that other builds are not official releases.

Letter and word game feedback is clearer.

- Letter Fall now uses one active target at a time, with stronger speech and visual emphasis on the current target.
- Letter Fall now slows itself down automatically when speech is active, uses clearer countdown cues, repeats only the current target on `Ctrl+Space`, and uses `Tab` to report the current target plus how many letters are waiting.
- Letter Fall and Word Typing now use the same correct and wrong key tones used elsewhere in lessons.
- Word Typing now starts more directly, and `Ctrl+Space` repeats only the current word.

Speech for confusing letters is clearer where it helps.

- A small set of letters such as A, C, D, E, K, and P can now use brief hints like `A, like alpha` in places where hearing the letter name alone can be confusing.
- Greek symbols and unusual old-style letters were removed from gameplay content.

## Tuesday March 10th 2026

Version 1.1.3

This patch fixes a pet screen crash and makes update errors stay local.

- The pet screen no longer crashes if older saved state or a partial startup path leaves the pet menu data missing.
- Update failures now write details to `keyquest_error.log`, try to copy that log to the clipboard automatically, and offer the setup download.
- Unexpected app errors now also stay local and tell you where the error log was saved.
- If KeyQuest has to use the Windows PowerShell fallback during update checks, it now does that without flashing a visible console window.
- When KeyQuest writes an update or app error, it now tries to copy the local error log to the clipboard automatically.

## Monday March 9th 2026

Version 1.1.2

This update makes the Practice Log easier to understand and keeps the app on one Python version more consistently.

- The Practice Log now says what activity was done in the day summary instead of only saying how many activities there were.
- Wording in the Practice Log is now clearer about the current item, such as whether today was faster or slower than the previous recorded day, or whether this activity did better or worse than the last similar activity.
- Internal release, Pages, and linting tools are now aligned to Python 3.9, which matches the app launcher and helps avoid version-related startup problems.

Version 1.1.1

This update smooths out several rough edges in daily use.

- Menus, setup screens, shop screens, pet screens, and confirmation dialogs were tightened so they behave more consistently.
- The Pet Shop now opens as a true pet-only shop instead of showing the full store.
- Word Typing now accepts Space to submit a word, and several leftover separator messages were removed from visible screens.
- Hangman results no longer keep repeating "round complete" while you move through the post-round menu.
- Hangman sentence practice now uses shorter prompts instead of repeating "type it exactly as shown" before every sentence.
- The Practice Log now uses friendlier dates and times, more natural duration wording, clearer activity names and results, simple day-to-day comparison notes, and a copy-to-clipboard option.
- Update failures now create a local error log and offer the setup download.
- General unexpected app errors now write to the same local error log.

## Saturday March 7th 2026

Version 1.1.1

This patch republishes the lesson and speech improvements below after fixing release validation checks.

This release makes lesson navigation and spoken guidance clearer.

- Lessons and Free Practice now end with clearer choice menus that use Up and Down arrows.
- The title now comes first, followed right away by the navigation instructions, so new screen reader users hear how to move through the choices sooner.
- The post-session wording now uses simpler continue and back wording.
- `Home` and `End` jump to the first and last items in menus, lesson lists, options, and results menus.
- Startup speech and menu speech are more reliable again on Windows.

Typing lesson speech is clearer.

- If you make a mistake in a lesson, KeyQuest now repeats only what is left to type instead of starting the whole prompt over.
- `Control+Space` in lessons now repeats only the remaining part of the target.
- Repeated-letter drills are spoken more clearly, so patterns like `aass` and `asas` are read as letter sequences instead of sounding like made-up words.
- Early lessons now introduce a new key with simpler repeated drills first before mixing it into longer patterns.

## Friday March 6th 2026

Version 1.0.4

This release fixes the Windows release build.

- The release build now uses a `cytolk` version that matches what KeyQuest already uses locally, so GitHub can publish the installer and portable downloads again.

Release pipeline fix

This release fixes the update pipeline itself.

- GitHub release publishing was repaired so shipped updates can build and publish the installer and portable downloads correctly again.
- The release process now has a clearer split between a plain GitHub push and a full shipped update.

Keyboard command practice is clearer.

- Windows, NVDA, and JAWS command topics were cleaned up so the wording feels more practical and less technical.
- Several command lines now read more naturally while still teaching the same shortcuts.

Guide and download wording improved.

- Download links now use cleaner names like `Installer.exe` and `Portable.zip`.
- The public guide, changelog, and blog wording were smoothed out to be clearer for new users, AT instructors, and educators.

Screen and menu layout improved.

The screen is easier to follow while you type and move through menus.

- Long sentences no longer try to stay on one line. They break across lines so they are easier to read.
- Your typed text can also continue onto the next line instead of getting cramped.
- Long menus are easier to follow because the current item stays in view more clearly.
- More screens now show when there are more items above or below the part you are looking at, including menus, options, shop lists, pet lists, and sound lists.
- There is now a Focus Assist option that adds stronger panels and emphasis around the part of the screen you should pay attention to.
- Several typing, setup, and results screens use stronger spacing and grouping so the active area is easier to find.
- Font Size now also includes larger 175% and 200% options for people who need bigger text.
- The guide and What's New page are being kept more current so it is easier to see what changed.

Typing reminders are clearer.

- Speed Test and Sentence Practice now remind you to use capital letters and punctuation before you begin.
- If you make a sentence mistake, KeyQuest gives a simpler spoken hint about what to type next.
- Quit now stays at the very end of the Main Menu.

Help and updates are easier to access.

- There is now a Main Menu item for the online guide.
- There is now a Main Menu item for this What's New page.
- You can now check for updates from inside KeyQuest, whether you installed it or are using the portable version.
- When KeyQuest updates, your progress stays with you.
- If you added your own sentence files, KeyQuest keeps them during updates and also brings in new built-in sentences.

## Wednesday February 25th 2026

Visual and reading options expanded.

- Text can now be made larger with the Font Size option.
- Key presses can show a brief visual flash as well as playing sounds.
- If your computer is already using Windows High Contrast, KeyQuest follows that automatically when the theme is set to Auto.
- A small on-screen Escape counter appears while you are exiting active modes.

## Thursday February 19th 2026

Version 1.0

KeyQuest 1.0 was released.

- The About screen was added to the Main Menu.
- The first Windows installer was added.
- The guide was expanded and made easier to read in a web browser.
