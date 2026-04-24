from pathlib import Path


def test_builtin_spanish_sentences_cover_english_keyboard_compose_characters():
    text = Path("Sentences/Spanish Sentences.txt").read_text(encoding="utf-8")

    for char in ("á", "é", "í", "ó", "ú", "ñ", "ü", "¿", "¡"):
        assert char in text
