"""Naninovel format adapter for LocPipe.

Supports both Naninovel localization document types:
1. Managed Text (Text/*.txt, CharacterNames.txt, DefaultUI.txt, etc.)
   Format:
     ; Source text (English)
     Key: Target text (Hungarian)

2. Script Localization Documents (Text/Scripts/*.txt)
   Format:
     # ID
     ; > Annotations (e.g. ; > ActorId: |#ID|)
     ; Source text
     Target text
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..models import Entry
from .base import FormatAdapter


class NaninovelAdapter(FormatAdapter):
    name = "naninovel"

    def __init__(self, options: dict | None = None):
        super().__init__(options)
        self.character_replacements: dict[str, str] = self.options.get(
            "character_replacements", {}
        )

    def extract(
        self, path: Path, audit_sink: list[tuple[str, str, str]] | None = None
    ) -> list[Entry]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if not text.strip():
            return []

        lines = text.splitlines()
        is_script = any(line.startswith("# ") or line == "#" for line in lines)
        if is_script:
            return self._extract_script(path, lines, audit_sink)
        return self._extract_managed(path, lines, audit_sink)

    def _extract_script(
        self, path: Path, lines: list[str], audit_sink: list[tuple[str, str, str]] | None
    ) -> list[Entry]:
        entries: list[Entry] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            if line.startswith("# ") or line == "#":
                key = line[2:].strip() if line.startswith("# ") else ""
                i += 1
                annos: list[str] = []
                sources: list[str] = []
                targets: list[str] = []
                speaker: str | None = None

                while i < n and (lines[i].startswith("; >") or lines[i].startswith(";>")):
                    ann_line = lines[i]
                    annos.append(ann_line)
                    m_spk = re.match(
                        r"^;\s*>\s*([^\s.:|]+)(?:\.[^\s.:|]+)?:\s*\|#",
                        ann_line,
                    )
                    if m_spk:
                        speaker = m_spk.group(1)
                    i += 1

                while i < n and lines[i].startswith(";") and not (
                    lines[i].startswith("; >") or lines[i].startswith(";>")
                ):
                    src_line = lines[i]
                    src = (
                        src_line[1:].lstrip(" ")
                        if src_line.startswith("; ")
                        else src_line[1:]
                    )
                    sources.append(src)
                    i += 1

                while i < n and not (lines[i].startswith("# ") or lines[i] == "#"):
                    curr = lines[i]
                    if not curr.startswith(";") and curr.strip():
                        targets.append(curr)
                    i += 1

                source_text = "\n".join(sources)
                target_text = "\n".join(targets)

                if not speaker and ":" in source_text:
                    m_prefix = re.match(r"^([^\s.:|]+):\s*(.*)$", source_text)
                    if m_prefix:
                        speaker = m_prefix.group(1)

                entry = Entry(
                    file=str(path),
                    key=key,
                    source=source_text,
                    target=target_text,
                    speaker=speaker,
                    notes=annos,
                    extra={"format_type": "script"},
                )
                entries.append(entry)
                if audit_sink is not None:
                    action = "kept" if source_text.strip() else "skipped: empty"
                    audit_sink.append((key, source_text, action))
            else:
                i += 1

        return entries

    def _extract_managed(
        self, path: Path, lines: list[str], audit_sink: list[tuple[str, str, str]] | None
    ) -> list[Entry]:
        entries: list[Entry] = []
        pending_comments: list[str] = []

        for line in lines:
            if line.startswith(";"):
                pending_comments.append(line)
            elif ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()

                src_lines = [
                    c[1:].lstrip(" ") if c.startswith("; ") else c[1:]
                    for c in pending_comments
                    if not (c.startswith("; >") or c.startswith(";>"))
                ]
                source_text = "\n".join(src_lines) if src_lines else (val or key)
                target_text = val

                entry = Entry(
                    file=str(path),
                    key=key,
                    source=source_text,
                    target=target_text,
                    notes=list(pending_comments),
                    extra={"format_type": "managed"},
                )
                entries.append(entry)
                if audit_sink is not None:
                    action = "kept" if source_text.strip() else "skipped: empty"
                    audit_sink.append((key, source_text, action))
                pending_comments = []

        return entries

    def merge(self, path: Path, entries: list[Entry]) -> None:
        if not path.exists():
            return
        orig_text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = orig_text.splitlines()
        is_script = any(line.startswith("# ") or line == "#" for line in lines)

        by_key = {e.key: e for e in entries}

        if is_script:
            new_text = self._merge_script(orig_text, lines, by_key)
        else:
            new_text = self._merge_managed(orig_text, lines, by_key)

        path.write_text(new_text, encoding="utf-8", newline="\n")

    def _apply_replacements(self, text: str) -> str:
        for src_ch, rep_ch in self.character_replacements.items():
            text = text.replace(src_ch, rep_ch)
        return text

    def _merge_script(
        self, orig_text: str, lines: list[str], by_key: dict[str, Entry]
    ) -> str:
        leading: list[str] = []
        i = 0
        n = len(lines)
        while i < n and not (lines[i].startswith("# ") or lines[i] == "#"):
            leading.append(lines[i])
            i += 1

        out_lines = list(leading)

        while i < n:
            if lines[i].startswith("# ") or lines[i] == "#":
                id_line = lines[i]
                key = id_line[2:].strip() if id_line.startswith("# ") else ""
                i += 1
                annos: list[str] = []
                sources: list[str] = []
                existing_targets: list[str] = []
                trailing: list[str] = []

                while i < n and (lines[i].startswith("; >") or lines[i].startswith(";>")):
                    annos.append(lines[i])
                    i += 1
                while i < n and lines[i].startswith(";") and not (
                    lines[i].startswith("; >") or lines[i].startswith(";>")
                ):
                    sources.append(lines[i])
                    i += 1
                while i < n and not (lines[i].startswith("# ") or lines[i] == "#"):
                    curr = lines[i]
                    if not curr.startswith(";") and curr.strip():
                        existing_targets.append(curr)
                    else:
                        trailing.append(curr)
                    i += 1

                out_lines.append(id_line)
                out_lines.extend(annos)
                out_lines.extend(sources)

                entry = by_key.get(key)
                if entry and entry.target.strip():
                    rep_target = self._apply_replacements(entry.target)
                    out_lines.extend(rep_target.splitlines())
                elif existing_targets:
                    out_lines.extend(existing_targets)

                out_lines.extend(trailing)
            else:
                i += 1

        result = "\n".join(out_lines)
        if orig_text.endswith("\n"):
            result += "\n"
        return result

    def _merge_managed(
        self, orig_text: str, lines: list[str], by_key: dict[str, Entry]
    ) -> str:
        out_lines: list[str] = []
        for line in lines:
            if ":" in line and not line.startswith(";") and not line.startswith("#"):
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                entry = by_key.get(key)
                if entry and entry.target.strip():
                    rep_target = self._apply_replacements(entry.target)
                    if "\n" in rep_target:
                        rep_target = rep_target.replace("\r\n", "<br>").replace("\n", "<br>")
                    out_lines.append(f"{key}: {rep_target}")
                else:
                    out_lines.append(line)
            else:
                out_lines.append(line)

        result = "\n".join(out_lines)
        if orig_text.endswith("\n"):
            result += "\n"
        return result
