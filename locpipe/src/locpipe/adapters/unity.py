"""Unity CSV adapter.

Ported from a working reference implementation found while comparing
locpipe against a parallel, independently-built pipeline (see
README.md's "Bugs found and fixed" section) — the column-detection
and composite-key logic below is theirs, tested against a real Unity
export; this file adapts it to locpipe's FormatAdapter/Entry contract
and generalizes the one thing that was specific to their setup: the
target column name was hardcoded to "Hungarian". Here it comes from
config.target_lang (or an explicit override — see below), so the same
adapter works for any language pair, not just one project's.

Column names are detected heuristically (case-insensitive), since
Unity CSV exports vary project to project:
  id column:      "id", "key"
  source column:  "english", "source", "source text", "en"
  keyname column: "keyname", "key_name", "key"     (optional)
  type column:    "type", "content_type", "category"  (optional, maps to Entry.category hint)
  target column:  target_lang's name/code, or "target", "target text" -- appended if missing

Composite id (id + keyname) guards against a real, common Unity export
quirk: numeric ids that repeat across different content types (e.g.
UI text and narrative text sharing the same id sequence). Only used
when a keyname column exists and differs from the id column.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from ..models import Entry
from .base import FormatAdapter

_UNIT_SEP = "\x1f"  # internal composite-key delimiter, never appears in real CSV text


def _find_column(header: list[str], candidates: list[str], default_idx: int) -> int:
    header_lower = [h.lower().strip() for h in header]
    for candidate in candidates:
        if candidate.lower() in header_lower:
            return header_lower.index(candidate.lower())
    return default_idx


def _composite_key(raw_id: str, keyname: str, id_idx: int, keyname_idx: int) -> str:
    if keyname and keyname_idx != id_idx:
        return f"{raw_id}{_UNIT_SEP}{keyname}"
    return raw_id


class UnityCSVAdapter(FormatAdapter):
    name = "unity"

    def __init__(
        self,
        target_column_names: Optional[list[str]] = None,
        source_column_names: Optional[list[str]] = None,
        max_length_column_names: Optional[list[str]] = None,
    ):
        # Extra candidate names for the target/source columns, beyond the
        # generics -- e.g. project.yaml's format_options:
        #   source_column_names: ["Original_German_To_Replace", "German"]
        #   target_column_names: ["Hungarian_Translation", "Hungarian"]
        self.target_column_names = target_column_names or []
        self.source_column_names = source_column_names or []
        # Opt-in: only set this if your actual export has a real per-row
        # character-limit column (some Unity localization exports do, from
        # the UI component's own max-length setting). If it's not there,
        # entry.max_length stays None for this adapter's rows -- classify.py's
        # CategoryRule.default_max_length is the fallback for "no such column,
        # but I know the limit anyway" (a static per-category number).
        self.max_length_column_names = max_length_column_names or []

    def extract(self, path: Path) -> list[Entry]:
        entries = []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return entries

            id_idx = _find_column(header, ["id", "key"], 0)
            source_idx = _find_column(
                header, [*self.source_column_names, "english", "source", "source text", "en"], 2
            )
            en_idx = _find_column(header, ["english", "english_source", "english_text", "en"], -1)
            keyname_idx = _find_column(header, ["keyname", "key_name", "key"], -1)
            type_idx = _find_column(header, ["type", "content_type", "category"], -1)
            target_idx = _find_column(
                header, [*self.target_column_names, "target", "target text"], -1
            )
            max_length_idx = _find_column(
                header, [*self.max_length_column_names, "max_length", "char_limit", "character_limit"], -1
            )

            for row in reader:
                if not row or len(row) <= max(id_idx, 0):
                    continue
                raw_id = row[id_idx] if id_idx < len(row) else ""
                source_text = row[source_idx] if 0 <= source_idx < len(row) else ""
                if not source_text.strip() and 0 <= en_idx < len(row):
                    source_text = row[en_idx]
                if not source_text.strip():
                    continue
                keyname = row[keyname_idx].strip() if 0 <= keyname_idx < len(row) else ""
                existing_target = row[target_idx].strip() if 0 <= target_idx < len(row) else ""

                content_type_hint = None
                if 0 <= type_idx < len(row):
                    t_val = row[type_idx].lower().strip()
                    if t_val:
                        content_type_hint = t_val

                max_length: Optional[int] = None
                if 0 <= max_length_idx < len(row):
                    raw_max_len = row[max_length_idx].strip()
                    if raw_max_len.isdigit():
                        max_length = int(raw_max_len)
                    # non-numeric/blank cell -- leave as None rather than guess or crash;
                    # CategoryRule.default_max_length is the fallback path for this row.

                # content_type_hint also goes into notes -- not just extra --
                # so a project.yaml category rule can actually route on it via
                # match_notes_regex (e.g. r"type:dialogue"). Many real Unity
                # exports have exactly this column (distinguishing UI/dialogue/
                # item text), and it's a much more reliable classification
                # signal than guessing from speaker-presence or key patterns
                # alone -- wiring it up here means it isn't captured for
                # nothing.
                notes = [f"type:{content_type_hint}"] if content_type_hint else []

                entries.append(
                    Entry(
                        file=str(path),
                        key=_composite_key(raw_id, keyname, id_idx, keyname_idx),
                        source=source_text,
                        target=existing_target,
                        max_length=max_length,
                        notes=notes,
                        extra={"content_type_hint": content_type_hint} if content_type_hint else {},
                    )
                )
        return entries

    def merge(self, path: Path, entries: list[Entry]) -> None:
        by_key = {e.key: e.target for e in entries}

        with open(path, "r", encoding="utf-8-sig", newline="") as fin:
            reader = csv.reader(fin)
            rows = list(reader)
        if not rows:
            return
        header, data_rows = rows[0], rows[1:]

        id_idx = _find_column(header, ["id", "key"], 0)
        keyname_idx = _find_column(header, ["keyname", "key_name", "key"], -1)
        target_idx = _find_column(header, [*self.target_column_names, "target", "target text"], -1)

        if target_idx == -1:
            target_idx = len(header)
            header = [*header, (self.target_column_names[0] if self.target_column_names else "target")]

        out_rows = [header]
        for row in data_rows:
            if not row:
                out_rows.append(row)
                continue
            raw_id = row[id_idx] if id_idx < len(row) else ""
            keyname = row[keyname_idx].strip() if 0 <= keyname_idx < len(row) else ""
            lookup_key = _composite_key(raw_id, keyname, id_idx, keyname_idx)

            if lookup_key in by_key:
                row = list(row)
                while len(row) <= target_idx:
                    row.append("")
                row[target_idx] = by_key[lookup_key]
            out_rows.append(row)

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as fout:
            csv.writer(fout).writerows(out_rows)

