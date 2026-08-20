"""
Final End-to-End Verification Runner for GameStringer across 5 Unity Games.
"""

import os
import sys
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

GAMES = {
    "ChildrenOfMorta": {
        "path": r"G:\Steam games\steamapps\common\ChildrenOfMorta",
        "engine": "unity",
        "flags": ["--scan-dlls", "--scan-custom-tables"]
    },
    "ShoppeKeep": {
        "path": r"G:\Steam games\steamapps\common\Shoppe Keep",
        "engine": "unity",
        "flags": ["--scan-dlls", "--scan-custom-tables"]
    },
    "Sunderfolk": {
        "path": r"G:\Steam games\steamapps\common\Sunderfolk",
        "engine": "il2cpp",
        "flags": []
    },
    "Cursebreaker": {
        "path": r"G:\Steam games\steamapps\common\Cursebreaker",
        "engine": "unity",
        "flags": ["--scan-dlls", "--scan-custom-tables"]
    },
    "CitizenSleeper": {
        "path": r"G:\Steam games\steamapps\common\Citizen Sleeper",
        "engine": "unity",
        "flags": ["--scan-dlls", "--scan-custom-tables"]
    }
}

OUTPUT_DIR = r"D:\github\GameStringer-main\e2e_verification_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_xliff_units(xliff_path: str) -> List[Tuple[str, str, str]]:
    if not os.path.exists(xliff_path):
        return []

    with open(xliff_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
    root = ET.fromstring(xml_clean)

    units = []
    for tu in root.iter():
        if tu.tag.endswith('trans-unit'):
            uid = tu.attrib.get('id', '')
            src = ""
            note = ""
            for c in tu:
                tag_name = c.tag.split("}")[-1]
                if tag_name == "source" and c.text:
                    src = c.text.strip()
                elif tag_name == "note" and c.text:
                    note = c.text.strip()
            if src:
                units.append((uid, src, note))

    return units


def main():
    results = {}

    for name, config in GAMES.items():
        game_path = config["path"]
        engine_arg = config["engine"]
        flags = config["flags"]

        print(f"\n==================================================")
        print(f"RUNNING VERIFICATION FOR GAME: {name}")
        print(f"Path: {game_path}")
        print(f"==================================================")

        raw_xliff = os.path.join(OUTPUT_DIR, f"{name}_raw.xliff")
        clean_xliff = os.path.join(OUTPUT_DIR, f"{name}_final_complete.xliff")

        cmd = [
            sys.executable, "-m", "gamestringer.cli", "extract",
            "--engine", engine_arg,
            "--input", game_path,
            "--output", raw_xliff
        ] + flags

        print(f"Executing extraction: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("Extraction Output Summary:", res.stdout[-400:] if res.stdout else "")

        if os.path.exists(raw_xliff):
            print(f"Running xliff_cleaner.py...")
            clean_cmd = [sys.executable, "xliff_cleaner.py", raw_xliff, clean_xliff]
            clean_res = subprocess.run(clean_cmd, capture_output=True, text=True)
            print("Cleaner Output:", clean_res.stdout)

        clean_units = parse_xliff_units(clean_xliff)
        clean_sources = [src for _, src, _ in clean_units]
        unique_clean_sources = set(clean_sources)

        # Citizen Sleeper Ink check
        ink_unit_count = 0
        if name == "CitizenSleeper":
            ink_units = [u for u in clean_units if u[0].startswith("ink_") or "ink" in u[2].lower()]
            ink_unit_count = len(ink_units)
            print(f"[Citizen Sleeper Verification] Extracted Ink Narrative Units: {ink_unit_count}")

        # Sample entries
        samples = clean_units[:15]

        results[name] = {
            "raw_xliff": raw_xliff,
            "clean_xliff": clean_xliff,
            "total_raw_units": len(parse_xliff_units(raw_xliff)) if os.path.exists(raw_xliff) else 0,
            "final_clean_units": len(clean_units),
            "unique_clean_sources": len(unique_clean_sources),
            "ink_unit_count": ink_unit_count,
            "samples": samples
        }

    summary_path = os.path.join(OUTPUT_DIR, "e2e_verification_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[E2E VERIFICATION COMPLETED] Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
