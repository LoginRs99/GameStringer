"""XLIFF 1.2 Format Adapter for LocPipe.

Extracts and merges trans-units from standard XLIFF 1.2 files.
"""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from ..models import Entry
from .base import FormatAdapter

ET.register_namespace('', "urn:oasis:names:tc:xliff:document:1.2")


class XLIFFAdapter(FormatAdapter):
    name = "xliff"

    def __init__(self, options: dict | None = None):
        super().__init__(options)

    def extract(self, path: Path) -> list[Entry]:
        content = path.read_text(encoding="utf-8", errors="ignore")
        xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
        root = ET.fromstring(xml_clean)

        entries: list[Entry] = []
        for tu in root.iter():
            if not tu.tag.endswith("trans-unit"):
                continue

            uid = tu.attrib.get("id", "")
            src_text = ""
            tgt_text = ""
            notes: list[str] = []

            for child in tu:
                tag_name = child.tag.split("}")[-1]
                if tag_name == "source" and child.text:
                    src_text = child.text
                elif tag_name == "target" and child.text:
                    tgt_text = child.text
                elif tag_name == "note" and child.text:
                    notes.append(child.text.strip())

            if src_text:
                entries.append(
                    Entry(
                        file=str(path),
                        key=uid,
                        source=src_text,
                        target=tgt_text,
                        notes=notes,
                    )
                )

        return entries

    def merge(self, path: Path, entries: list[Entry]) -> None:
        content = path.read_text(encoding="utf-8", errors="ignore")
        xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', content)
        root = ET.fromstring(xml_clean)

        key_to_entry = {e.key: e for e in entries}
        replacements = self.options.get("character_replacements", {})

        for tu in root.iter():
            if not tu.tag.endswith("trans-unit"):
                continue

            uid = tu.attrib.get("id", "")
            if uid not in key_to_entry:
                continue

            entry = key_to_entry[uid]
            target_elem = None

            for child in tu:
                tag_name = child.tag.split("}")[-1]
                if tag_name == "target":
                    target_elem = child
                    break

            if target_elem is None:
                target_elem = ET.SubElement(tu, "{urn:oasis:names:tc:xliff:document:1.2}target")

            target_text = entry.target
            if target_text and replacements:
                for old_char, new_char in replacements.items():
                    target_text = target_text.replace(old_char, new_char)

            target_elem.text = target_text

        tree = ET.ElementTree(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)
