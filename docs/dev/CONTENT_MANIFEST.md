# Sentence Content Manifest

KeyQuest now treats built-in practice topics as data instead of hard-coded lists.

## Files

- `Sentences/manifest.json`: canonical built-in topic list
- `docs/dev/schemas/sentences-manifest.schema.json`: JSON schema for the manifest
- `modules/sentences_manager.py`: runtime loader and fallback logic

## What belongs in the manifest

Each topic entry should define:

- `name`: canonical topic key used by the app
- `file`: backing `.txt` file inside `Sentences/`
- `display_name`: optional UI label override
- `explanation`: optional short description for menus and docs

The manifest also defines `speed_test_file`, which keeps the speed-test pool configurable without changing Python code.

## Fallback behavior

- If `Sentences/manifest.json` is missing or invalid, the app falls back to the built-in default manifest in `modules/sentences_manager.py`.
- Extra `.txt` files dropped into `Sentences/` still appear as practice topics even if they are not yet listed in the manifest.
- Manifest entries win when both a manifest mapping and an inferred filename are available.

## Contributor guidance

- Add new built-in topics to `Sentences/manifest.json` and commit the matching `.txt` file in `Sentences/`.
- Keep display names and explanations concise; they are spoken aloud in menu flows.
- If the shape changes, update the schema and `modules/sentences_manager.py` together.
