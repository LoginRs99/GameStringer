"""A format adapter's whole job: native file <-> list[Entry].

Nothing else in the pipeline is allowed to know about file syntax.
Add a new engine/format by writing one class here and registering it
in registry.py — no other module changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import Entry


class FormatAdapter(ABC):
    name: str

    def __init__(self, options: dict | None = None):
        self.options = options or {}

    @abstractmethod
    def extract(self, path: Path) -> list[Entry]:
        """Read a native file and return its entries. Only `source`
        needs to eventually reach the LLM — file/namespace/key/notes
        stay in Python per the original design goal: never send
        metadata to the model that it doesn't need.
        """
        raise NotImplementedError

    @abstractmethod
    def merge(self, path: Path, entries: list[Entry]) -> None:
        """Write translated entries back into the native file at path.
        Only `target` may change; everything else about the file's
        structure is preserved.
        """
        raise NotImplementedError
