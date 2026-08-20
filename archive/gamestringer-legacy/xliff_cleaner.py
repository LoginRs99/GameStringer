"""
XLIFF Cleaner Utility for GameStringer.

Cleans and deduplicates extracted XLIFF 1.2 files prior to translation.
Filters out internal Unity engine noise, animation clips, C# code symbols, hardware strings, and prefab handles.
"""

import sys
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

ET.register_namespace('', "urn:oasis:names:tc:xliff:document:1.2")

UI_SINGLE_WORDS = {
    'ok', 'yes', 'no', 'cancel', 'back', 'play', 'start', 'quit', 'exit', 'save', 'load',
    'settings', 'options', 'inventory', 'map', 'quest', 'quests', 'achievements', 'credits',
    'continue', 'pause', 'resume', 'retry', 'skip', 'confirm', 'delete', 'rename', 'hp', 'mp',
    'level', 'gold', 'health', 'mana', 'armor', 'weapon', 'skills', 'items', 'status', 'teleport',
    'close', 'open', 'buy', 'sell', 'equip', 'unequip', 'use', 'take', 'drop', 'outline', 'help',
    'tutorial', 'chapter', 'stage', 'wave', 'round', 'turn', 'score', 'combo', 'solo', 'coop'
}

TECHNICAL_PATTERNS = [
    r'animator', r'idle sequence', r'collection handle', r'narrative handle', r'datacontainer',
    r'environment', r'prefab', r'event:/', r'snapshot:/', r'm_name', r'm_script', r'm_color',
    r'lightprefab', r'talentasset', r'sequence', r'throwasset', r'codex entry asset',
    r'inventory item asset', r'dos mode', r'specular color', r'base layer', r'china only',
    r'firstframe', r'tunon_', r'spawning object', r'generator asset', r'chunk asset',
    r'camera handle', r'sound handle', r'fx handle', r'handler', r'component', r'condition',
    r'saitek', r'8bitdo', r'dual box', r'instance', r'node', r'layer', r'vfx_', r'ui/extensions',
    r'gamepad', r'joystick', r'controller', r'srclength', r'precisionflag', r'debugtypes',
    r'netaction', r'pdefault', r'transition animation', r'button \d+', r'stat', r'manager'
]


def is_genuine_ingame_text(s: str) -> bool:
    """Strict filter to determine if a string is genuine in-game human text."""
    if not s or len(s) < 2:
        return False
        
    s_str = s.strip()
    low = s_str.lower()

    # 1. Reject paths, assets, prefabs, anims, csv, FMOD, technical tags
    if re.search(r'\.(prefab|anim|png|wav|mp3|ogg|asset|mat|controller|shad|unity3d|bundle|csv)$', low):
        return False
    if 'assets/' in low or 'assets\\' in low or 'event:/' in low or 'snapshot:/' in low:
        return False

    # 2. Reject technical keywords
    for pat in TECHNICAL_PATTERNS:
        if re.search(pat, low):
            return False

    # 3. Reject Unity C# log strings & hardware device names & code methods
    if 'can\'t set' in low or 'can\'t find' in low or '{0}' in s_str or '{1}' in s_str or 'vector' in low or 'set_' in low or 'get_' in low:
        return False

    # 4. Single word checks: Drop any single word with no spaces unless it's a known UI word
    if ' ' not in s_str:
        if low not in UI_SINGLE_WORDS:
            return False

    # 5. Multi-word checks: Drop if ends with _[0-9]+ or contains asset handles / technical suffixes
    if re.search(r'_[0-9]+$', s_str) and not any(p in s_str for p in '.,!?:;'):
        return False
    if re.search(r' - (casual|move|stand|sheathed|side|up|down|idle|talk|action|dive|jump|attack|hit|die|stat|skin)', low):
        return False

    # 6. Must contain letters
    if not re.search(r'[a-zA-Z\u00C0-\u024F]', s_str):
        return False

    return True


def clean_xliff(input_xliff_path: str, output_xliff_path: str) -> None:
    print(f"Reading input XLIFF: {input_xliff_path}...")
    
    with open(input_xliff_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Clean non-XML control characters
    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
    root = ET.fromstring(xml_clean)

    all_units = [tu for tu in root.iter() if tu.tag.endswith('trans-unit')]
    input_count = len(all_units)
    print(f"Input trans-units: {input_count}")

    # Deduplicate by exact source text
    dedup_dict: Dict[str, Tuple[str, List[str], ET.Element]] = {}
    
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

        if not src_text or not is_genuine_ingame_text(src_text):
            continue

        if src_text not in dedup_dict:
            dedup_dict[src_text] = (uid, [note_text] if note_text else [], tu)
        else:
            existing_uid, existing_notes, existing_tu = dedup_dict[src_text]
            if note_text and note_text not in existing_notes:
                existing_notes.append(note_text)
            if len(uid) < len(existing_uid):
                dedup_dict[src_text] = (uid, existing_notes, tu)

    after_clean_count = len(dedup_dict)
    print(f"After strict noise filter: {after_clean_count} (removed {input_count - after_clean_count} technical noise items)")

    # Build final clean XML body
    body = root.find(".//{urn:oasis:names:tc:xliff:document:1.2}body") or root.find(".//body")

    if body is not None:
        body.clear()
    else:
        file_elem = root.find(".//{urn:oasis:names:tc:xliff:document:1.2}file") or root.find(".//file")
        body = ET.SubElement(file_elem, "body")

    for src, (uid, notes, orig_tu) in dedup_dict.items():
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

    tree = ET.ElementTree(root)
    tree.write(output_xliff_path, encoding="utf-8", xml_declaration=True)

    print(f"\n==========================================")
    print(f"FINAL CLEAN SUMMARY:")
    print(f"  • Input trans-units: {input_count}")
    print(f"  • Clean in-game text trans-units: {after_clean_count}")
    print(f"Saved clean XLIFF to: '{output_xliff_path}'")
    print(f"==========================================\n")


if __name__ == "__main__":
    input_p = sys.argv[1] if len(sys.argv) > 1 else "output/raw_COM_output.xliff"
    output_p = sys.argv[2] if len(sys.argv) > 2 else "output/COM_output.xliff"
    
    if os.path.exists(input_p):
        clean_xliff(input_p, output_p)
    else:
        print(f"Input file '{input_p}' not found!")
