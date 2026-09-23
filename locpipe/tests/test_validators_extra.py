import json
import pytest
from pathlib import Path

from locpipe.validators.validate_uabea_json import validate_file as validate_uabea
from locpipe.validators.validate_generic_kv import validate_file as validate_kv
from locpipe.validators.validate_po_gettext import validate_file as validate_po
from locpipe.validators.validate_weblate_xliff import validate_file as validate_xliff


# ==========================================
# UABEA JSON Validator Tests
# ==========================================

def test_uabea_missing_and_invalid_json(tmp_path):
    # 1. Non-existent file
    c, m, mi, inf = validate_uabea(str(tmp_path / "missing.json"))
    assert len(c) == 1
    assert "not found" in c[0]

    # 2. Invalid syntax
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{broken json", encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(bad_file))
    assert len(c) == 1
    assert "Invalid JSON syntax" in c[0]

    # 3. Invalid root type (not dict or list)
    str_file = tmp_path / "str.json"
    str_file.write_text('"just a string"', encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(str_file))
    assert len(c) == 1
    assert "Expected JSON object or array" in c[0]


def test_uabea_csv_script_and_array(tmp_path):
    # 1. Valid CSV-in-m_Script
    csv_file = tmp_path / "csv_valid.json"
    data = {
        "m_Name": "DialogueText",
        "m_Script": "KEY,EN,HU\nstart_btn,Start,Indítás\nquit_btn,Quit,\n"
    }
    csv_file.write_text(json.dumps(data), encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(csv_file))
    assert len(c) == 0
    # Missing target for quit_btn
    assert any("missing target translation" in item for item in mi)

    # 2. Empty m_Script
    empty_script = tmp_path / "empty_script.json"
    empty_script.write_text(json.dumps({"m_Script": ""}), encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(empty_script))
    assert any("m_Script is empty" in item for item in inf)

    # 3. Array of objects
    arr_file = tmp_path / "array_uabea.json"
    arr_data = [
        {"m_Name": "Asset1", "m_Script": "EN,HU\nHello,Szia\n"},
        {"m_Name": "Asset2", "some_text": "Sample"}
    ]
    arr_file.write_text(json.dumps(arr_data), encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(arr_file))
    assert len(c) == 0

    # 4. Empty array
    empty_arr = tmp_path / "empty_arr.json"
    empty_arr.write_text("[]", encoding="utf-8")
    c, m, mi, inf = validate_uabea(str(empty_arr))
    assert any("array is empty" in item for item in inf)


# ==========================================
# Generic KV Validator Tests
# ==========================================

def test_generic_kv_validator(tmp_path):
    # 1. Missing file
    c, m, mi, inf = validate_kv(str(tmp_path / "missing.json"))
    assert len(c) == 1

    # 2. Invalid structure (not list)
    not_list = tmp_path / "not_list.json"
    not_list.write_text(json.dumps({"id": "1"}), encoding="utf-8")
    c, m, mi, inf = validate_kv(str(not_list))
    assert len(c) == 1
    assert "tombnek" in c[0].lower() or "array" in c[0].lower() or "list" in c[0].lower()

    # 3. Valid batch with token mismatch & duplicate id
    batch_file = tmp_path / "batch.json"
    batch_data = [
        {"id": "entry_1", "source": "Hello {user}, you have {coins} coins!", "target": "Szia {user}!"},  # missing {coins}
        {"id": "entry_1", "source": "Duplicate", "target": "Duplikátum"},  # duplicate id
        {"id": "entry_2", "source": "Save game", "target": ""},  # empty target
        {"id": "entry_3", "source": "Select {count, plural, one{# item} other{# items}}", "target": "Válassz ki {count} elemet"}
    ]
    batch_file.write_text(json.dumps(batch_data), encoding="utf-8")
    c, m, mi, inf = validate_kv(str(batch_file))
    # Duplicate ID is critical
    assert any("duplikalt" in err.lower() for err in c)
    # Placeholder set mismatch is major
    assert any("placeholder-keszlet" in err.lower() for err in m)
    # Empty target is informational
    assert any("target" in err.lower() and "ures" in err.lower() for err in inf)


# ==========================================
# GNU Gettext PO Validator Tests
# ==========================================

def test_po_gettext_validator(tmp_path):
    # 1. Missing file
    c, m, mi, inf = validate_po(str(tmp_path / "missing.po"))
    assert len(c) == 1

    # 2. Valid PO with singular, plural, and fuzzy entries
    po_file = tmp_path / "test.po"
    po_content = r'''msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#, fuzzy
msgid "Hello World"
msgstr "Szia Világ"

msgid "You have %d items"
msgid_plural "You have %d items"
msgstr[0] "Van %d elemed"
msgstr[1] "Van elemed"

msgid "Missing translation"
msgstr ""

msgid "Duplicate"
msgstr "Első"

msgid "Duplicate"
msgstr "Második"
'''
    po_file.write_text(po_content, encoding="utf-8")
    c, m, mi, inf = validate_po(str(po_file))
    # Duplicate msgid in same context is critical
    assert any("duplikalt" in err.lower() for err in c)
    # Plural token mismatch (%d missing in msgstr[1]) is major
    assert any("token" in err.lower() or "%d" in err for err in m)
    # Fuzzy entry is reported in info
    assert any("fuzzy" in err for err in inf)
    # Empty translation is reported in info
    assert any("ures" in err.lower() for err in inf)


# ==========================================
# Weblate XLIFF Validator Tests
# ==========================================

def test_weblate_xliff_validator(tmp_path):
    # 1. Missing file
    c, m, mi, inf = validate_xliff(str(tmp_path / "missing.xlf"))
    assert len(c) == 1

    # 2. Bad XML
    bad_xml = tmp_path / "bad.xlf"
    bad_xml.write_text("<xliff><unclosed>", encoding="utf-8")
    c, m, mi, inf = validate_xliff(str(bad_xml))
    assert len(c) == 1
    assert "XML" in c[0]

    # 3. Valid XLIFF with curly brace mismatch and %s mismatch
    xlf_file = tmp_path / "valid.xlf"
    xlf_content = """<?xml version="1.0" encoding="utf-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.1" version="1.1">
  <file original="UI.po" source-language="en" target-language="hu" datatype="po">
    <body>
      <trans-unit id="unit_1">
        <source>Welcome {name}, level %d!</source>
        <target>Üdvözöllek {name, szint %s!</target>
      </trans-unit>
      <trans-unit id="unit_1">
        <source>Duplicate</source>
        <target>Duplikátum</target>
      </trans-unit>
      <trans-unit id="unit_2">
        <source>Untranslated</source>
        <target></target>
      </trans-unit>
    </body>
  </file>
</xliff>
"""
    xlf_file.write_text(xlf_content, encoding="utf-8")
    c, m, mi, inf = validate_xliff(str(xlf_file))
    # Duplicate unit ID is critical
    assert any("duplikalt" in err.lower() for err in c)
    # Brace count mismatch / % token mismatch is major
    assert any("elter" in err.lower() or "token" in err.lower() for err in m)
    # Untranslated is informational
    assert any("ures" in err.lower() for err in inf)
