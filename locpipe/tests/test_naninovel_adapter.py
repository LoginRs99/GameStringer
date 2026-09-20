"""Unit tests for the Naninovel format adapter and validator."""

import tempfile
from pathlib import Path

from locpipe.adapters.registry import get_adapter
from locpipe.adapters.naninovel import NaninovelAdapter
from locpipe.models import Entry
from locpipe.validators.validate_naninovel import validate_file

_SAMPLE_MANAGED_TEXT = """\


; No
Confirmation.No: 

; Yes
Confirmation.Yes: 

; Congratulations! You've completed the main story!<br>You can keep playing.
FinalEnding.ContinuePlaying: 
"""

_SAMPLE_SCRIPT = """\

# 1
; > Scene: Front door of the pool in the morning
; > Ryouma: |#1|
; The faint smell of chlorine, the sound of a whistle.


# 2
; > Aoi: |#2|
; Eek!


# choice_1
; > @choice "|#choice_1|" goto:.Run_Choice
; Jump into the pool
"""


def test_registry_naninovel_adapter():
    adapter = get_adapter("naninovel")
    assert isinstance(adapter, NaninovelAdapter)


def test_extraction_managed_text():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "DefaultUI.txt"
        p.write_text(_SAMPLE_MANAGED_TEXT, encoding="utf-8")

        adapter = NaninovelAdapter()
        entries = adapter.extract(p)

        assert len(entries) == 3
        assert entries[0].key == "Confirmation.No"
        assert entries[0].source == "No"
        assert entries[0].target == ""

        assert entries[1].key == "Confirmation.Yes"
        assert entries[1].source == "Yes"

        assert entries[2].key == "FinalEnding.ContinuePlaying"
        assert "<br>" in entries[2].source


def test_extraction_script():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "Main.txt"
        p.write_text(_SAMPLE_SCRIPT, encoding="utf-8")

        adapter = NaninovelAdapter()
        entries = adapter.extract(p)

        assert len(entries) == 3
        assert entries[0].key == "1"
        assert entries[0].speaker == "Ryouma"
        assert "The faint smell" in entries[0].source

        assert entries[1].key == "2"
        assert entries[1].speaker == "Aoi"
        assert entries[1].source == "Eek!"

        assert entries[2].key == "choice_1"
        assert entries[2].speaker is None
        assert entries[2].source == "Jump into the pool"


def test_merge_script_and_managed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p_ui = Path(tmp_dir) / "DefaultUI.txt"
        p_ui.write_text(_SAMPLE_MANAGED_TEXT, encoding="utf-8")

        p_sc = Path(tmp_dir) / "Main.txt"
        p_sc.write_text(_SAMPLE_SCRIPT, encoding="utf-8")

        adapter = NaninovelAdapter()

        # Merge UI
        entries_ui = adapter.extract(p_ui)
        entries_ui[0].target = "Nem"
        entries_ui[1].target = "Igen"
        entries_ui[2].target = "Gratulálunk! Befejezted a fő történetet!<br>Tovább játszhatsz."
        adapter.merge(p_ui, entries_ui)

        merged_ui = p_ui.read_text(encoding="utf-8")
        assert "Confirmation.No: Nem" in merged_ui
        assert "Confirmation.Yes: Igen" in merged_ui
        assert "; No" in merged_ui  # comments preserved

        # Merge Script
        entries_sc = adapter.extract(p_sc)
        entries_sc[0].target = "A klór halvány szaga, sípszó hangja."
        entries_sc[1].target = "Ík!"
        entries_sc[2].target = "Ugorj a medencébe"
        adapter.merge(p_sc, entries_sc)

        merged_sc = p_sc.read_text(encoding="utf-8")
        assert "# 1" in merged_sc
        assert "; > Ryouma: |#1|" in merged_sc
        assert "; The faint smell of chlorine" in merged_sc
        assert "A klór halvány szaga, sípszó hangja." in merged_sc

        # Re-extract merged script
        re_entries = adapter.extract(p_sc)
        assert len(re_entries) == 3
        assert re_entries[0].target == "A klór halvány szaga, sípszó hangja."
        assert re_entries[1].target == "Ík!"


def test_naninovel_validator():
    sample = """\
# 1
; Score: <color=#FF0000>100</color>

# 2
; Hello {name}!
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "Test.txt"
        p.write_text(sample, encoding="utf-8")

        adapter = NaninovelAdapter()
        entries = adapter.extract(p)

        # Introduce tag mismatch
        entries[0].target = "Pontszám: 100"  # missing tag

        # Introduce variable mismatch
        entries[1].target = "Szia {user}!"  # missing {name}, extra {user}

        adapter.merge(p, entries)

        critical, major, minor, info = validate_file(p)
        assert any("Missing placeholder '{name}'" in m for m in critical)
        assert any("hianyzik a HTML/XML tag" in m for m in major)


def test_utf8_bom_and_unicode_speaker():
    # Unity files frequently start with UTF-8 BOM (\ufeff) and can have Japanese actor names
    bom_script = "# 1\n; > 綾音: |#1|\n; おはよう\n\n# 2\n; > Scene: 教室\n; 静かな朝。\n"
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "BomTest.txt"
        p.write_bytes(bom_script.encode("utf-8-sig"))

        adapter = NaninovelAdapter()
        entries = adapter.extract(p)

        assert len(entries) == 2
        assert entries[0].key == "1"
        assert entries[0].speaker == "綾音"
        assert entries[0].source == "おはよう"
        assert entries[1].notes == ["; > Scene: 教室"]

        entries[0].target = "Jó reggelt"
        entries[1].target = "Csendes reggel."
        adapter.merge(p, entries)

        content = p.read_text(encoding="utf-8-sig")
        assert "Jó reggelt" in content
        assert "Csendes reggel." in content


def test_naninovel_inline_expression_slot_validation():
    # Naninovel replaces extracted expressions/commands in dialogue with $@
    sample = "# 1\n; You found $@ and received $@ gold.\n"
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "SlotTest.txt"
        p.write_text(sample, encoding="utf-8")

        adapter = NaninovelAdapter()
        entries = adapter.extract(p)
        assert len(entries) == 1

        # Missing one $@ slot
        entries[0].target = "Megtaláltad: $@ és kaptál aranyat."
        adapter.merge(p, entries)

        critical, major, minor, info = validate_file(p)
        assert any("Inline expression slot" in m for m in critical)

        # Correct count
        entries[0].target = "Megtaláltad: $@ és kaptál $@ aranyat."
        adapter.merge(p, entries)

        critical_ok, _, _, _ = validate_file(p)
        assert not any("Inline expression slot" in m for m in critical_ok)

