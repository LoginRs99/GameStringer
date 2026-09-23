"""Tests for Hungarian font checking and character fallback configuration.

Covers:
- locpipe.preflight.font_check.check_game_fonts (Unity, unsupported engines, missing path)
- locpipe.preflight.font_check.apply_hungarian_fallback_if_needed (no fallback, fallback injection, user override preservation, None format_options, report file generation)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from locpipe.config import ProjectConfig, ProviderConfig
from locpipe.preflight.font_check import (
    DEFAULT_HU_FALLBACK,
    check_game_fonts,
    apply_hungarian_fallback_if_needed,
)


def _make_dummy_config(root_dir: Path, format_options=None) -> ProjectConfig:
    return ProjectConfig(
        project="TestProject",
        root=root_dir,
        source_lang="en",
        target_lang="hu",
        target_register="informal",
        project_type="game",
        format="uabea_json",
        batch_glob="batches/**/*.json",
        resources={},
        categories=[],
        provider=ProviderConfig(),
        tm_db_path=root_dir / "tm.sqlite3",
        format_options=format_options if format_options is not None else {},
    )


def test_check_game_fonts_errors_and_unsupported(tmp_path):
    # Nonexistent path raises ValueError
    with pytest.raises(ValueError, match="Target input path does not exist"):
        check_game_fonts(str(tmp_path / "nonexistent"), "unity")

    # Unsupported engines
    for eng in ("unreal", "renpy", "cri", "godot"):
        res = check_game_fonts(str(tmp_path), eng)
        assert res["status"] == "unsupported"
        assert res["engine"] == eng
        assert "not yet supported" in res["message"]


def test_check_game_fonts_with_text_and_ttf(tmp_path):
    # Case 1: Empty folder -> warning (hungarian_support = False)
    res_empty = check_game_fonts(str(tmp_path), "unity")
    assert res_empty["status"] == "warning"
    assert res_empty["hungarian_support"] is False

    # Case 2: Folder containing Hungarian ő and ű in a script/json file
    sub_dir = tmp_path / "GameData"
    sub_dir.mkdir()
    (sub_dir / "dialogue.json").write_text('{"text": "Őrült fűnyíró"}', encoding="utf-8")
    (sub_dir / "custom_font.ttf").write_bytes(b"\x00\x01\x00\x00")

    res_supported = check_game_fonts(str(sub_dir), "unity")
    assert res_supported["status"] == "supported"
    assert res_supported["hungarian_support"] is True
    assert "custom_font.ttf" in res_supported["font_assets"]


def test_apply_hungarian_fallback_when_supported(tmp_path):
    # Game data has Hungarian ő and ű
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "text.txt").write_text("árvíztűrő fúrógép", encoding="utf-8")

    cfg = _make_dummy_config(tmp_path, format_options={})
    res = apply_hungarian_fallback_if_needed(cfg, str(game_dir), "unity")

    assert res["hungarian_support"] is True
    assert res["character_replacements_applied"] == {}
    assert "character_replacements" not in cfg.format_options

    report_file = tmp_path / "preflight" / "font_check_report.json"
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["font_check_result"]["hungarian_support"] is True


def test_apply_hungarian_fallback_when_unsupported(tmp_path):
    # Empty game directory -> hungarian_support is False
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    cfg = _make_dummy_config(tmp_path, format_options={})
    res = apply_hungarian_fallback_if_needed(cfg, str(game_dir), "unity")

    assert res["hungarian_support"] is False
    # All DEFAULT_HU_FALLBACK characters should have been applied
    assert res["character_replacements_applied"] == DEFAULT_HU_FALLBACK
    assert cfg.format_options["character_replacements"] == DEFAULT_HU_FALLBACK

    report_file = tmp_path / "preflight" / "font_check_report.json"
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["character_replacements_applied"] == DEFAULT_HU_FALLBACK
    assert report_data["character_replacements_in_effect"] == DEFAULT_HU_FALLBACK


def test_apply_hungarian_fallback_preserves_user_overrides(tmp_path):
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    # User explicitly configured custom replacements
    existing_replacements = {
        "ő": "o",  # user prefers ASCII 'o' rather than circumflex 'ô'
        "custom_code": "code"
    }
    cfg = _make_dummy_config(tmp_path, format_options={"character_replacements": dict(existing_replacements)})
    res = apply_hungarian_fallback_if_needed(cfg, str(game_dir), "unity")

    assert res["hungarian_support"] is False
    # 'ő' should NOT be overwritten with 'ô'
    assert cfg.format_options["character_replacements"]["ő"] == "o"
    assert cfg.format_options["character_replacements"]["custom_code"] == "code"
    # missing characters like 'ű', 'Ő', 'Ű' should be filled in
    assert cfg.format_options["character_replacements"]["ű"] == "û"
    assert cfg.format_options["character_replacements"]["Ő"] == "Ô"
    assert cfg.format_options["character_replacements"]["Ű"] == "Û"

    # Only newly applied ones in applied_fallback
    assert "ő" not in res["character_replacements_applied"]
    assert res["character_replacements_applied"]["ű"] == "û"


def test_apply_hungarian_fallback_none_format_options(tmp_path):
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    cfg = _make_dummy_config(tmp_path, format_options=None)
    cfg.format_options = None  # explicitly None

    res = apply_hungarian_fallback_if_needed(cfg, str(game_dir), "unity")
    assert res["hungarian_support"] is False
    assert cfg.format_options is not None
    assert cfg.format_options["character_replacements"] == DEFAULT_HU_FALLBACK
