import pytest
from locpipe.models import Entry
from locpipe.context_key import derive_context_key, build_tm_key


def test_derive_context_key_explicit_speaker():
    entry = Entry(file="test.txt", key="line_01", source="Hello", target="", speaker="Aoi")
    key, via = derive_context_key(entry, {"Aoi", "Minami"})
    assert key == "Aoi"
    assert via == "speaker_field"


def test_derive_context_key_notes_match():
    entry = Entry(
        file="test.txt",
        key="line_01",
        source="Hello",
        target="",
        notes=["Spoken by Minami in the garden", "Important context"]
    )
    key, via = derive_context_key(entry, {"Aoi", "Minami"})
    assert key == "Minami"
    assert via == "notes_match"


def test_derive_context_key_pattern_match_and_boundary_safety():
    characters = {"Al", "Tom", "Sam", "Minami"}

    # 1. Genuine delimiter matches
    entry1 = Entry(file="test.txt", key="dialogue_al_greeting", source="Hi", target="")
    key1, via1 = derive_context_key(entry1, characters)
    assert key1 == "Al"
    assert via1 == "key_pattern"

    entry2 = Entry(file="test.txt", key="scene:tom:intro", source="Hi", target="")
    key2, via2 = derive_context_key(entry2, characters)
    assert key2 == "Tom"
    assert via2 == "key_pattern"

    # 2. False-positive prevention: substring inside unrelated words
    entry_false_al = Entry(file="test.txt", key="dialogue_talk_general", source="Hi", target="")
    key_fa, via_fa = derive_context_key(entry_false_al, characters)
    assert key_fa is None
    assert via_fa == "none"

    entry_false_tom = Entry(file="test.txt", key="ui_custom_button", source="Click", target="")
    key_ft, via_ft = derive_context_key(entry_false_tom, characters)
    assert key_ft is None
    assert via_ft == "none"

    entry_false_sam = Entry(file="test.txt", key="ui_sample_card", source="Item", target="")
    key_fs, via_fs = derive_context_key(entry_false_sam, characters)
    assert key_fs is None
    assert via_fs == "none"


def test_derive_context_key_none():
    entry = Entry(file="test.txt", key="ui_btn_cancel", source="Cancel", target="", notes=["UI button"])
    key, via = derive_context_key(entry, {"Aoi", "Minami"})
    assert key is None
    assert via == "none"


def test_build_tm_key():
    k1 = build_tm_key("hash123", "dialogue", "Aoi")
    assert k1 == "hash123:dialogue:Aoi"

    k2 = build_tm_key("hash123", "ui", None)
    assert k2 == "hash123:ui:-"

    k3 = build_tm_key("hash123", "ui", "")
    assert k3 == "hash123:ui:-"
