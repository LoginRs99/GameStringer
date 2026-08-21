"""
Tests for Hungarian translation accuracy improvements:
1. Sibling character limit extraction in uabea_json adapter
2. Hungarian spellcheck validator (validate_hu_spelling)
3. Suffix-near-placeholder heuristic in confidence.py
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from locpipe.adapters.uabea_json import UABEAJsonAdapter
from locpipe.confidence import confidence_flags, score, has_suffix_near_placeholder
from locpipe.models import Entry, ValidationResult
from locpipe.validators.validate_hu_spelling import validate_file as validate_hu_spelling_file


def test_uabea_json_sibling_char_limit_extraction(tmp_path: Path):
    adapter = UABEAJsonAdapter()
    file_path = tmp_path / "test_asset.json"

    # Fixture with sibling m_CharacterLimit
    data_with_limit = {
        "m_Name": "InputName",
        "m_Text": "Some string with limit",
        "m_CharacterLimit": 20
    }
    file_path.write_text(json.dumps(data_with_limit), encoding="utf-8")

    entries = adapter.extract(file_path)
    assert len(entries) == 1
    assert entries[0].source == "Some string with limit"
    assert entries[0].max_length == 20


def test_uabea_json_sibling_less_leaves_max_length_none(tmp_path: Path):
    adapter = UABEAJsonAdapter()
    file_path = tmp_path / "test_asset.json"

    # Fixture without m_CharacterLimit
    data_without_limit = {
        "m_Name": "InputName",
        "m_Text": "Some string without limit"
    }
    file_path.write_text(json.dumps(data_without_limit), encoding="utf-8")

    entries = adapter.extract(file_path)
    assert len(entries) == 1
    assert entries[0].source == "Some string without limit"
    assert entries[0].max_length is None


def test_hu_spelling_validator_flags_misspelling(tmp_path: Path):
    file_path = tmp_path / "test_hu.json"
    data = {
        "text": "Ez egy hibasrosszszo123 ami nem létezik"
    }
    file_path.write_text(json.dumps(data), encoding="utf-8")

    critical, major, minor, info = validate_hu_spelling_file(str(file_path), target_lang="hu")
    assert len(critical) == 0
    assert len(major) == 0
    assert len(minor) >= 1
    assert any("hibasrosszszo" in m for m in minor)


def test_hu_spelling_validator_ignores_glossary_words(tmp_path: Path):
    file_path = tmp_path / "test_hu.json"
    data = {
        "text": "Ez egy hibasrosszszo123 ami a szótárban van"
    }
    file_path.write_text(json.dumps(data), encoding="utf-8")

    glossary = [("FakeWord", "hibasrosszszo123")]
    critical, major, minor, info = validate_hu_spelling_file(str(file_path), glossary_entries=glossary, target_lang="hu")
    assert len(critical) == 0
    assert len(major) == 0
    assert len(minor) == 0


def test_hu_spelling_validator_ignores_protected_tokens(tmp_path: Path):
    file_path = tmp_path / "test_hu.json"
    data = {
        "text": "Találtál egy {custom_xyz_token} tárgyat @special_buff_tag@ hatással."
    }
    file_path.write_text(json.dumps(data), encoding="utf-8")

    critical, major, minor, info = validate_hu_spelling_file(str(file_path), target_lang="hu")
    assert len(critical) == 0
    assert len(major) == 0
    assert len(minor) == 0


def test_suffix_near_placeholder_confidence_flag():
    entry = Entry(
        file="test.json",
        key="k1",
        source="You found the {item}.",
        target="A {item}t megtaláltad",
    )
    assert has_suffix_near_placeholder(entry.target) is True

    flags = confidence_flags(entry)
    assert any("placeholder is immediately followed by a Hungarian suffix" in f for f in flags)
    assert score(entry, ValidationResult(entry_key="k1")) < 1.0


def test_suffix_near_placeholder_clean_spacing_not_flagged():
    entry = Entry(
        file="test.json",
        key="k1",
        source="You found the {item}.",
        target="A {item} van a kezedben",
    )
    assert has_suffix_near_placeholder(entry.target) is False
    flags = confidence_flags(entry)
    assert not any("placeholder is immediately followed by a Hungarian suffix" in f for f in flags)
