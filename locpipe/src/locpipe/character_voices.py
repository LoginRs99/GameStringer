"""Parses a project's character-voices.md into per-character rows so a
dialogue batch that only has lines from 2 characters doesn't have to
carry the whole cast's voice bible into the prompt every time. Same
spirit as glossary.prune_for_batch: a cheap, table-row-level filter,
biased toward keeping a row if there's any doubt, since a false
positive just costs a few extra tokens and a false negative costs a
character speaking in the wrong register.

classify.py's load_known_characters() (pipeline.py) already parses
this same file, but only into a flat set of names -- enough to check
"is this speaker known" but not enough to keep just some rows and drop
others. This module keeps the actual row text instead.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|")


@lru_cache(maxsize=None)
def load_character_voice_rows(path: Optional[Path]) -> tuple[list[str], dict[str, str]]:
    """Returns (preamble_lines, {character_name: full_row_line}).

    preamble_lines is everything before and including the table header
    and its `|---|...` separator (title, any intro prose, the header
    row) -- always kept verbatim regardless of which characters end up
    selected, since it's small and the table means nothing without it.
    """
    if path is None or not path.exists():
        return [], {}

    preamble: list[str] = []
    rows: dict[str, str] = {}
    header_done = False

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        m = _ROW_RE.match(stripped)
        if not m:
            if not header_done:
                preamble.append(line)
            continue

        name = m.group(1).strip()
        if set(name) <= {"-", ":"}:
            # the |---|---| separator row -- last line of the preamble
            preamble.append(line)
            header_done = True
            continue
        if not header_done:
            # this is the header row itself (e.g. "| Character | Register | ... |")
            preamble.append(line)
            continue
        if not name or name.lower() in ("character", "szereplő"):
            continue

        rows[name] = line

    return preamble, rows


def prune_character_voices_for_batch(
    preamble: list[str], rows: dict[str, str], speakers: set[str]
) -> str:
    """Keep only the rows for characters actually speaking in this batch.

    A speaker name that isn't in the table just means nothing gets added
    for them here -- that's a distinct, already-handled signal elsewhere
    (classify.py flags unknown speakers via _speaker_uncertain), not this
    function's job to catch.
    """
    if not rows:
        return "\n".join(preamble).strip() or "(no character voice bible provided)"

    kept = [line for name, line in rows.items() if name in speakers]
    if not kept:
        # category needs a voice but nobody in THIS batch matched a known
        # row -- still send the preamble/header rather than an empty
        # table, and let classify.py's speaker-uncertain flag (already
        # dedicated to exactly this case) do the actual flagging.
        return "\n".join(preamble).strip() or "(no character voice bible provided)"

    return "\n".join(preamble + kept)
