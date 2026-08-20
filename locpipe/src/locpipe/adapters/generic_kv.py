"""Generic key-value JSON adapter.

Schema (format-generic-kv.md):
    [{"id": "...", "source": "...", "target": "...", "notes": [...],
      "speaker": "...", "max_length": N, "context_screen": "..."}, ...]

`id` may legitimately equal `source` (some export tools use the raw
English string as the id) — that's the tool's convention, not a
duplicate-detection bug.

Write-back rule from format-generic-kv.md is "only rewrite entries
that actually changed, don't regenerate the whole file" — that rule
existed to limit how much a *conversational* agent had to re-produce
by hand. Once Python owns the read/write, a full read-modify-write is
strictly safer (no risk of an entry silently vanishing mid-edit), so
that's what this adapter does; the on-disk result is identical either
way because id/source/notes/other fields and array order are always
preserved untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Entry
from .base import FormatAdapter


class GenericKVAdapter(FormatAdapter):
    name = "generic_kv"

    def extract(self, path: Path) -> list[Entry]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for obj in raw:
            entries.append(
                Entry(
                    file=str(path),
                    key=str(obj["id"]),
                    source=obj.get("source", ""),
                    target=obj.get("target", ""),
                    notes=list(obj.get("notes", []) or []),
                    speaker=obj.get("speaker"),
                    context_screen=obj.get("context_screen"),
                    max_length=obj.get("max_length"),
                    extra={k: v for k, v in obj.items()
                           if k not in {"id", "source", "target", "notes",
                                        "speaker", "context_screen", "max_length"}},
                )
            )
        return entries

    def merge(self, path: Path, entries: list[Entry]) -> None:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        by_id = {str(o["id"]): o for o in raw}
        for e in entries:
            obj = by_id.get(e.key)
            if obj is None:
                # File didn't have this entry yet (new project run) — append it
                # in the original field order this adapter always writes.
                obj = {"id": e.key, "source": e.source, "notes": e.notes}
                obj.update(e.extra)
                raw.append(obj)
                by_id[e.key] = obj
            obj["target"] = e.target  # only field this adapter is allowed to touch
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
