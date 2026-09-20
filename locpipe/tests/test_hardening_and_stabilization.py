"""Tests for Phase Hardening, Reviewer Safety, Format Adapters, and Stability Improvements.
"""

import asyncio
import csv
import json
import os
import tempfile
from pathlib import Path
import pytest
import polib

from locpipe.models import Entry, EntryStatus, ValidationIssue, ValidationResult, Severity, TMRecord
from locpipe.review_queue import ReviewItem
from locpipe.reviewer import build_review_payload
from locpipe.checkpoint import Checkpoint
from locpipe.consistency import find_consistency_issues
from locpipe.adapters.unity import UnityCSVAdapter
from locpipe.adapters.po_gettext import PoGettextAdapter
from locpipe.validators.registry import run_validator
from locpipe.preflight.font_check import check_game_fonts
from locpipe.providers.antigravity_cli_provider import AntigravityCLIProvider
from gamestringer.core.addressables_crc import fix_catalog_crc_command, auto_update_addressables_crc


def test_reviewer_payload_includes_confidence_flags():
    """Verify that build_review_payload passes confidence_flags so LLM knows why item was flagged."""
    entry = Entry(
        file="test.json",
        key="key_1",
        source="Start Game",
        target="Játék indítása",
        category="ui",
    )
    vr = ValidationResult(entry_key="key_1")
    item = ReviewItem(
        entry=entry,
        validation=vr,
        confidence=0.75,
        relevant_glossary_terms=[],
        confidence_flags=["target_unchanged_from_source", "length_ratio_exceeded"],
    )
    payload_json = build_review_payload([item], [])
    data = json.loads(payload_json)
    assert "items" in data
    assert len(data["items"]) == 1
    review_dict = data["items"][0]
    assert "confidence_flags" in review_dict
    assert "target_unchanged_from_source" in review_dict["confidence_flags"]
    assert "length_ratio_exceeded" in review_dict["confidence_flags"]


def test_checkpoint_thread_safety(tmp_path: Path):
    """Verify concurrent save_batch_drafts and mark_batch_done do not raise dict size mutation error."""
    import threading

    cp_path = tmp_path / "checkpoint.json"
    cp = Checkpoint(cp_path)

    errors = []

    def writer_drafts(worker_id: int):
        try:
            for i in range(50):
                cp.save_batch_drafts({f"key_{worker_id}_{i}": f"target_{worker_id}_{i}"})
        except Exception as e:
            errors.append(e)

    def writer_batches(worker_id: int):
        try:
            for i in range(50):
                cp.mark_batch_done("ui", i)
        except Exception as e:
            errors.append(e)

    threads = []
    for w in range(4):
        threads.append(threading.Thread(target=writer_drafts, args=(w,)))
        threads.append(threading.Thread(target=writer_batches, args=(w,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    drafts = cp.get_batch_drafts()
    assert len(drafts) == 200


def test_consistency_exact_source_conflict():
    """Verify that identical source strings with differing translations are flagged with similarity 1.0."""
    records = [
        ("key1", TMRecord("key1", "Cancel", "Mégse", "en", "hu", "ui", None, 1.0, "mt")),
        ("key2", TMRecord("key2", "Cancel", "Kilépés", "en", "hu", "dialogue", None, 1.0, "mt")),
        ("key3", TMRecord("key3", "Save", "Mentés", "en", "hu", "ui", None, 1.0, "mt")),
    ]
    issues = find_consistency_issues(records, threshold=0.85, min_length=3)
    assert len(issues) == 1
    assert issues[0]["source_a"] == "Cancel"
    assert issues[0]["similarity"] == 1.0
    targets = {issues[0]["target_a"], issues[0]["target_b"]}
    assert targets == {"Mégse", "Kilépés"}


def test_unity_csv_semicolon_delimiter_handling(tmp_path: Path):
    """Verify Unity CSV adapter automatically sniffs semicolon delimiters and preserves them on merge."""
    csv_file = tmp_path / "strings.csv"
    csv_file.write_text(
        "id;source;target\n"
        "ui_play;Play Game;Játék indítása\n"
        "ui_quit;Quit Game;\n",
        encoding="utf-8"
    )

    adapter = UnityCSVAdapter(source_column_names=["source"], target_column_names=["target"])
    entries = adapter.extract(csv_file)
    assert len(entries) == 2
    assert entries[0].key == "ui_play"
    assert entries[0].source == "Play Game"
    assert entries[0].target == "Játék indítása"
    assert entries[1].key == "ui_quit"
    assert entries[1].target == ""

    # Merge translation
    entries[1].target = "Kilépés"
    adapter.merge(csv_file, entries)

    content = csv_file.read_text(encoding="utf-8-sig")
    assert ";" in content
    assert "ui_quit;Quit Game;Kilépés" in content


def test_unity_csv_validator_critical_headers(tmp_path: Path):
    """Verify that validate_unity_csv outputs -- CRITICAL (N) -- so registry.run_validator flags failures."""
    invalid_csv = tmp_path / "bad.csv"
    invalid_csv.write_text("WrongHeader1,WrongHeader2\nval1,val2\n", encoding="utf-8")

    result = run_validator("unity", invalid_csv, format_kwargs={"source_col": "source", "target_col": "target"})
    assert not result.passed
    assert len(result.critical) > 0
    assert any("Nincs 'Key' vagy 'ID' oszlop" in c.message for c in result.critical)


def test_po_gettext_wrapwidth_zero_preservation(tmp_path: Path):
    """Verify that PoGettextAdapter loads and saves with wrapwidth=0 to avoid line wrapping."""
    po_file = tmp_path / "test.po"
    po = polib.POFile()
    long_source = "This is a very long string that would usually be wrapped across multiple lines if wrapwidth was 78 characters."
    long_target = "Ez egy nagyon hosszú szöveg, amit normál esetben több sorba tördelne a polib, ha a wrapwidth 78 karakter lenne."
    po.append(polib.POEntry(msgid=long_source, msgstr=long_target))
    po.save(str(po_file))

    adapter = PoGettextAdapter()
    entries = adapter.extract(po_file)
    assert len(entries) == 1
    entries[0].target = long_target + " Módosítva."
    adapter.merge(po_file, entries)

    saved_raw = po_file.read_text(encoding="utf-8")
    # Wrapwidth=0 ensures msgstr is kept on one continuous line without linebreaks inside the string
    assert f'msgstr "{long_target} Módosítva."' in saved_raw


def test_font_check_requires_both_o_and_u(tmp_path: Path):
    """Verify font check does not declare Hungarian support if only ő or generic 'hu' string is found."""
    test_dir = tmp_path / "game_fonts"
    test_dir.mkdir()

    # Case 1: Config file contains 'hu', but no Hungarian font glyphs
    (test_dir / "config.json").write_text(json.dumps({"language": "hu", "author": "John Hu"}), encoding="utf-8")
    res1 = check_game_fonts(str(test_dir), "unity")
    assert res1["hungarian_support"] is False
    assert res1["status"] == "warning"

    # Case 2: Text file has only 'ő', but lacks 'ű'
    (test_dir / "dialogue.txt").write_text("Csak ő van itt, más nincs.", encoding="utf-8")
    res2 = check_game_fonts(str(test_dir), "unity")
    assert res2["hungarian_support"] is False

    # Case 3: Text file has both 'ő' and 'ű'
    (test_dir / "dialogue.txt").write_text("Ők és űrhajók.", encoding="utf-8")
    res3 = check_game_fonts(str(test_dir), "unity")
    assert res3["hungarian_support"] is True
    assert res3["status"] == "supported"


def test_addressables_crc_ignores_bak_files(tmp_path: Path):
    """Verify auto_update_addressables_crc ignores .bak backup files and correctly processes catalogs."""
    cat_path = tmp_path / "catalog.json"
    cat_path.write_text(json.dumps({
        "m_InternalIds": ["game.bundle"],
        "m_Crcs": {"game.bundle": 12345}
    }), encoding="utf-8")

    # Create a backup file that should be ignored
    bak_path = tmp_path / "catalog_2026.json.bak"
    bak_path.write_text("INVALID_JSON_OR_STALE_CATALOG", encoding="utf-8")

    bundle_path = tmp_path / "game.bundle"
    bundle_path.write_bytes(b"BundleContent123")

    res = fix_catalog_crc_command(str(tmp_path))
    assert res["catalog_found"] is True
    assert "game.bundle" in res["updated_files"]
    assert str(bak_path) not in res["catalogs"]
