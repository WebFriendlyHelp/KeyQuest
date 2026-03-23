# KeyQuest Release Policy

Use two different commands for two different goals.

## Update Git

Meaning:

- commit and push the current repo changes
- update GitHub Pages if the pushed files affect the guide or changelog
- do not bump the app version
- do not create a release tag
- do not trigger in-app self-update

Use this for:

- small docs changes
- sentence wording changes
- guide/blog cleanup
- internal notes
- work that is not ready to ship as a user-facing update

## Ship Updates

Meaning:

- this means publish a real release, not just commit locally
- bump the app version
- require a plain-language update in `docs/user/WHATS_NEW.md`
  - use one heading per date; append same-day updates under the existing date heading
- require the top `docs/user/WHATS_NEW.md` version entry to match `modules/version.py`
- rebuild the Pages site
- rebuild the local EXE, portable ZIP, and installer
- commit and push `main`
- create and push the matching version tag
- trigger the GitHub Release workflow
- wait for the GitHub Release workflow to finish successfully
- verify that the published GitHub Release contains the installer, portable ZIP, and both `.sha256` sidecars
- wait for the post-release updater smoke test job in `release.yml` to finish successfully
- make the new release visible to the in-app updater

Use this for:

- a real user-facing update
- a fix or improvement you want installed copies to receive
- anything that should publish new installer and portable downloads

## Automatic Version Bump

The helper script for `ship updates` uses a conservative automatic rule:

- `patch`
  - docs changes
  - sentence file changes
  - guide/changelog/blog wording changes
  - small user-facing polish
- `minor`
  - app code changes under `modules/`
  - game changes under `games/`
  - release/build workflow changes
  - anything outside the normal docs/content buckets
- `major`
  - never chosen automatically
  - use only when you explicitly want a major release

In practice:

- most shipped KeyQuest updates should be `patch`
- `minor` should be used for meaningful new features or bigger behavior changes
- `major` should be rare

## Commands

Plain push:

```powershell
git add -A
git commit -m "Your message"
git push origin main
```

Ship a release with automatic bump selection:

```powershell
powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1
```

Ship a release with an explicit bump:

```powershell
powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1 -Bump patch
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File tools/ship_updates.ps1 -Bump minor
```

## Notes

- `tools/release.ps1` is still the core release script.
- `tools/ship_updates.ps1` is a wrapper that chooses and applies the version bump before calling `tools/release.ps1`.
- `tools/release.ps1` now automates the main release checks: local tests, local builds, release publication wait, and published asset verification. The post-release updater smoke test now runs as a second job inside `release.yml`, so the release workflow itself stays the single GitHub gate.
- If version metadata is stale or mismatched, the release script must fail before publishing.
- Release pushes are normal fast-forward pushes only. Do not use force-push, branch deletion, or tag rewrite workflows for this repo.
- The in-app updater only sees a new update after a new GitHub Release exists.
- Pushing `main` alone is not enough for self-update.
