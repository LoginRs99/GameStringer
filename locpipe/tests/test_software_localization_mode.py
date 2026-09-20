"""Tests for Step 3: Software Localization Mode (selectable project_type: software,
software presets, action/menu categories, accelerator keys & keyboard shortcuts).
"""

from pathlib import Path
import pytest

from locpipe.cli import main
from locpipe.config import load_project
from locpipe.schemas import build_system_prompt_for_category
from locpipe.glossary import load_glossary
from locpipe.validators.protected_tokens import audit_entry_tokens, extract_protected_tokens


def test_software_project_init_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["init", "desktop_tool", "--type", "software", "--source", "en", "--target", "hu"])
    assert exit_code == 0

    proj_dir = tmp_path / "projects" / "desktop_tool"
    cfg_file = proj_dir / "project.yaml"
    assert cfg_file.exists()

    content = cfg_file.read_text(encoding="utf-8")
    assert "project_type: software" in content

    cfg = load_project(proj_dir)
    assert cfg.project_type == "software"
    assert cfg.source_lang == "en"
    assert cfg.target_lang == "hu"

    cat_names = [c.name for c in cfg.categories]
    assert "action" in cat_names
    assert "menu" in cat_names
    assert "ui" in cat_names

    # Style guide should contain software UI preset
    style_content = (proj_dir / "resources" / "lang-style.md").read_text(encoding="utf-8")
    assert "Szoftver UI" in style_content or "UI Actions" in style_content

    # Glossary should include initial software UI terms
    glossary_content = (proj_dir / "resources" / "glossary.md").read_text(encoding="utf-8")
    assert "Mégse" in glossary_content
    assert "Mentés" in glossary_content


def test_software_system_prompt_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    main(["init", "soft_app", "--type", "software"])
    main(["init", "game_app", "--type", "game"])

    cfg_soft = load_project(tmp_path / "projects" / "soft_app")
    cfg_game = load_project(tmp_path / "projects" / "game_app")

    prompt_soft = build_system_prompt_for_category(cfg_soft, "action", glossary=[])
    prompt_game = build_system_prompt_for_category(cfg_game, "ui", glossary=[])

    assert "SOFTWARE LOCALIZATION RULES" in prompt_soft
    assert "SOFTWARE LOCALIZATION RULES" not in prompt_game


def test_accelerator_access_key_validation():
    # Valid accelerator preservation
    source = "&File"
    target = "&Fájl"
    issues = audit_entry_tokens(source, target)
    assert len(issues) == 0

    # Valid accelerator shifted to another letter (Save &As... -> Mentés má&sként...)
    source2 = "Save &As..."
    target2 = "Mentés má&sként..."
    issues2 = audit_entry_tokens(source2, target2)
    assert len(issues2) == 0

    # Missing accelerator in target
    source3 = "&Open"
    target3 = "Megnyitás"
    issues3 = audit_entry_tokens(source3, target3)
    assert any(i.code == "ACCESS_KEY_MISSING" for i in issues3)

    # Plain ampersand without hotkey letter (e.g. "Tom & Jerry") should not trigger ACCESS_KEY_MISSING
    source4 = "Tom & Jerry"
    target4 = "Tom és Jerry"
    issues4 = audit_entry_tokens(source4, target4)
    assert not any(i.code == "ACCESS_KEY_MISSING" for i in issues4)


def test_keyboard_shortcuts_protection():
    source = "Press Ctrl+Shift+P to open Command Palette, or Ctrl+S to save."
    tokens = extract_protected_tokens(source)
    assert "Ctrl+Shift+P" in tokens
    assert "Ctrl+S" in tokens

    # Translation preserving shortcuts
    target_ok = "Nyomd meg a Ctrl+Shift+P billentyűt a Parancspaletta megnyitásához, vagy a Ctrl+S-t a mentéshez."
    issues_ok = audit_entry_tokens(source, target_ok)
    assert len(issues_ok) == 0

    # Translation with corrupted shortcut
    target_corrupt = "Nyomd meg a Vezérlés+S-t a mentéshez."
    issues_bad = audit_entry_tokens(source, target_corrupt)
    assert any("Ctrl+S" in i.message or "Ctrl+Shift+P" in i.message for i in issues_bad)


def test_cross_language_project_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    # ja -> en
    exit_code = main(["init", "retro_rpg", "--type", "game", "--source", "ja", "--target", "en", "--format", "po_gettext"])
    assert exit_code == 0
    cfg = load_project(tmp_path / "projects" / "retro_rpg")
    assert cfg.source_lang == "ja"
    assert cfg.target_lang == "en"
    assert cfg.project_type == "game"
    assert cfg.format == "po_gettext"

    # hu -> en software
    exit_code2 = main(["init", "hu_app", "--type", "software", "--source", "hu", "--target", "en", "--format", "xliff"])
    assert exit_code2 == 0
    cfg2 = load_project(tmp_path / "projects" / "hu_app")
    assert cfg2.source_lang == "hu"
    assert cfg2.target_lang == "en"
    assert cfg2.project_type == "software"
    assert cfg2.format == "xliff"

