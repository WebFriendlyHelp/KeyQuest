# KeyQuest Instructions

## Start Here

- For code changes, releases, or bug investigation, read `docs/dev/HANDOFF.md` and the newest entry in `docs/dev/CHANGELOG.md`.
- Read `CLAUDE.md` for architecture, commands, and project conventions. Treat `modules/version.py` as the version source of truth.

## Project Rules

- Preserve prompt-free, windowless updater behavior and the documented release workflow.
- Accessibility is required: keyboard access, predictable focus, concise announcements, and explicit screen-reader shutdown on app exit. WCAG 2.2 AA is the minimum bar for any user-facing UI.
- Prefer semantic structure over ARIA; add ARIA only when native controls cannot express the behavior.
- For NVDA-specific behavior, check current NV Access documentation from `nvaccess.org` or `download.nvaccess.org`. Do not recite it from memory.
- Put the result before supporting detail, in answers and in app output, to cut listening time.
- Use existing helpers and documented Python environment. Run focused tests first and the documented full suite before a release.
- Do not edit generated `dist/` copies as source. Update source and rebuild.
- Do not publish a release unless the user explicitly requests it. When the user says `ship`, follow the documented release workflow and verify the tag, assets, and post-release checks.
- Update existing handoff, changelog, and user documentation when shipped behavior changes.
