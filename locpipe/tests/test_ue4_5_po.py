"""Tests for ue4_5_po: the Unreal Localization Dashboard .po format, which
aliases straight to PoGettextAdapter for extract/merge (see adapters/
registry.py -- standard gettext structure, no UE-specific adapter code
needed) plus its own validator layer for the {Arg}|plural/gender/ordinal(...)
argument-modifier syntax that IS Unreal-specific (validate_ue4_5_po.py).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from locpipe.adapters.po_gettext import PoGettextAdapter
from locpipe.adapters.registry import get_adapter
from locpipe.validators.registry import run_validator
from locpipe.validators.validate_ue4_5_po import check_entry, extract_modifier_clauses

_SAMPLE_UE_PO = '''msgid ""
msgstr ""
"Project-Id-Version: Game\\n"
"Language: hu\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

#. Key:\tItemCountMsg
msgctxt "UI.Inventory,ItemCountMsg"
msgid "You have {Count}|plural(one=You have {Count} item,other=You have {Count} items)."
msgstr ""

#. Key:\tGreetGender
msgctxt "Dialogue.NPC,GreetGender"
msgid "{Gender}|gender(He,She,They) greets you warmly."
msgstr ""

#. Key:\tPlainButton
msgctxt "UI.MainMenu,PlainButton"
msgid "Start Game"
msgstr ""
'''


def _write_sample(tmp_path: Path) -> Path:
    p = tmp_path / "Game.po"
    p.write_text(_SAMPLE_UE_PO, encoding="utf-8")
    return p


# --- extract_modifier_clauses / check_entry: pure logic, real UE syntax ---


def test_extract_modifier_clauses_plural_ordinal_gender():
    plural = extract_modifier_clauses("{Count}|plural(one=X,other=Y)")
    assert len(plural) == 1
    assert plural[0].arg_name == "Count"
    assert plural[0].modifier == "plural"
    assert plural[0].keys == ["one", "other"]

    ordinal = extract_modifier_clauses("{Number}{Number}|ordinal(one=st,two=nd,few=rd,other=th)!")
    assert ordinal[0].keys == ["one", "two", "few", "other"]

    gender = extract_modifier_clauses("{Gender}|gender(He,She,They) said hello.")
    assert gender[0].modifier == "gender"
    assert len(gender[0].keys) == 3  # positional, unnamed -- just counted


def test_extract_modifier_clauses_respects_quoted_commas():
    # A comma INSIDE a quoted clause value must not be mistaken for the
    # top-level argument separator.
    text = '{x}|plural(one="big \\"quoted\\" apple, right?",other="apples, right?")'
    clauses = extract_modifier_clauses(text)
    assert len(clauses) == 1
    assert clauses[0].keys == ["one", "other"]


def test_extract_modifier_clauses_ignores_plain_braces():
    # A bare {Name} with no |modifier( suffix isn't this adapter's concern
    # (validate_po_gettext.py's own placeholder check already covers it).
    assert extract_modifier_clauses("Hello, {PlayerName}!") == []


def test_check_entry_flags_completely_stripped_modifier():
    src = "You have {Count}|plural(one=You have {Count} item,other=You have {Count} items)."
    tgt = "Neked van {Count} tárgyad."  # modifier gone entirely
    critical, major = check_entry(src, tgt)
    assert len(critical) == 1
    assert "missing from the translation" in critical[0]
    assert major == []


def test_check_entry_flags_missing_plural_key():
    src = "You have {Count}|plural(one=X,other=Y)."
    tgt = "{Count}|plural(one=Z)."  # "other" branch dropped
    critical, major = check_entry(src, tgt)
    assert len(critical) == 1
    assert "'other'" in critical[0]


def test_check_entry_flags_gender_form_count_mismatch():
    src = "{Gender}|gender(He,She,They) greets you."
    tgt = "{Gender}|gender(Ő) köszönt."  # 3 forms collapsed into 1
    critical, major = check_entry(src, tgt)
    assert critical == []
    assert len(major) == 1
    assert "3 form(s)" in major[0] and "1 in the translation" in major[0]


def test_check_entry_silent_when_correctly_preserved():
    src = "{Gender}|gender(He,She,They) greets you. {Count}|plural(one=X,other=Y)."
    tgt = "{Gender}|gender(Ő,Ő,Ők) köszönt. {Count}|plural(one=Z,other=W)."
    critical, major = check_entry(src, tgt)
    assert critical == [] and major == []


def test_check_entry_ignores_plain_text_with_no_modifiers():
    critical, major = check_entry("Start Game", "Játék indítása")
    assert critical == [] and major == []


# --- Adapter registry: ue4_5_po aliases to PoGettextAdapter ---


def test_ue4_5_po_aliases_to_po_gettext_adapter():
    adapter = get_adapter("ue4_5_po", {})
    assert isinstance(adapter, PoGettextAdapter)


def test_ue4_5_po_extract_uses_msgctxt_as_context_key(tmp_path: Path):
    p = _write_sample(tmp_path)
    adapter = get_adapter("ue4_5_po", {})
    entries = adapter.extract(p)
    assert len(entries) == 3
    context_keys = {e.context_key for e in entries}
    assert "UI.Inventory,ItemCountMsg" in context_keys
    assert "Dialogue.NPC,GreetGender" in context_keys


def test_ue4_5_po_merge_round_trip_preserves_comments(tmp_path: Path):
    p = _write_sample(tmp_path)
    adapter = get_adapter("ue4_5_po", {})
    entries = adapter.extract(p)
    for e in entries:
        e.target = f"[HU] {e.source}"
    adapter.merge(p, entries)

    content = p.read_text(encoding="utf-8")
    assert "Key:\tItemCountMsg" in content  # extracted comment survived the round trip
    assert "[HU]" in content


# --- Validator registry: run_validator("ue4_5_po", ...) end to end ---


def test_run_validator_ue4_5_po_catches_broken_modifier(tmp_path: Path):
    p = _write_sample(tmp_path)
    adapter = get_adapter("ue4_5_po", {})
    entries = adapter.extract(p)
    by_ctx = {e.context_key: e for e in entries}
    by_ctx["UI.Inventory,ItemCountMsg"].target = "Neked van {Count} tárgyad."  # modifier stripped
    by_ctx["Dialogue.NPC,GreetGender"].target = "{Gender}|gender(Ő,Ő,Ők) köszönt."  # fine
    by_ctx["UI.MainMenu,PlainButton"].target = "Játék indítása"
    adapter.merge(p, entries)

    result = run_validator("ue4_5_po", p, entry_key="Game.po")
    assert len(result.critical) == 1
    assert "missing from the translation" in result.critical[0].message


def test_run_validator_ue4_5_po_clean_when_all_correct(tmp_path: Path):
    p = _write_sample(tmp_path)
    adapter = get_adapter("ue4_5_po", {})
    entries = adapter.extract(p)
    by_ctx = {e.context_key: e for e in entries}
    by_ctx["UI.Inventory,ItemCountMsg"].target = "{Count}|plural(one=Van {Count} tárgyad,other=Van {Count} tárgyad)."
    by_ctx["Dialogue.NPC,GreetGender"].target = "{Gender}|gender(Ő,Ő,Ők) melegen köszönt."
    by_ctx["UI.MainMenu,PlainButton"].target = "Játék indítása"
    adapter.merge(p, entries)

    result = run_validator("ue4_5_po", p, entry_key="Game.po")
    assert result.critical == []
    assert result.major == []


def test_run_validator_po_gettext_dispatch_does_not_crash(tmp_path: Path):
    """Regression check: validate_po_gettext.validate_file() used to return
    a 3-tuple while the registry unpacked 4 -- this crashed the FIRST time
    anything actually called run_validator("po_gettext", ...) end to end."""
    p = _write_sample(tmp_path)
    adapter = get_adapter("po_gettext", {})
    entries = adapter.extract(p)
    for e in entries:
        e.target = e.source
    adapter.merge(p, entries)

    result = run_validator("po_gettext", p, entry_key="Game.po")
    assert isinstance(result.critical, list)
    assert isinstance(result.minor, list)


# --- CategoryRule.match_source_regex: routing by string content, e.g. to
# flag UE's argument-modifier syntax for its own category/batch handling ---


def test_category_rule_match_source_regex():
    from locpipe.config import CategoryRule
    from locpipe.models import Entry

    rule = CategoryRule(name="format_sensitive", match_source_regex=r"\|(plural|gender|ordinal)\(")
    modifier_entry = Entry(file="f", key="k1", source="{Count}|plural(one=X,other=Y)", target="")
    plain_entry = Entry(file="f", key="k2", source="Plain text here", target="")

    assert rule.matches(modifier_entry) is True
    assert rule.matches(plain_entry) is False


def test_category_rule_existing_match_types_unaffected_by_source_regex_addition():
    from locpipe.config import CategoryRule
    from locpipe.models import Entry

    rule = CategoryRule(name="dialogue", match_speaker_present=True)
    with_speaker = Entry(file="f", key="k3", source="Hi", target="", speaker="Kael")
    without_speaker = Entry(file="f", key="k4", source="Hi", target="", speaker=None)

    assert rule.matches(with_speaker) is True
    assert rule.matches(without_speaker) is False
