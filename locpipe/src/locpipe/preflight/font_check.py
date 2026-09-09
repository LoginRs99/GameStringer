"""Hungarian Character Font Preflight Check.

Moved from gamestringer/core/font_checker.py -- gamestringer's
`gamestringer check-fonts` CLI command and its GUI preflight tab both
now import check_game_fonts from HERE instead (see Task 13/14). New in
this module: apply_hungarian_fallback_if_needed(), which auto-configures
format_options.character_replacements on a ProjectConfig when Hungarian
glyph support is missing -- closing the gap where a human previously had
to click a fallback button in gamestringer's Projects tab GUI
(projects_tab.py's _DEFAULT_CHAR_FALLBACK).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    import UnityPy
    import UnityPy.config
    UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.0f1"
except ImportError:
    UnityPy = None

HU_GLYPHS = {"ő", "ű", "Ő", "Ű", "\u0151", "\u0171", "\u0150", "\u0170"}

# Same mapping gamestringer/desktop_gui/tabs/projects_tab.py's "one-click
# shortcut" button used to write into project.yaml by hand.
DEFAULT_HU_FALLBACK = {"ő": "ô", "ű": "û", "Ő": "Ô", "Ű": "Û"}


def check_game_fonts(input_path: str, engine_name: str) -> Dict[str, Any]:
    """Check game font assets for Hungarian glyph support (ő/ű).
    Logic unchanged from gamestringer/core/font_checker.py.
    """
    eng_lower = engine_name.lower()
    if eng_lower not in ("unity", "il2cpp"):
        msg = f"Font checking not yet supported for engine '{engine_name}'."
        logger.info(msg)
        return {"status": "unsupported", "engine": engine_name, "message": msg}

    if not os.path.exists(input_path):
        raise ValueError(f"Target input path does not exist: {input_path}")

    font_assets: List[str] = []
    hu_glyphs_detected = False
    hu_config_detected = False

    base_dir = os.path.dirname(os.path.abspath(input_path)) if os.path.isfile(input_path) else os.path.abspath(input_path)
    for root, _, files in os.walk(base_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".ttf", ".otf"):
                font_assets.append(f)
            elif ext in (".json", ".txt", ".csv", ".yaml", ".xml"):
                full = os.path.join(root, f)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as file_obj:
                        content = file_obj.read()
                        if any(g in content for g in HU_GLYPHS):
                            hu_glyphs_detected = True
                        if re.search(r"\b(hu|hungarian|magyar)\b", content, re.IGNORECASE):
                            hu_config_detected = True
                except Exception:
                    pass

    if UnityPy is not None:
        asset_files = []
        if os.path.isfile(base_dir):
            asset_files.append(base_dir)
        else:
            for root, _, files in os.walk(base_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".bundle", ".assets", ".asset") or f.startswith("sharedassets") or f == "resources.assets":
                        asset_files.append(os.path.join(root, f))

        for full in asset_files[:15]:
            try:
                env = UnityPy.load(full)
                for obj in env.objects:
                    if obj.type.name in ("Font", "TMP_FontAsset", "TextMeshPro"):
                        try:
                            data = obj.read()
                            name = getattr(data, "m_Name", getattr(data, "name", f"Font_{obj.path_id}"))
                            if name not in font_assets:
                                font_assets.append(name)

                            character_table = getattr(data, "m_CharacterTable", None) or getattr(data, "characterTable", None)
                            if character_table:
                                for entry in character_table:
                                    ascii_val = getattr(entry, "m_Unicode", getattr(entry, "unicode", 0))
                                    if ascii_val in (337, 369, 336, 368):  # ő (337), ű (369), Ő (336), Ű (368)
                                        hu_glyphs_detected = True
                                        break
                        except Exception:
                            pass
            except Exception:
                pass

    supported = hu_glyphs_detected or hu_config_detected

    if supported:
        msg = f"[INFO] Font scan result: Found {len(font_assets)} font asset(s) ({', '.join(font_assets[:5]) or 'embedded fonts'}). Hungarian ő/ű glyph support DETECTED."
        logger.info(msg)
    else:
        font_list_str = f"({', '.join(font_assets[:5])})" if font_assets else "(embedded fonts)"
        msg = (
            f"[WARNING] Game font scan result: Found {len(font_assets)} font asset(s) {font_list_str}, but no explicit ő/ű Hungarian glyph support was detected.\n"
            f"Recommendation: This game may not support ő/ű characters. Consider using ô/û in translation, or replace the font with a Noto/DejaVu variant that supports Hungarian."
        )
        logger.warning(msg)

    return {
        "status": "supported" if supported else "warning",
        "engine": engine_name,
        "font_assets": font_assets,
        "hungarian_support": supported,
        "message": msg,
    }


def apply_hungarian_fallback_if_needed(config, asset_path: str, engine: str) -> Dict[str, Any]:
    """Runs check_game_fonts() and, if Hungarian glyph support is NOT
    detected, fills any MISSING keys of DEFAULT_HU_FALLBACK into
    config.format_options["character_replacements"] -- never overwriting a
    mapping the human already configured by hand in project.yaml.

    Mutates config in memory only. Deliberately does NOT rewrite
    project.yaml on disk: round-tripping it through yaml.safe_load/
    safe_dump would silently drop comments and reorder keys in a
    human-authored file. Instead writes a separate, inspectable JSON
    report under <project_root>/preflight/font_check_report.json so the
    decision is auditable without touching the source of truth.
    """
    result = check_game_fonts(asset_path, engine)

    applied_fallback: Dict[str, str] = {}
    if not result.get("hungarian_support", True):
        current = config.format_options.setdefault("character_replacements", {})
        for src_char, fallback_char in DEFAULT_HU_FALLBACK.items():
            if src_char not in current:
                current[src_char] = fallback_char
                applied_fallback[src_char] = fallback_char

    report = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "asset_path": asset_path,
        "engine": engine,
        "font_check_result": result,
        "character_replacements_applied": applied_fallback,
        "character_replacements_in_effect": dict(config.format_options.get("character_replacements", {})),
    }
    report_dir = Path(config.root) / "preflight"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "font_check_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result["character_replacements_applied"] = applied_fallback
    return result
