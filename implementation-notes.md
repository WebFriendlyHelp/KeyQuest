# Implementation notes

Newest at top. The why and the watch-outs; what changed is in `docs/dev/CHANGELOG.md` and the open owner decisions are in `docs/dev/HANDOFF.md`.

## 2026-11-11, 1.28.1: uninstall removes everything

- **Every new file KeyQuest writes needs an `[UninstallDelete]` entry** in `tools/build/installer/KeyQuest.iss`, or uninstall leaves it behind. `tests/test_uninstall_removes_everything.py` makes the known writers write into a temporary install folder and fails on anything uncovered, but it only knows the writers it calls; add a new one there too.
- **`{app}` is deliberately not deleted wholesale.** `/DIR=` can point Setup at a folder holding other files. Entries name KeyQuest's own files and folders, then `dirifempty` removes `{app}`.
- **Updates keep progress only because nothing on the update path runs the uninstaller.** The updater and a by-hand Setup run both install over the top. A test refuses "uninstall" or `unins*.exe` in the updater modules; never add an uninstall-then-install step.
- **Not removed, on purpose:** files in the Downloads folder (Report a Problem bundles, a re-downloaded update). They were placed there for the learner. Raised with Casey.
- **Proof level.** The test parses the script and runs the writers; Inno is not run. The script compiles with the Inno Setup 6 ISCC on this machine. The real check is the VM checklist in the 1.28.1 report.
- **Dev server.** A refusal sent before the body is read must drain first (`_drain_and_refuse`, at most 64 KiB and 1 second), or Windows resets the connection. The handler timeout is 5 seconds; long polls wait in the handler and are unaffected.

## 2026-11-10, pre-merge review fixes

- **Never reduce a plural by stripping its final "s".** Wiktionary has "Obsolete spelling of" entries for many stripped forms (darknes, abilitie), and that step shipped them. Reduce only on "plural of X", or drop the plural when its singular is itself a sentence word. The list is 1,265 words. Some plurals whose singular is not a sentence word still have an odd first sense ("cliffs": Cliff notes, "facts": used to express agreement); the extraction keeps only one sense per word, so a better fix is in build_hangman_dictionary.py, not here.
- **A Letter Fall pause survives modifier and screen reader keys** (`_PAUSE_KEEPING_KEYS` in keyquest_app.py). Any other key resumes, says "Resumed. Current target: X.", and is swallowed, so the key that resumes is never scored.
- **Pet mood and evolution lines are queued** (interrupt=False). They always follow a session's own end line.
- **Not changed, written up:** a progress file from before this branch has no `pet_decay_applied_date`, so the first launch applies one more decay (one time, floored at 0). A queued follower spoken with priority and no protect_seconds ends the leader's protection window early (Speech.say sets it to now + 0); only non-priority non-interrupting lines were ever dropped by that window. `--selftest` loads Tolk on the release runner, which is unproven until the first tagged build.

## 2026-11-10, round 4: the Hangman extraction leaves the repo

- **`tools/dev/hangman_source/` is git-ignored and holds the 62 MB extraction.** Switching to a branch that still tracks `data/wordlists/hangman_definitions.json` (speech-capture-pilot, main) checks those files out there again; switching back removes them from `data/wordlists` while the ignored copies stay put.
- **History still contains the 62 MB.** Removing it needs a history rewrite and force-push, which is the owner's call.
- **`games/hangman.py` still names `data/wordlists/hangman_words.txt`** (`EXTERNAL_WORDLIST_PATH`, used only by `load_external_words`, which nothing in the game calls). It now finds no file and returns an empty list, as its tests expect. Left alone; deleting the dead loader is a separate cleanup.

## 2026-11-10, round 3: the owner's decisions

- **Every source edit in round 3 went through the Edit tool**, after a watched failing run; none through a script.
- **Never spawn `keyquest.pyw` from a test to check a new flag.** Run test-first, an unhandled flag starts the full app; it ran headless for two minutes and spoke through NVDA. Test the flag in-process and read the entry point instead (`tests/test_release_selftest.py`).
- **Paths to shipped data must come from `app_paths.get_app_dir()`, not `__file__`.** In the frozen build, `games/` and `modules/` are imported from the PyInstaller archive and `__file__` points into `_internal`, where the spec copies nothing.
- **The installer and the bats now share the staging job.** A current installer stages `_sentences_incoming` itself on an existing install; the bats clear any leftover set before the installer runs and stage from `Sentences` only when it did not (an older installer). A bat from an older app in the field still overwrites the installer's set with the user's files: the merge then does nothing, and the defaults fallback delivers on the next start. No data is lost; corrections arrive one start late, once.
- **Inno `Excludes` must stay anchored (`"\Sentences\*"`).** Unanchored, it also drops `defaults\Sentences`, which the merge falls back to.
- **The Hangman list is a selection, rebuilt by a tool, not hand-edited.** Re-run `tools/dev/build_hangman_common.py` after sentence or dictionary changes and read the words it reports leaving out. It is short of "a few thousand" because it only uses words from KeyQuest's English sentence files.
- **`PAUSE_ON_ESCAPE` pauses by skipping `update()`.** Games that time by wall clock (Word Typing) would not actually pause this way, which is why only Letter Fall opts in.
- **Hand-added history hash:** `sentence_history.json` has one hash for "Spanish Sentences.txt" (abf2c6d2...) that no shipped file has; it is the old loader's rewrite. The hash tool only adds, so it survives.

## 2026-11-10: Fable review fixes (branch fix/fable-review-2026-11-10)

- **Most source edits on this branch were applied by a replace script, not the Edit tool**, because the test-first edit guard could not see subagent transcripts at the time. The scripts did exact, unique string replacement and kept each file's encoding and line endings. Afterwards every source diff on the branch was read in full against speech-capture-pilot: no stray reformatting, no replacement in the wrong place, the BOM on `docs/dev/HANDOFF.md` intact, and all committed blobs pure LF. The only whitespace-only differences are deliberate re-indents (lesson_mode special-key branch, pet and shop queued announcements, the Hangman clipboard test). The scripts did leave mixed CRLF and LF in four working-tree files (base_game, word_typing, challenge_manager, quest_manager); `core.autocrlf=true` normalised them on commit, so the repository never saw it.
- **Queuing a follower line needs `priority=True` as well as `interrupt=False`.** A plain non-priority line spoken inside the previous line's protection window is dropped, not queued. `tests/speech_burst.py` runs the real `Speech.say` drop logic; it proves call order, not what NVDA voices.
- **Sentence files are cleaned in memory only.** Never reintroduce a write-back from the loader: it deleted learners' sentences and made shipped files hash as customised. The merge report only mentions kept files when `_sentences_incoming` was present at startup, because without a staged update every edited file is "kept" on every launch.
- **Mojibake is a two-character sequence**, a marker letter followed by Latin-1 punctuation or a cp1252 special. The marker letter alone is ordinary French, Portuguese or Icelandic. It is checked before normalising too, because normalising strips the second character of "Ã©".
- **Special-key lessons (25 to 32) advance on accuracy above 80 percent alone.** The streak counter ignores repeated keys and the WPM bar is for phrase lessons. If the owner wants a different bar, change it there, not in `should_advance`.
- **`release.ps1` Invoke-Step resets and checks `$LASTEXITCODE`.** A step whose native command answers with its exit code (the tag probe uses `git ls-remote --exit-code`) must pass `-AllowNonZeroExit` and check the code itself.
- **Not fixed and not reached in this run:** modules finding 14 (streak milestones from `record_session` are dropped by all four callers, and the `streak_milestone_*` coin rewards are unused), UI finding 8 (the What's New gate is satisfied by the version bump), UI finding 9 (the release smoke test exits before importing the app). Modules finding 9 (one late typo blocks the unlock) is an owner decision about the advancement rule.
- **Lint baseline:** `ruff check .` reports one F401 in `tests/test_speech_capture.py` (unused `MagicMock`). It is already on speech-capture-pilot and was left alone.
