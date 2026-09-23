import pytest
from pathlib import Path
from locpipe.character_voices import load_character_voice_rows, prune_character_voices_for_batch


def test_load_character_voice_rows_none_or_missing(tmp_path):
    assert load_character_voice_rows(None) == ([], {})
    assert load_character_voice_rows(tmp_path / "nonexistent.md") == ([], {})


def test_load_character_voice_rows_valid(tmp_path):
    doc = tmp_path / "character-voices.md"
    content = """# Character Voice Bible
Introductory notes for translators.

| Character | Register | Tone / Personality | Special Rules |
|---|---|---|---|
| Aoi | informal | Energetic and direct | Uses 'te' |
| Minami | formal | Polite, reserved | Uses 'ön' |
| Ágnes | informal | Sarcastic | Accented name |
| 葵 | informal | Japanese speaker | Asian glyphs |
"""
    doc.write_text(content, encoding="utf-8")

    preamble, rows = load_character_voice_rows(doc)
    assert len(preamble) >= 4  # Title, prose, header, separator
    assert any("Character Voice Bible" in p for p in preamble)
    assert any("|---|---|" in p for p in preamble)
    assert "Aoi" in rows
    assert "Minami" in rows
    assert "Ágnes" in rows
    assert "葵" in rows
    assert "Character" not in rows


def test_prune_character_voices_empty():
    assert prune_character_voices_for_batch([], {}, set()) == "(no character voice bible provided)"
    preamble = ["# Voice Bible", "| Character | Role |", "|---|---|"]
    assert prune_character_voices_for_batch(preamble, {}, {"Aoi"}) == "\n".join(preamble)


def test_prune_character_voices_exact_and_normalized():
    preamble = ["# Voice Bible", "| Character | Register |", "|---|---|"]
    rows = {
        "Aoi": "| Aoi | informal |",
        "Minami": "| Minami | formal |",
        "Kagura-San": "| Kagura-San | neutral |",
        "Ágnes": "| Ágnes | informal |",
        "葵": "| 葵 | informal |",
    }

    # 1. Exact match
    res1 = prune_character_voices_for_batch(preamble, rows, {"Aoi"})
    assert "| Aoi | informal |" in res1
    assert "| Minami |" not in res1

    # 2. Normalized match (casing, hyphens)
    res2 = prune_character_voices_for_batch(preamble, rows, {"kagurasan"})
    assert "| Kagura-San | neutral |" in res2
    assert "| Aoi |" not in res2

    # 3. Unicode Hungarian accented match
    res3 = prune_character_voices_for_batch(preamble, rows, {"ágnes"})
    assert "| Ágnes | informal |" in res3

    # 4. Unicode Asian glyph match
    res4 = prune_character_voices_for_batch(preamble, rows, {"葵"})
    assert "| 葵 | informal |" in res4

    # 5. Multiple speakers
    res5 = prune_character_voices_for_batch(preamble, rows, {"Aoi", "Minami"})
    assert "| Aoi |" in res5
    assert "| Minami |" in res5
    assert "| Ágnes |" not in res5

    # 6. Unknown speaker fallback
    res6 = prune_character_voices_for_batch(preamble, rows, {"UnknownNPC"})
    assert "| Aoi |" not in res6
    assert "\n".join(preamble) in res6
