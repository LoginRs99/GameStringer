"""
XLIFF Cleaner Utility for GameStringer.

Cleans and deduplicates extracted XLIFF 1.2 files prior to translation.
"""

import sys
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

ET.register_namespace('', "urn:oasis:names:tc:xliff:document:1.2")


def clean_xliff(input_xliff_path: str, output_xliff_path: str) -> None:
    print(f"Reading input XLIFF: {input_xliff_path}...")
    
    with open(input_xliff_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Clean non-XML control characters
    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
    root = ET.fromstring(xml_clean)

    # Collect all trans-unit elements using iter()
    all_units = []
    for tu in root.iter():
        if tu.tag.endswith('trans-unit'):
            all_units.append(tu)

    input_count = len(all_units)
    print(f"Input trans-units: {input_count}")

    # Step 1: Deduplicate by exact source text
    dedup_dict: Dict[str, Tuple[str, List[str], ET.Element]] = {}  # source -> (best_id, merged_notes, orig_tu)
    
    for tu in all_units:
        uid = tu.attrib.get("id", "")
        src_text = ""
        note_text = ""

        for child in tu:
            tag_name = child.tag.split("}")[-1]
            if tag_name == "source" and child.text:
                src_text = child.text.strip()
            elif tag_name == "note" and child.text:
                note_text = child.text.strip()

        if not src_text:
            continue

        if src_text not in dedup_dict:
            dedup_dict[src_text] = (uid, [note_text] if note_text else [], tu)
        else:
            existing_uid, existing_notes, existing_tu = dedup_dict[src_text]
            if note_text and note_text not in existing_notes:
                existing_notes.append(note_text)
            if len(uid) < len(existing_uid):
                dedup_dict[src_text] = (uid, existing_notes, tu)

    after_dedup_count = len(dedup_dict)
    print(f"After deduplication: {after_dedup_count} (removed {input_count - after_dedup_count} duplicates)")

    # Step 2: Filter FMOD audio paths (event:/, snapshot:/)
    fmod_filtered_dict = {}
    fmod_pattern = re.compile(r"^(event:/|snapshot:/)", re.IGNORECASE)
    
    for src, (uid, notes, tu) in dedup_dict.items():
        if not fmod_pattern.search(src):
            fmod_filtered_dict[src] = (uid, notes, tu)

    after_fmod_count = len(fmod_filtered_dict)
    print(f"After FMOD filter: {after_fmod_count} (removed {after_dedup_count - after_fmod_count} audio event paths)")

    # Step 3: Filter internal code variable names (snake_case trailing underscore)
    code_var_pattern = re.compile(r"^[a-z]+_[a-z0-9_]+_$")
    code_filtered_dict = {}

    for src, (uid, notes, tu) in fmod_filtered_dict.items():
        if not code_var_pattern.match(src):
            code_filtered_dict[src] = (uid, notes, tu)

    after_code_count = len(code_filtered_dict)
    print(f"After code variable filter: {after_code_count} (removed {after_fmod_count - after_code_count} trailing-underscore variables)")

    # Step 4: Filter pure asset handle names, card IDs, chunk keys, and render pipeline strings
    handle_suffixes = ("Prefab handle", "Spawning object", "animation collection handle", "Damage", "Cooldown")
    camel_no_space_pattern = re.compile(r"^[A-Z][a-zA-Z0-9]+$")

    card_id_re = re.compile(r"^[A-Z][a-zA-Z]+_[A-Z][a-zA-Z]+_[A-Za-z0-9_]+$")
    chunk_key_re = re.compile(r"^[a-z]+_[a-z0-9_]+_(chunk|lvl|level|scene)$")
    render_re = re.compile(r"^(system_|unity_)render_.*$", re.IGNORECASE)

    asset_filtered_dict = {}

    for src, (uid, notes, tu) in code_filtered_dict.items():
        should_drop = False

        if card_id_re.match(src) or chunk_key_re.match(src) or render_re.match(src):
            should_drop = True
        elif any(src.endswith(suffix) for suffix in handle_suffixes):
            prefix = src
            for suffix in handle_suffixes:
                if prefix.endswith(suffix):
                    prefix = prefix[:-len(suffix)].strip()
                    break

            if prefix and " " not in prefix and camel_no_space_pattern.match(prefix):
                should_drop = True

        if not should_drop:
            asset_filtered_dict[src] = (uid, notes, tu)

    after_asset_count = len(asset_filtered_dict)
    print(f"After asset handle & technical key filter: {after_asset_count} (removed {after_code_count - after_asset_count} technical keys & handles)")

    # Step 5: Build final clean XML body
    body = root.find(".//{urn:oasis:names:tc:xliff:document:1.2}body")
    if body is None:
        body = root.find(".//body")

    if body is not None:
        body.clear()
    else:
        file_elem = root.find(".//{urn:oasis:names:tc:xliff:document:1.2}file") or root.find(".//file")
        body = ET.SubElement(file_elem, "body")

    real_text_count = 0

    for src, (uid, notes, orig_tu) in asset_filtered_dict.items():
        tu = ET.SubElement(body, "{urn:oasis:names:tc:xliff:document:1.2}trans-unit")
        tu.attrib["id"] = uid
        
        src_elem = ET.SubElement(tu, "{urn:oasis:names:tc:xliff:document:1.2}source")
        src_elem.text = src
        
        target_elem = ET.SubElement(tu, "{urn:oasis:names:tc:xliff:document:1.2}target")
        target_elem.text = ""

        if notes:
            merged_note = " | ".join(notes[:5])
            note_elem = ET.SubElement(tu, "{urn:oasis:names:tc:xliff:document:1.2}note")
            note_elem.text = merged_note

        if " " in src or any(c.isupper() for c in src):
            real_text_count += 1

    # Write clean XML to file
    tree = ET.ElementTree(root)
    tree.write(output_xliff_path, encoding="utf-8", xml_declaration=True)

    print(f"\n==========================================")
    print(f"FINAL CLEAN SUMMARY:")
    print(f"  • Input trans-units: {input_count}")
    print(f"  • After deduplication: {after_dedup_count}")
    print(f"  • After FMOD filter: {after_fmod_count}")
    print(f"  • After code variable filter: {after_code_count}")
    print(f"  • After asset handle filter: {after_asset_count}")
    print(f"  • Final clean trans-units: {after_asset_count}")
    print(f"  • Estimated real human game text strings: ~{real_text_count}")
    print(f"Saved clean XLIFF to: '{output_xliff_path}'")
    print(f"==========================================\n")


if __name__ == "__main__":
    input_p = sys.argv[1] if len(sys.argv) > 1 else "ChildrenOfMorta_dlls.xliff"
    output_p = sys.argv[2] if len(sys.argv) > 2 else "ChildrenOfMorta_final.xliff"
    
    if os.path.exists(input_p):
        clean_xliff(input_p, output_p)
    else:
        print(f"Input file '{input_p}' not found!")
