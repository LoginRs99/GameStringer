"""Dedicated unit tests for locpipe.adapters:
- po_gettext (PoGettextAdapter extraction, plural forms, fuzzy handling, merge back)
- registry (get_adapter for all supported, static, configurable, unported, and unknown formats)
"""

import pytest
from pathlib import Path
import polib

from locpipe.adapters.po_gettext import (
    PoGettextAdapter,
    _key,
    _nplurals_from_header,
)
from locpipe.adapters.registry import get_adapter
from locpipe.adapters.generic_kv import GenericKVAdapter
from locpipe.adapters.unity import UnityCSVAdapter
from locpipe.adapters.xliff import XLIFFAdapter
from locpipe.adapters.uabea_json import UABEAJsonAdapter
from locpipe.adapters.naninovel import NaninovelAdapter
from locpipe.models import Entry


# ==========================================
# po_gettext Adapter Tests
# ==========================================

def test_po_gettext_helpers():
    # _key without context
    assert _key(None, "Hello") == "Hello"
    assert _key("", "Hello") == "Hello"

    # _key with context
    assert _key("UI", "Save") == "UI\x04Save"

    # _key with plural index
    assert _key(None, "%d items", 0) == "%d items[0]"
    assert _key("Quest", "%d items", 1) == "Quest\x04%d items[1]"

    # _nplurals_from_header
    po = polib.POFile()
    assert _nplurals_from_header(po) == 2  # default fallback

    po.metadata["Plural-Forms"] = "nplurals=1; plural=0;"
    assert _nplurals_from_header(po) == 1

    po.metadata["Plural-Forms"] = "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2);"
    assert _nplurals_from_header(po) == 3


def test_po_gettext_extract_and_merge(tmp_path):
    po_path = tmp_path / "messages.po"

    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": "1.0",
        "Content-Type": "text/plain; charset=utf-8",
        "Plural-Forms": "nplurals=2; plural=(n != 1);",
    }

    # 1. Singular normal
    e1 = polib.POEntry(
        msgid="Start Game",
        msgstr="Játék indítása",
        comment="Start button note",
    )
    po.append(e1)

    # 2. Singular with msgctxt
    e2 = polib.POEntry(
        msgctxt="Menu",
        msgid="Options",
        msgstr="Beállítások",
    )
    po.append(e2)

    # 3. Fuzzy singular (draft)
    e3 = polib.POEntry(
        msgid="Credits",
        msgstr="Stáb (nem végleges)",
        flags=["fuzzy"],
    )
    po.append(e3)

    # 4. Plural entry
    e4 = polib.POEntry(
        msgid="You have %d coin",
        msgid_plural="You have %d coins",
        msgstr_plural={0: "Van %d érméd", 1: "Van %d érméd"},
    )
    po.append(e4)

    # 5. Fuzzy plural entry
    e5 = polib.POEntry(
        msgid="%d gem",
        msgid_plural="%d gems",
        msgstr_plural={0: "gem", 1: "gems"},
        flags=["fuzzy"],
    )
    po.append(e5)

    po.save(str(po_path))

    adapter = PoGettextAdapter()
    extracted = adapter.extract(po_path)

    # Total entries: 1 (e1) + 1 (e2) + 1 (e3) + 2 (e4 plural 0,1) + 2 (e5 plural 0,1) = 7
    assert len(extracted) == 7

    # Verify e1
    ent_start = next(e for e in extracted if e.source == "Start Game")
    assert ent_start.target == "Játék indítása"
    assert ent_start.notes == ["Start button note"]
    assert ent_start.context_key is None
    assert ent_start.extra["is_plural"] is False

    # Verify e2 (with context)
    ent_options = next(e for e in extracted if e.source == "Options")
    assert ent_options.target == "Beállítások"
    assert ent_options.context_key == "Menu"
    assert ent_options.key == "Menu\x04Options"

    # Verify e3 (fuzzy -> target must be empty for re-translation)
    ent_credits = next(e for e in extracted if e.source == "Credits")
    assert ent_credits.target == ""
    assert ent_credits.extra["fuzzy"] is True

    # Verify e4 (plural)
    ent_p0 = next(e for e in extracted if e.key == "You have %d coin[0]")
    assert ent_p0.target == "Van %d érméd"
    assert ent_p0.extra["is_plural"] is True
    assert ent_p0.extra["plural_index"] == 0

    ent_p1 = next(e for e in extracted if e.key == "You have %d coin[1]")
    assert ent_p1.target == "Van %d érméd"
    assert ent_p1.source == "You have %d coins"
    assert ent_p1.extra["plural_index"] == 1

    # Verify e5 (fuzzy plural -> targets empty)
    ent_gems0 = next(e for e in extracted if e.key == "%d gem[0]")
    assert ent_gems0.target == ""
    assert ent_gems0.extra["fuzzy"] is True

    # Now modify extracted entries and merge back
    ent_credits.target = "Készítők"
    ent_gems0.target = "%d drágakő"
    ent_gems1 = next(e for e in extracted if e.key == "%d gem[1]")
    ent_gems1.target = "%d drágakő"

    adapter.merge(po_path, extracted)

    # Reload merged PO and verify
    reloaded_po = polib.pofile(str(po_path))
    reloaded_credits = reloaded_po.find("Credits")
    assert reloaded_credits.msgstr == "Készítők"
    # Fuzzy flag must have been cleared
    assert "fuzzy" not in reloaded_credits.flags

    reloaded_gems = reloaded_po.find("%d gem")
    assert reloaded_gems.msgstr_plural[0] == "%d drágakő"
    assert reloaded_gems.msgstr_plural[1] == "%d drágakő"
    assert "fuzzy" not in reloaded_gems.flags


# ==========================================
# Registry Tests
# ==========================================

def test_registry_get_adapter_all_formats():
    # Static adapters
    assert isinstance(get_adapter("generic_kv"), GenericKVAdapter)
    assert isinstance(get_adapter("po_gettext"), PoGettextAdapter)
    assert isinstance(get_adapter("ue4_5_po"), PoGettextAdapter)
    assert isinstance(get_adapter("xliff"), XLIFFAdapter)
    assert isinstance(get_adapter("weblate_xliff"), XLIFFAdapter)

    # Configurable adapters
    assert isinstance(get_adapter("naninovel", {}), NaninovelAdapter)
    assert isinstance(get_adapter("uabea_json", {}), UABEAJsonAdapter)
    assert isinstance(get_adapter("bayonetta_json", {}), UABEAJsonAdapter)

    unity_adapter = get_adapter(
        "unity",
        {
            "target_column_names": ["Magyar"],
            "source_column_names": ["English"],
            "max_length_column_names": ["Limit"],
            "source_lang": "en",
            "target_lang": "hu",
        }
    )
    assert isinstance(unity_adapter, UnityCSVAdapter)
    assert unity_adapter.target_column_names == ["Magyar"]

    # Not yet ported formats raise NotImplementedError
    with pytest.raises(NotImplementedError, match="'renpy' adapter isn't ported yet"):
        get_adapter("renpy")

    with pytest.raises(NotImplementedError, match="'ue3' adapter isn't ported yet"):
        get_adapter("ue3")

    # Unknown format raises ValueError with known list
    with pytest.raises(ValueError, match="Unknown format 'invalid_fmt'"):
        get_adapter("invalid_fmt")
