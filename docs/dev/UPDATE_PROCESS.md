# KeyQuest Update Process

This is the end-to-end technical reference for how KeyQuest updates itself, and
how a release is built and published so that installed copies can find it. It is
deliberately detailed because the system has many moving parts across three
places: the running app (Python), the build/release pipeline (PowerShell + GitHub
Actions), and the Windows install layout (Inno Setup or portable ZIP).

For the *policy* side (when to ship, how the version bump is chosen, the human
commands), see `RELEASE_POLICY.md`. This document covers the *machinery*.

## The one mental model to keep

The updater that performs an update from version N to version N+1 is the updater
**baked into the already-installed version N** — not the newer code in the repo.

So when you change anything in `modules/update_manager.py` or
`modules/update_controller.py`, those changes do not help the jump *to* that
release; they only take effect for the *next* jump after users are already on it.
Always reason about an update as "the old version's updater applying the new
version's files."

## Two distribution layouts

KeyQuest ships in two shapes, and the updater behaves differently for each.

- Installer layout. Produced by Inno Setup (`tools/build/installer/KeyQuest.iss`).
  Installs per-user to `%LocalAppData%\Programs\KeyQuest`. Detected by
  `is_installed_layout()`: the presence of a `.keyquest-installed` marker file
  (written by the installer's `[Run]` step) or any `unins*.exe`. This is a
  non-OneDrive, non-synced location, which matters: the file-replacement step is
  not fighting a sync engine for locks.
- Portable layout. The `KeyQuest-win64.zip` unpacked anywhere by the user.
  Detected by `is_portable_layout()`: a frozen `KeyQuest.exe` sitting next to
  `modules/`, `games/`, and `Sentences/`, with no installer markers. Portable
  copies may live in a synced folder (Dropbox/OneDrive), which is the main reason
  the portable path is more failure-prone than the installer path.

`AppUpdateController.__init__` picks the mode once at startup
(`_portable_update_mode`) and never changes it for the session.

## The self-update gate

`update_manager.can_self_update()` returns true only when both are true:

- the OS is Windows (`os.name == "nt"`), and
- the process is a frozen build (`getattr(sys, "frozen", False)`).

So running from source (`py -3.11 keyquest.pyw`) never self-updates, and neither
does any non-Windows environment. A manual "check for updates" from source speaks
"Automatic updating is only available in the installed Windows app." and stops.

## Client runtime flow

All client orchestration lives in `modules/update_controller.py`
(`AppUpdateController`). It is created in `KeyQuestApp.__init__`, and the app
drives it through a small public surface:

- `start_startup_update_check_if_enabled()` — called once at startup. Cleans up
  stale staged files, runs post-restart verification (see the pending marker
  below), and — if `Settings.auto_update_check` is on — kicks off a background
  check.
- `poll_update_work()` — called every frame from the main loop. This is where all
  completed background work is applied on the main thread (check results, download
  results, fallback results), where the 4-hour periodic re-check is triggered
  (`UPDATE_PERIODIC_INTERVAL_S`), and where a deferred update is resumed.
- `maybe_check_from_main_menu()` and `begin_pending_update_if_ready()` — called
  when the app returns to the main menu, to re-check after a cooldown and to start
  any update that was deferred while the user was mid-game.

All network and disk work happens on daemon threads; results are handed back to
the main thread through `self._update_lock`-guarded fields and consumed in
`poll_update_work()`. The Pygame canvas is never touched off-thread.

### Check

`update_manager.check_for_update(current_version, portable)`:

1. `fetch_latest_release()` GETs the GitHub "latest release" endpoint
   (`/releases/latest`), which returns the newest release that is **not** a draft
   and **not** a pre-release. This is why the rolling `latest` pre-release (see
   the pipeline section) is invisible to the updater.
2. `parse_release_version()` reads `tag_name` (then `name`) and
   `normalize_version()` reduces it to dotted digits. `is_newer_version()` does a
   tuple compare of the numeric parts, zero-padding to equal width, so `1.20.0`
   vs `1.20.1` and `1.20` vs `1.20.0` compare correctly.
3. If newer, it selects the asset for this layout: `select_installer_asset()`
   wants exactly `KeyQuestSetup.exe` (falling back to any `*setup*.exe`);
   `select_portable_asset()` wants exactly `KeyQuest-win64.zip` (falling back to
   any `keyquest*.zip`). If no matching asset is attached, it raises
   `UpdateNoAssetError` and the UI reports "no installer/portable asset attached
   yet."
4. The metadata fetch has retry-with-backoff for transient network errors
   (`_fetch_with_retry`), but not for HTTP or parse errors (retrying those will
   not help).

### Defer if mid-game

If an update is found while the user is not at the main menu, it is stored in
`_pending_update_release` and applied later from `begin_pending_update_if_ready()`
once `state.mode == "MENU"`. We never interrupt a game to install.

### Download and verify

`_download_update_worker` downloads to the staging directory
`%TEMP%\KeyQuestUpdater\` (`get_updates_dir()`), under a stable per-version
filename (`build_installer_filename` / `build_portable_zip_filename`). It reports
byte progress to the speech/status line.

Integrity check: if the release contains a `<asset>.sha256` sidecar
(`select_sha256_asset`), the updater downloads it (`fetch_sha256_for_asset`,
tolerant of both bare-hex and "hex  filename" formats) and compares
(`verify_file_sha256`). A mismatch aborts the update. If there is no sidecar, the
check is skipped with a logged note (it is not treated as a failure, but the
pipeline always produces sidecars, so in practice the check always runs).

### Handoff and exit

`_launch_downloaded_update()` writes a detached `.bat` launcher (see the two path
sections below), starts it with `cmd /c` under `DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`, then watches it for ~4 seconds. If
the launcher exits within that window it is treated as an immediate failure and
the direct fallback runs. Otherwise the app writes the pending marker, saves
progress, announces the restart, and exits so its files are unlocked.

### Post-restart verification

Before exiting, the controller writes `pending_update.json` into the app dir
(`write_pending_update_marker`) recording the expected version. On the next
startup, `check_pending_update_marker` compares the now-running version against
the expected one and deletes the marker:

- running version meets or exceeds expected -> "update applied successfully"
  (logged), and
- running version is still behind -> a spoken warning that the update did not
  apply and KeyQuest will try again.

## Installer update path (the path the installed copy uses)

`create_update_launcher()` renders `_INSTALLER_BAT_TEMPLATE` into
`run_keyquest_update.bat`. The bat is pure cmd built-ins plus `robocopy` and the
Inno installer — no PowerShell dependency (this is a hard project rule; execution
policy has bitten us before). Steps:

1. Wait for the old KeyQuest PID to exit by polling `tasklist`; after 30 seconds
   it force-closes with `taskkill /F` as a safety net.
2. Back up user data into an `installer_backup` folder: `progress.json` and the
   whole `Sentences` tree (so user-added sentence sets survive).
3. Run the installer silently into the existing directory:
   `KeyQuestSetup.exe /CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL
   /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /DIR=<app dir>`. Because the Inno
   script is `PrivilegesRequired=lowest` and the install is per-user, this needs
   no admin elevation and shows no UAC prompt. Inno performs the actual file
   replacement, which is far more robust than a hand-rolled copy.
4. Sanity-check that `modules\version.py` exists afterward; if not (or if the
   installer returned non-zero), restart the old exe and bail.
5. Restore `progress.json` and merge the backed-up `Sentences` back in
   (`robocopy /XN`, so freshly shipped sets are not clobbered by older copies),
   delete the backup, restart `KeyQuest.exe`, and delete the downloaded installer.

## Portable update path

`create_portable_update_launcher()` renders `_PORTABLE_BAT_TEMPLATE` into
`run_keyquest_portable_update.bat`. Pure cmd plus `tar` (Windows 10 1803+) and
`robocopy`; an optional `KEYQUEST_UPDATER_TEST_PYTHON` env var swaps in a Python
extractor for tests. Steps:

1. Wait for the PID to exit (same `tasklist` loop, 30s then `taskkill`).
2. Extract the ZIP into a `portable_extract` folder and confirm
   `KeyQuest\KeyQuest.exe` is present.
3. Preserve the existing `Sentences` into the extracted tree (`robocopy /XN`).
4. Mirror the new tree over the app dir with `robocopy /MIR`, excluding
   `progress.json`, `KeyQuest.exe`, `keyquest_error.log`, and the `Sentences` and
   `updates` directories.
5. Replace `KeyQuest.exe` with a retry loop (up to 15 tries) because the exe can
   stay briefly locked. `KEYQUEST_UPDATER_SKIP_EXE_COPY` skips this in tests.
6. Restart and delete the ZIP.

Because this path replaces files directly rather than going through an installer,
it is the one most exposed to sync-engine locks and the place where the RemSound
ideas (stage off-tree in LocalAppData, do the swap in-process) would help if we
ever harden it.

## Three fallback layers

Every failure path is designed so the user is never left without a running app.

1. Primary: the detached `.bat` launcher above.
2. Direct apply (`_fallback_run_update_direct` -> `_fallback_apply`): used when the
   launcher exits within ~4 seconds or fails to start. For the installer it
   launches `KeyQuestSetup.exe` directly (visible UI). For portable it writes a
   second pure-bat extractor (`create_portable_fallback_bat`,
   `_PORTABLE_FALLBACK_BAT_TEMPLATE`) and runs that.
3. Re-download (`_fallback_download_worker`): if the staged file is gone by the
   time the fallback runs, it re-downloads the latest asset to `~/Downloads/` and
   then applies it.

If all of that fails, the app returns to the menu and speaks a "please update
manually from the website" message.

## Network resilience

The default transport is `urllib` with an SSL context that loads both the OS
trust store and `certifi` when available. On Windows, if a request fails with a
certificate-verification error specifically, the updater retries the same request
through Windows-native helpers in order: PowerShell (`Invoke-RestMethod` /
`Invoke-WebRequest`) then `curl.exe`. This is the workaround for old Windows TLS
stacks where Python's bundled chain cannot validate GitHub. Other network errors
surface as `UpdateNetworkError` with a plain-language message.

## Staging, cleanup, logging

- Staging dir: `%TEMP%\KeyQuestUpdater\` for downloads, launcher scripts, backup,
  and extract folders.
- `cleanup_stale_update_files()` runs at startup and removes staged
  `.exe/.zip/.bat/.sha256` older than 3 days plus the known working folders.
- The launchers append progress lines to `keyquest_error.log` in the app dir, so a
  failed update leaves a diagnostic trail even though the GUI is gone by then.

## Release and CI pipeline

How a new release is built and published so the updater can find it.

### Local: ship a release

`tools/ship_updates.ps1` (wrapper):

1. Requires a dirty working tree and that `modules/version.py` is not already
   modified.
2. Chooses the bump (`auto` uses `tools/dev/release_bump.py --suggest`; or pass
   `-Bump patch|minor|major`) and applies it to `modules/version.py`.
3. Calls `tools/release.ps1 -SkipLocalBuilds`.

`tools/release.ps1` (core): must be on `main`. It enforces release hygiene before
anything is pushed: `docs/user/WHATS_NEW.md` must be updated, its top version
entry must match `modules/version.py`, and the day name in the dated heading must
match the actual date. It rebuilds the Pages site, runs the test suite, then
commits `Release vX.Y.Z`, pushes `main`, creates the annotated tag `vX.Y.Z`, and
pushes the tag. It has resume logic if the tag already exists locally.

Pushing the tag is the trigger. Pushing `main` alone never publishes a release.

### CI: build and publish (`.github/workflows/release.yml`)

Triggered on pushing a `v*` tag:

1. Reads the version and asserts the pushed tag equals `v<version>` (guards
   against a tag/version mismatch).
2. ruff lint, pytest, `release_bump.py --validate`.
3. Builds the exe (with a `--version` smoke test), the portable ZIP, and the
   installer; verifies both artifacts exist.
4. Generates `.sha256` sidecars for the ZIP and the installer.
5. `gh release create vX.Y.Z ... --latest` attaching all four assets with exact
   pinned names (`KeyQuest-win64.zip`, `KeyQuest-win64.zip.sha256`,
   `KeyQuestSetup.exe`, `KeyQuestSetup.exe.sha256`). Marked latest, not a
   pre-release.
6. A second job runs `tests/update_smoke_test.py` against the fresh release.

### CI: rolling dev build (`.github/workflows/latest-build.yml`)

Triggered on every push to `main`: builds the same artifacts and overwrites a
rolling `latest` tag release targeting HEAD, marked `--prerelease`. This is for
manual testers. Because it is a pre-release, `/releases/latest` ignores it and it
never triggers an auto-update.

### CI: manual smoke test (`.github/workflows/update-smoke-test.yml`)

A `workflow_dispatch` (manual) runner for `tests/update_smoke_test.py`.

## The contract between release and updater

For an installed copy to auto-update to the next version, the release must:

- be a normal release marked latest (not draft, not pre-release), so
  `/releases/latest` returns it;
- carry a numeric `tag_name`/version strictly greater than the installed one; and
- attach the asset named exactly `KeyQuestSetup.exe` (installer) and/or
  `KeyQuest-win64.zip` (portable), ideally with their `.sha256` sidecars.

Going through `tools/ship_updates.ps1` satisfies all of this automatically. The
single most common way to break self-update by hand is to publish the next
release as a pre-release instead of latest.

## Testing

- `py -3.11 tests/run_local_updater_integration.py` — full local end-to-end test.
  Builds fixture exes, seeds an old installed app and an old portable app, builds
  a new payload tree, ZIP, and fake installer, serves a local release feed, then
  runs both update cycles (detect -> download -> sha256 verify -> launcher ->
  stop old -> apply -> relaunch into new version). 21 steps; writes
  `tests/logs/local_updater/REPORT.md`.
- `tests/update_smoke_test.py` — runs in CI post-release and via the manual
  workflow.
- `tests/test_*` updater unit tests under `tests/` cover version parsing, asset
  selection, marker logic, and launcher rendering.

## Key files

- `modules/update_manager.py` — release API, version compare, asset selection,
  download, SHA-256, staging, the bat launcher templates, cleanup.
- `modules/update_controller.py` — `AppUpdateController`: scheduling, threading,
  defer-while-in-game, fallback layers, post-restart verification.
- `modules/keyquest_app.py` — wires the controller into the app lifecycle.
- `modules/app_paths.py` — `get_app_dir()` (the install dir for a frozen build).
- `modules/version.py` — the single source of truth for the version.
- `tools/build/installer/KeyQuest.iss` — Inno script (per-user, lowest privilege).
- `tools/ship_updates.ps1`, `tools/release.ps1` — local release flow.
- `.github/workflows/release.yml`, `latest-build.yml`, `update-smoke-test.yml` — CI.

## Known failure modes and gotchas

- Improving the updater does not help the jump *to* that release; it helps the
  next jump. Plan updater changes a version ahead.
- Pushing `main` does not publish a release. Only a pushed `vX.Y.Z` tag does.
- Publishing the next release as a pre-release hides it from `/releases/latest`,
  so no installed copy updates. Use the tag flow.
- Asset names are matched exactly first. Renaming `KeyQuestSetup.exe` or
  `KeyQuest-win64.zip` breaks selection unless the loose fallback still matches.
- The portable path replaces files directly and is the one exposed to OneDrive /
  Dropbox sync locks. The installer path (per-user `AppData\Local`) is not.
- Launchers must stay pure `.bat`. Do not reintroduce a PowerShell dependency in
  the apply step.
