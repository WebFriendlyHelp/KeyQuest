# Accessibility

KeyQuest is a typing game built first for screen reader, keyboard-only, and low-vision players. If any part of it can't be reached that way, that's a bug and I want to hear about it.

## Supported environments

- Windows 10 and Windows 11.
- NVDA and JAWS, through the Tolk screen reader library. Speech and braille both go to your screen reader.
- Narrator, and no screen reader at all. When neither NVDA nor JAWS is running, KeyQuest speaks through Windows' built-in SAPI voices.

## What is built in

- Everything is played from the keyboard. Nothing needs a mouse.
- Font Size in the Options menu goes from 100% to 200%. The Auto setting follows your Windows display scaling.
- The Auto theme follows Windows High Contrast when you have it turned on.
- Each keystroke gets a visual flash as well as speech.
- The full user guide is plain HTML you can read in a browser or open from inside the game.

These are tracked against WCAG 2.2 AA in docs/user/ACCESSIBILITY_COMPLIANCE_SUMMARY.md. That's a working record, not a formal certification.

## Known barriers

KeyQuest draws its own interface with Pygame instead of using standard Windows controls. That means your screen reader's object navigation, review cursor, and OCR have nothing to read. Everything you hear is sent by KeyQuest itself. If something on screen isn't spoken, it's missing from KeyQuest's speech, and that's worth reporting.

## Reporting a barrier

Open an issue with the bug report form and add the accessibility label, plus screen reader, keyboard, or low vision if one fits. Tell me which screen reader and version you use, what you were doing, and what you heard or didn't hear.

You can also email help@webfriendlyhelp.com if you'd rather not post publicly.

## Contributing

CONTRIBUTING.md covers setup. Before a change touches menus, dialogs, or speech, run the checks in docs/dev/SCREEN_READER_SMOKE_TESTS.md. A change that breaks speech or keyboard flow will be asked to fix that before it's merged.
