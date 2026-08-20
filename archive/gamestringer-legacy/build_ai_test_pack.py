"""
AI Test Pack Generator & Repository Cleanup Script for GameStringer.
"""

import os
import shutil
import zipfile
import datetime
import xml.etree.ElementTree as ET
import re

ROOT_DIR = r"D:\github\GameStringer-main"
TEST_PACK_DIR = os.path.join(ROOT_DIR, "ai_test_pack")
DOCS_DIR = os.path.join(ROOT_DIR, "docs")

os.makedirs(TEST_PACK_DIR, exist_ok=True)
os.makedirs(os.path.join(TEST_PACK_DIR, "source_code"), exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)


def extract_unique_strings_to_txt(xliff_path: str, output_txt_path: str, max_lines: int = 3000) -> int:
    if not os.path.exists(xliff_path):
        print(f"Warning: XLIFF path not found: {xliff_path}")
        return 0

    with open(xliff_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
    root = ET.fromstring(xml_clean)

    unique_sources = []
    seen = set()

    for tu in root.iter():
        if tu.tag.endswith("trans-unit"):
            for child in tu:
                if child.tag.endswith("source") and child.text:
                    s = child.text.strip()
                    if s and s not in seen:
                        seen.add(s)
                        unique_sources.append(s)
                        if len(unique_sources) >= max_lines:
                            break
            if len(unique_sources) >= max_lines:
                break

    with open(output_txt_path, "w", encoding="utf-8") as out_f:
        for line in unique_sources:
            out_f.write(line + "\n")

    print(f"Saved {len(unique_sources)} unique lines to {os.path.basename(output_txt_path)}")
    return len(unique_sources)


def main():
    print("=== Step 1: Generating Sample TXT Files ===")
    
    # 1. Children of Morta (5,000 lines)
    morta_xliff = os.path.join(ROOT_DIR, "stress_test_output", "ChildrenOfMorta_stricter_complete.xliff")
    if not os.path.exists(morta_xliff):
        morta_xliff = os.path.join(ROOT_DIR, "ChildrenOfMorta_complete.xliff")
    extract_unique_strings_to_txt(morta_xliff, os.path.join(TEST_PACK_DIR, "children_of_morta_sample.txt"), max_lines=5000)

    # 2. Shoppe Keep (3,000 lines)
    shoppe_xliff = os.path.join(ROOT_DIR, "stress_test_output", "ShoppeKeep_complete.xliff")
    extract_unique_strings_to_txt(shoppe_xliff, os.path.join(TEST_PACK_DIR, "shoppe_keep_sample.txt"), max_lines=3000)

    # 3. Sunderfolk (3,000 lines)
    sunder_xliff = os.path.join(ROOT_DIR, "stress_test_output", "Sunderfolk_stricter.xliff")
    if not os.path.exists(sunder_xliff):
        sunder_xliff = os.path.join(ROOT_DIR, "stress_test_output", "Sunderfolk_complete.xliff")
    extract_unique_strings_to_txt(sunder_xliff, os.path.join(TEST_PACK_DIR, "sunderfolk_sample.txt"), max_lines=3000)

    # 4. Cursebreaker (3,000 lines)
    curse_xliff = os.path.join(ROOT_DIR, "stress_test_output", "Cursebreaker_complete.xliff")
    extract_unique_strings_to_txt(curse_xliff, os.path.join(TEST_PACK_DIR, "cursebreaker_sample.txt"), max_lines=3000)

    # 5. Citizen Sleeper (3,000 lines)
    sleeper_xliff = os.path.join(ROOT_DIR, "scratch", "CitizenSleeper_complete.xliff")
    extract_unique_strings_to_txt(sleeper_xliff, os.path.join(TEST_PACK_DIR, "citizen_sleeper_sample.txt"), max_lines=3000)

    print("\n=== Step 2: Copying Source Code Modules ===")
    src_code_dir = os.path.join(TEST_PACK_DIR, "source_code")
    code_files = [
        os.path.join(ROOT_DIR, "gamestringer", "core", "dll_scanner.py"),
        os.path.join(ROOT_DIR, "gamestringer", "core", "custom_table_extractor.py"),
        os.path.join(ROOT_DIR, "gamestringer", "engines", "unity_mono.py"),
        os.path.join(ROOT_DIR, "gamestringer", "engines", "il2cpp_hybrid.py"),
        os.path.join(ROOT_DIR, "xliff_cleaner.py"),
    ]
    for src in code_files:
        if os.path.exists(src):
            dst = os.path.join(src_code_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            print(f"Copied {os.path.basename(src)} -> source_code/")

    print("\n=== Step 3: Writing README_FOR_AI.txt ===")
    today_str = datetime.date.today().strftime("%B %d, %Y")
    readme_content = f"""=== GameStringer Pipeline Summary ===
Last modified: {today_str}
Purpose: Extract translatable text from Unity games (Mono & IL2CPP)

=== Current Filter Philosophy ===

    Tier 1: Keep strings with spaces + 3+ letters, accented chars, or punctuation
    Tier 2: Keep single words only if TitleCase, ALL CAPS UI, or whitelisted
    Tier 3: Reject camelCase with code suffixes (handler, callback, manager, etc.)

=== Modules ===

    unity_mono.py: Asset extraction (MonoBehaviour, TextAsset)
    dll_scanner.py: Managed assembly string extraction (Mono) / IL2CppDumper fallback (IL2CPP)
    custom_table_extractor.py: Length-prefixed binary string scanning
    xliff_cleaner.py: Deduplication + noise filtering

=== Known Limitations ===

    IL2CPP games may still have metadata noise if filters are too loose
    Custom binary formats (Altar.Localization.StringTable) require custom_table_extractor
    Some edge-case text may be in runtime-loaded CSVs not scanned

=== Test Samples in this folder ===
1. children_of_morta_sample.txt — Children of Morta (Mono, Unity 2019/2021)
2. shoppe_keep_sample.txt — Shoppe Keep (Mono, Unity 5.3)
3. sunderfolk_sample.txt — Sunderfolk (IL2CPP, Unity 2022/2023)
4. cursebreaker_sample.txt — Cursebreaker (Mono, Unity 2021.3)
5. citizen_sleeper_sample.txt — Citizen Sleeper (Mono, Ink engine narrative text)

=== Suggested Review Tasks for Next AI ===

    Review the sample .txt files — are there obvious false positives (code, noise) that should be filtered?
    Review the sample .txt files — are there obvious false negatives (missing real text) visible in the game but not in the sample?
    Suggest improvements to the 3-tier filter logic in il2cpp_hybrid.py and dll_scanner.py
    Suggest additional per-game config options if needed
"""
    readme_path = os.path.join(TEST_PACK_DIR, "README_FOR_AI.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("Created README_FOR_AI.txt")

    print("\n=== Step 4: Creating ZIP Archive ai_test_pack.zip ===")
    zip_path = os.path.join(ROOT_DIR, "ai_test_pack.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root_p, _, files in os.walk(TEST_PACK_DIR):
            for f in files:
                full_p = os.path.join(root_p, f)
                rel_p = os.path.relpath(full_p, ROOT_DIR)
                zipf.write(full_p, rel_p)
    print(f"Created ZIP archive: {zip_path} (Size: {os.path.getsize(zip_path)} bytes)")

    print("\n=== Step 5: Repository Cleanup ===")
    # Preserve key docs into docs/
    doc_moves = [
        ("cross_game_stress_test.md", os.path.join(DOCS_DIR, "cross_game_stress_test.md")),
        ("final_verification_report.md", os.path.join(DOCS_DIR, "final_verification_report.md")),
    ]
    for src_f, dst_f in doc_moves:
        full_src = os.path.join(ROOT_DIR, src_f)
        if os.path.exists(full_src):
            shutil.move(full_src, dst_f)
            print(f"Moved {src_f} -> docs/")

    # Remove temporary test outputs & raw dumps
    paths_to_delete = [
        os.path.join(ROOT_DIR, "stress_test_output"),
        os.path.join(ROOT_DIR, "ChildrenOfMorta_all.xliff"),
        os.path.join(ROOT_DIR, "ChildrenOfMorta_dlls.xliff"),
        os.path.join(ROOT_DIR, "ChildrenOfMorta_final.xliff"),
        os.path.join(ROOT_DIR, "ChildrenOfMorta_stricter.xliff"),
        os.path.join(ROOT_DIR, "ChildrenOfMorta_new.xliff"),
        os.path.join(ROOT_DIR, "diff_report.md"),
        os.path.join(ROOT_DIR, "ground_truth_diff_report.md"),
        os.path.join(ROOT_DIR, "updated_diff_report.md"),
        os.path.join(ROOT_DIR, "brute_force_strings.txt"),
        os.path.join(ROOT_DIR, "xliff_strings.txt"),
        os.path.join(ROOT_DIR, "analysis_out.json"),
        os.path.join(ROOT_DIR, "analyze_diff.py"),
        os.path.join(ROOT_DIR, "run_final_verification.py"),
        os.path.join(ROOT_DIR, "final_verification.json"),
        os.path.join(ROOT_DIR, "run_cross_game_test.py"),
    ]

    for p in paths_to_delete:
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            print(f"Deleted temp path: {os.path.basename(p)}")

    print("\n[COMPLETE] AI Test Pack created and repository cleaned up!")


if __name__ == "__main__":
    main()
