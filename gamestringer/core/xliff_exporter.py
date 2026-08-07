"""
XLIFF 1.2 Exporter, Reader, Validator, and Updater for GameStringer CLI.

Generates and parses standard XLIFF 1.2 XML localization files with NFC Unicode
normalization, XML 1.0 control character sanitization, token mismatch validation,
and game patch diff/update support.
"""

import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional, Any
from gamestringer.core.base_engine import TransUnit

XLIFF_NS = "urn:oasis:names:tc:xliff:document:1.2"
TOKEN_PATTERN = re.compile(r"(\{[^{}]+\})")
XML_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff\ufffe\uffff]")


def clean_xml_text(text: str) -> str:
    """Filter out characters that are invalid in XML 1.0 documents (control chars, surrogates, non-characters 0xFFFE/0xFFFF)."""
    if not text:
        return ""
    return XML_CONTROL_CHAR_RE.sub("", text)


def normalize_nfc(text: str) -> str:
    """Normalize string to Unicode NFC (composed form) and sanitize XML control chars."""
    if not text:
        return ""
    try:
        normalized = unicodedata.normalize("NFC", text)
    except Exception:
        normalized = text
    return clean_xml_text(normalized)


def _format_xml(element: ET.Element) -> str:
    """Format ElementTree Element as XML string."""
    try:
        ET.indent(element, space="  ")
    except Exception:
        pass
    rough_bytes = ET.tostring(element, encoding="utf-8", xml_declaration=True)
    return rough_bytes.decode("utf-8")


def export_xliff(
    units: List[TransUnit],
    output_path: str,
    source_lang: str = "en",
    target_lang: str = "it",
    engine_name: str = "gamestringer",
) -> str:
    """
    Export a list of TransUnit objects to an XLIFF 1.2 XML file with NFC normalization.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    root = ET.Element("xliff", {
        "version": "1.2",
        "xmlns": XLIFF_NS,
    })

    # Group units by original relative file path
    units_by_file: Dict[str, List[TransUnit]] = {}
    for unit in units:
        file_key = unit.file_path or "default_game_text"
        if file_key not in units_by_file:
            units_by_file[file_key] = []
        units_by_file[file_key].append(unit)

    for file_path, file_units in units_by_file.items():
        file_elem = ET.SubElement(root, "file", {
            "source-language": source_lang,
            "target-language": target_lang,
            "datatype": "plaintext",
            "original": clean_xml_text(file_path),
        })

        header_elem = ET.SubElement(file_elem, "header")
        tool_elem = ET.SubElement(header_elem, "tool", {
            "tool-id": "gamestringer-cli",
            "tool-name": f"GameStringer CLI ({engine_name})" if engine_name else "GameStringer CLI",
            "tool-version": "1.0.0",
        })

        body_elem = ET.SubElement(file_elem, "body")

        for unit in file_units:
            trans_unit = ET.SubElement(body_elem, "trans-unit", {"id": clean_xml_text(unit.id)})

            source_elem = ET.SubElement(trans_unit, "source")
            source_elem.text = normalize_nfc(unit.source or "")

            target_elem = ET.SubElement(trans_unit, "target")
            target_elem.text = normalize_nfc(unit.target or "")

            # Build metadata note tag
            notes = []
            if engine_name:
                notes.append(f"engine:{clean_xml_text(engine_name)}")
            if unit.file_path:
                notes.append(f"file:{clean_xml_text(unit.file_path)}")
            if unit.line_number is not None:
                notes.append(f"line:{unit.line_number}")
            if unit.namespace:
                notes.append(f"namespace:{clean_xml_text(unit.namespace)}")
            if unit.key:
                notes.append(f"key:{clean_xml_text(unit.key)}")
            if unit.speaker:
                notes.append(f"speaker:{clean_xml_text(unit.speaker)}")
            if unit.context_note:
                notes.append(f"context:{clean_xml_text(unit.context_note)}")

            if notes:
                note_elem = ET.SubElement(trans_unit, "note")
                note_elem.text = " | ".join(notes)

    xml_text = _format_xml(root)

    with open(output_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(xml_text)

    return output_path


def parse_xliff(xliff_path: str) -> List[TransUnit]:
    """
    Parse an XLIFF 1.2 XML file into a list of TransUnit objects with NFC normalization.
    """
    if not os.path.exists(xliff_path):
        raise FileNotFoundError(f"XLIFF file not found: {xliff_path}")

    # Read and clean XML content if invalid control chars exist
    with open(xliff_path, "r", encoding="utf-8", errors="replace") as f:
        raw_xml = f.read()

    cleaned_xml = clean_xml_text(raw_xml)
    root = ET.fromstring(cleaned_xml)

    units: List[TransUnit] = []

    for file_elem in root.iter():
        if file_elem.tag.endswith("file") or file_elem.tag == "file":
            original_file = file_elem.attrib.get("original", "")

            for tu in file_elem.iter():
                if tu.tag.endswith("trans-unit") or tu.tag == "trans-unit":
                    tu_id = tu.attrib.get("id", "")
                    source_text = ""
                    target_text = ""
                    note_text = ""

                    for child in tu:
                        tag_name = child.tag.split("}")[-1]
                        if tag_name == "source":
                            source_text = normalize_nfc(child.text or "")
                        elif tag_name == "target":
                            target_text = normalize_nfc(child.text or "")
                        elif tag_name == "note":
                            note_text = child.text or ""

                    line_number = None
                    namespace = None
                    key = None
                    speaker = None
                    context_note = None

                    if note_text:
                        parts = [p.strip() for p in note_text.split("|")]
                        for part in parts:
                            if part.startswith("line:"):
                                try:
                                    line_number = int(part.split(":", 1)[1])
                                except ValueError:
                                    pass
                            elif part.startswith("namespace:"):
                                namespace = part.split(":", 1)[1]
                            elif part.startswith("key:"):
                                key = part.split(":", 1)[1]
                            elif part.startswith("speaker:"):
                                speaker = part.split(":", 1)[1]
                            elif part.startswith("context:"):
                                context_note = part.split(":", 1)[1]

                    units.append(TransUnit(
                        id=tu_id,
                        source=source_text,
                        target=target_text,
                        file_path=original_file,
                        line_number=line_number,
                        namespace=namespace,
                        key=key,
                        speaker=speaker,
                        context_note=context_note,
                    ))

    return units


def validate_xliff(xliff_path: str) -> Dict[str, Any]:
    """
    Validate an XLIFF file for completeness and token safety.

    :param xliff_path: Path to .xliff file
    :return: Report dict containing stats, token mismatches, and validity boolean
    """
    units = parse_xliff(xliff_path)
    total = len(units)
    translated = 0
    untranslated = 0
    token_mismatches = []

    for u in units:
        src = u.source or ""
        tgt = u.target or ""

        if tgt and tgt.strip():
            translated += 1

            src_tokens = set(TOKEN_PATTERN.findall(src))
            tgt_tokens = set(TOKEN_PATTERN.findall(tgt))

            missing_tokens = src_tokens - tgt_tokens
            if missing_tokens:
                token_mismatches.append({
                    "id": u.id,
                    "source": src,
                    "target": tgt,
                    "missing_tokens": list(missing_tokens),
                })
        else:
            untranslated += 1

    is_valid = (untranslated == 0) and (len(token_mismatches) == 0)

    return {
        "total": total,
        "translated": translated,
        "untranslated": untranslated,
        "token_mismatches": token_mismatches,
        "valid": is_valid,
    }


def update_xliff(old_xliff_path: str, new_extracted_units: List[TransUnit], output_path: str) -> Tuple[str, Dict[str, int]]:
    """
    Merge newly extracted game strings with an old translated XLIFF file.
    """
    old_units = parse_xliff(old_xliff_path)
    old_map_by_id = {u.id: u for u in old_units}
    old_map_by_src = {u.source: u for u in old_units if u.source}

    merged_units: List[TransUnit] = []
    stats = {"kept": 0, "new": 0, "deprecated": 0}

    seen_new_ids = set()

    for new_u in new_extracted_units:
        seen_new_ids.add(new_u.id)

        matched_old = old_map_by_id.get(new_u.id) or old_map_by_src.get(new_u.source)
        if matched_old and matched_old.target and matched_old.target.strip():
            new_u.target = matched_old.target
            stats["kept"] += 1
        else:
            stats["new"] += 1

        merged_units.append(new_u)

    for old_u in old_units:
        if old_u.id not in seen_new_ids and old_u.source not in [u.source for u in new_extracted_units]:
            note = old_u.context_note or ""
            old_u.context_note = f"status:deprecated | {note}".strip(" |")
            merged_units.append(old_u)
            stats["deprecated"] += 1

    saved_path = export_xliff(merged_units, output_path)
    return saved_path, stats
