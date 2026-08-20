"""Phase 14. Groups entries by source file and hands each group to the
format adapter's merge(). No format-specific logic here — that's the
adapter's job (see adapters/base.py).
"""

from __future__ import annotations

from pathlib import Path

from .adapters.base import FormatAdapter
from .models import Entry


def merge_all(entries: list[Entry], adapter: FormatAdapter) -> list[Path]:
    by_file: dict[str, list[Entry]] = {}
    for e in entries:
        by_file.setdefault(e.file, []).append(e)

    written = []
    for file_path, file_entries in by_file.items():
        path = Path(file_path)
        adapter.merge(path, file_entries)
        written.append(path)
    return written
