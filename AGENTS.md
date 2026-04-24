## Session Start
Read `docs/dev/HANDOFF.md` and the top entry of `docs/dev/CHANGELOG.md` only when:
- Making code changes
- Preparing a release
- Investigating a bug

## Default Behavior
- Keep answers concise unless debugging or asked for detail.
- When troubleshooting, use step-by-step diagnosis before solutions.
- Include PowerShell commands in code blocks when giving instructions.
- Avoid mouse-only instructions unless requested.
- Prefer screen-reader-friendly answers: short paragraphs, flat lists, descriptive links, and no decorative symbols.
- Put the result before supporting detail to reduce listening time in NVDA and JAWS.

## Accessibility
- Always consider screen reader flow and keyboard navigation.
- Prefer simple, predictable layouts.
- Use WCAG 2.2 rules when working on UI or accessibility.
- Verify UI work against keyboard-only use, accessible names, focus order, and expected screen reader announcements.
- Prefer semantic structure over ARIA; add ARIA only when native controls cannot express the behavior.
- For NVDA-specific behavior, check current NV Access documentation from `nvaccess.org` or `download.nvaccess.org`.

## KeyQuest Rules
- Prefer single-file `index.html` outputs when producing web-based reports or artifacts.
- Maintain keyboard-first interaction design.

## Git Workflow
- Prefer direct commits with clear messages.
- Include git commands when suggesting changes.

## Documentation and Research
- Use Context7 only when working with an unfamiliar library, asked for docs, or version-specific behavior matters.
