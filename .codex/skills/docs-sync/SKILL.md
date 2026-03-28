---
name: docs-sync
description: Use when a KeyQuest change affects behavior, tooling, release flow, or maintainer workflow and the repo documentation needs to stay synchronized. Verifies README, changelog, handoff, and release notes expectations for this repo.
---

# Docs Sync

Use this skill after meaningful repo changes.

## Workflow
1. Identify whether the change is:
   - user-visible behavior
   - developer tooling or workflow
   - release-only
2. Update the right docs:
   - user-visible behavior: `README.html`, `docs/dev/CHANGELOG.md`
   - release work: `docs/user/WHATS_NEW.md`, `docs/dev/HANDOFF.md`
   - developer workflow or repo tooling: `docs/dev/CHANGELOG.md`, and `docs/dev/HANDOFF.md` if the guidance will matter in future sessions
3. Keep developer docs technical and user docs plain-language.
4. Verify links, commands, and file paths still match the current repo layout.

## Notes
- `README.md` is a pointer. The user-facing guide is `README.html`.
- Do not put code/file-name detail into `docs/user/WHATS_NEW.md`.

