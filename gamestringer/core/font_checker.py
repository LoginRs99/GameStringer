"""
Hungarian Character Font Warning & Font Asset Checker for GameStringer CLI.

Scans game assets for TextMeshPro (TMP_FontAsset) and standard Font objects,
checks for Hungarian glyph support (ő/ű/Ő/Ű), and warns translators of font limitations.
"""

import os
import re
from typing import List, Dict, Any, Tuple
from gamestringer.core.logger import logger

try:
    import UnityPy
except ImportError:
    UnityPy = None

HU_GLYPHS = {"ő", "ű", "Ő", "Ű", "\u0151", "\u0171", "\u0150", "\u0170"}


def check_game_fonts(input_path: str, engine_name: str) -> Dict[str, Any]:
    """
    Check game font assets for Hungarian glyph support (ő/ű).

    Returns summary dict with result status and detailed report.
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

    # Scan for loose TTF/OTF fonts & text localization configs
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

    # Unity Asset Inspection using UnityPy if available
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

        # Inspect first 15 asset files for Font / TMP_FontAsset
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
        "message": msg
    }
