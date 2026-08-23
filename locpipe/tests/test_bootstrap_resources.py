"""Tests for locpipe bootstrap-resources command and bootstrap module."""

import json
from pathlib import Path
import pytest

from locpipe.bootstrap import (
    ANTI_FABRICATION_DEFAULT,
    update_existing_anti_fabrication_checklist,
    filter_glossary_candidates,
    bootstrap_glossary,
    bootstrap_lang_style,
    bootstrap_character_voices,
)
from locpipe.config import load_project
from locpipe.models import Entry, TMRecord
from locpipe.providers.mock import MockProvider
from locpipe.tm import TranslationMemory
from locpipe.cli import main


def test_update_existing_anti_fabrication_checklist_detects_and_updates(tmp_path):
    proj_dir = tmp_path / "test_proj"
    proj_dir.mkdir()
    res_dir = proj_dir / "resources"
    res_dir.mkdir()
    af_file = res_dir / "anti-fabrication-checklist.md"
    af_file.write_text("# Anti-fabrication checklist\n", encoding="utf-8")

    (proj_dir / "project.yaml").write_text(
        "project: test_proj\nsource_lang: en\ntarget_lang: hu\nformat: generic_kv\n"
        "resources:\n  anti_fabrication_checklist: resources/anti-fabrication-checklist.md\n",
        encoding="utf-8",
    )
    config = load_project(proj_dir)

    updated = update_existing_anti_fabrication_checklist(config)
    assert updated is True
    assert af_file.read_text(encoding="utf-8") == ANTI_FABRICATION_DEFAULT

    # Second run does not overwrite custom/updated text
    updated_again = update_existing_anti_fabrication_checklist(config)
    assert updated_again is False


def test_filter_glossary_candidates_shrinks_tm():
    records = [
        ("h1", TMRecord("k1", "Leap", "Ugrás", "en", "hu", "mechanic", None, 1.0, "mt", 0)),
        ("h2", TMRecord("k2", "<keyword=\"stun\">Stun</keyword>", "Kábítás", "en", "hu", "mechanic", None, 1.0, "mt", 0)),
        ("h3", TMRecord("k3", "Attack", "Támadás", "en", "hu", "ui", None, 1.0, "mt", 0)),
        ("h4", TMRecord("k4", "This is a very long descriptive story sentence that goes on and on without any special keywords.", "Ez egy nagyon hosszú mondat.", "en", "hu", "dialogue", None, 1.0, "mt", 0)),
        ("h5", TMRecord("k5", "Short phrase", "Rövid kifejezés", "en", "hu", "ui", None, 1.0, "mt", 0)),
    ]
    candidates, total = filter_glossary_candidates(records)
    assert total == 5
    # The long story sentence should be filtered out, keeping mechanics & UI terms
    sources = [c["source"] for c in candidates]
    assert "Leap" in sources
    assert "<keyword=\"stun\">Stun</keyword>" in sources
    assert "Attack" in sources
    assert "This is a very long descriptive story sentence that goes on and on without any special keywords." not in sources
    assert len(candidates) < total


@pytest.mark.anyio
async def test_bootstrap_glossary_and_lang_style(tmp_path):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    res_dir = proj_dir / "resources"
    res_dir.mkdir()
    tm_dir = proj_dir / "tm"
    tm_dir.mkdir()
    tm_path = tm_dir / "tm.sqlite3"

    tm = TranslationMemory(tm_path)
    tm.upsert("h1", TMRecord("k1", "Power Chord", "Erőakkord", "en", "hu", "ui", None, 1.0, "mt", 0))
    tm.upsert("h2", TMRecord("k2", "Miss", "Mellé", "en", "hu", "ui", None, 1.0, "mt", 0))
    tm.upsert("h3", TMRecord("k3", "Leap", "Ugrás", "en", "hu", "mechanic", None, 1.0, "mt", 0))
    tm.close()

    (proj_dir / "project.yaml").write_text(
        "project: proj\nsource_lang: en\ntarget_lang: hu\nformat: generic_kv\n"
        "tm:\n  db_path: tm/tm.sqlite3\n"
        "resources:\n  glossary: resources/glossary.md\n  lang_style: resources/lang-style.md\n",
        encoding="utf-8",
    )
    config = load_project(proj_dir)
    provider = MockProvider()

    out_g = await bootstrap_glossary(config, provider)
    assert out_g is not None
    assert out_g.name == "glossary.draft.md"
    assert out_g.exists()
    content_g = out_g.read_text(encoding="utf-8")
    assert "# Glossary" in content_g
    assert "| Source term | Target translation | Category | Confidence | Source/justification |" in content_g

    out_ls = await bootstrap_lang_style(config, provider)
    assert out_ls is not None
    assert out_ls.name == "lang-style.draft.md"
    assert out_ls.exists()
    content_ls = out_ls.read_text(encoding="utf-8")
    assert "# Language style guide" in content_ls


@pytest.mark.anyio
async def test_bootstrap_character_voices_skips_when_no_speakers(tmp_path):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    batches = proj_dir / "batches"
    batches.mkdir()
    (batches / "data.json").write_text(json.dumps({"btn_start": "Start Game"}), encoding="utf-8")

    (proj_dir / "project.yaml").write_text(
        "project: proj\nsource_lang: en\ntarget_lang: hu\nformat: generic_kv\n"
        "batches:\n  glob: batches/*.json\n",
        encoding="utf-8",
    )
    config = load_project(proj_dir)
    provider = MockProvider()

    out_cv, msg = await bootstrap_character_voices(config, provider)
    assert out_cv is None
    assert "skipping character-voices bootstrap" in msg


def test_cli_bootstrap_resources_smoke(tmp_path, monkeypatch, capsys):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "resources").mkdir()
    (proj_dir / "batches").mkdir()
    (proj_dir / "tm").mkdir()
    tm = TranslationMemory(proj_dir / "tm" / "tm.sqlite3")
    tm.upsert("h1", TMRecord("k1", "Attack", "Támadás", "en", "hu", "ui", None, 1.0, "mt", 0))
    tm.close()

    (proj_dir / "project.yaml").write_text(
        "project: proj\nsource_lang: en\ntarget_lang: hu\nformat: generic_kv\n"
        "tm:\n  db_path: tm/tm.sqlite3\n"
        "batches:\n  glob: batches/*.json\n",
        encoding="utf-8",
    )

    ret = main(["bootstrap-resources", "--project", str(proj_dir), "--dry-run", "--yes"])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "=== BOOTSTRAP RESOURCES PLAN & ESTIMATE ===" in captured
    assert "Glossary Candidates:" in captured
    assert "=== BOOTSTRAP COMPLETED ===" in captured
    assert (proj_dir / "resources" / "glossary.draft.md").exists()
    assert (proj_dir / "resources" / "lang-style.draft.md").exists()
