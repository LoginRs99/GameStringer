"""Standard GNU gettext .po adapter, per format-po-gettext.md.

Uses polib rather than hand-parsing .po syntax — multi-line strings,
escaping, and comment blocks are exactly the kind of fiddly text
format where reusing a mature, well-tested parser beats a hand-rolled
one, for the same reason the rest of this project reuses MindsEye's
own validators instead of rewriting them.

Two things from the spec worth calling out because they shaped the
design, not just implementation notes:

  * msgctxt is gettext's own native context key — when present, it's
    a stronger, authoritative signal than the speaker-guessing
    heuristic in context_key.py (which exists for formats, like
    generic_kv, that have no built-in notion of context at all). This
    adapter sets Entry.context_key directly from msgctxt at extraction
    time; classify.py only falls back to guessing when an adapter
    hasn't already supplied one.

  * Plural entries (msgid_plural / msgstr[N]) are handled per the
    header's actual Plural-Forms line, never invented. Each msgstr[N]
    becomes its own Entry so the pipeline's normal dedup/TM/validation
    machinery applies to it unchanged — but this treats each plural
    form as an independent string rather than translating all of a
    language's forms jointly with awareness of each other. That's a
    real simplification, flagged here rather than silently shipped:
    for a language where forms 0 and 1 should end up textually
    identical (Hungarian, per the spec's own note), independent
    translation makes that harder to guarantee than a joint call
    would. Worth revisiting before this adapter handles a
    plural-heavy project.
"""

from __future__ import annotations

import re
from pathlib import Path

import polib

from ..models import Entry
from .base import FormatAdapter

_NPLURALS_RE = re.compile(r"nplurals\s*=\s*(\d+)")


def _key(msgctxt: str | None, msgid: str, plural_index: int | None = None) -> str:
    base = f"{msgctxt}\x04{msgid}" if msgctxt else msgid
    return base if plural_index is None else f"{base}[{plural_index}]"


def _nplurals_from_header(po: polib.POFile) -> int:
    """Read the actual count from Plural-Forms rather than assume —
    format-po-gettext.md is explicit that this must never be invented,
    and Hungarian .po files legitimately vary between nplurals=1 and
    the conventional nplurals=2 depending on the project's toolchain.
    """
    header = po.metadata.get("Plural-Forms", "")
    m = _NPLURALS_RE.search(header)
    return int(m.group(1)) if m else 2  # 2 is polib's own fallback for a missing header


class PoGettextAdapter(FormatAdapter):
    name = "po_gettext"

    def extract(self, path: Path) -> list[Entry]:
        po = polib.pofile(str(path))
        entries: list[Entry] = []
        for e in po:
            if e.obsolete or not e.msgid:  # skip obsolete entries and the header ("")
                continue
            notes = [n for n in (e.comment, e.tcomment) if n]
            if e.msgid_plural:
                is_fuzzy = "fuzzy" in e.flags
                expected_indices = e.msgstr_plural.keys() or range(_nplurals_from_header(po))
                for idx in sorted(expected_indices):
                    entries.append(
                        Entry(
                            file=str(path),
                            key=_key(e.msgctxt, e.msgid, idx),
                            source=e.msgid if idx == 0 else e.msgid_plural,
                            # fuzzy means "draft, not confirmed" -- same rule as the singular
                            # branch below, so a fuzzy plural draft still gets re-translated
                            # instead of silently being treated as already approved.
                            target="" if is_fuzzy else e.msgstr_plural.get(idx, ""),
                            notes=notes,
                            context_key=e.msgctxt,
                            extra={"is_plural": True, "plural_index": idx, "fuzzy": is_fuzzy},
                        )
                    )
            else:
                entries.append(
                    Entry(
                        file=str(path),
                        key=_key(e.msgctxt, e.msgid),
                        source=e.msgid,
                        target="" if "fuzzy" in e.flags else e.msgstr,  # fuzzy == not actually approved yet
                        notes=notes,
                        context_key=e.msgctxt,
                        extra={"is_plural": False, "fuzzy": "fuzzy" in e.flags},
                    )
                )
        return entries

    def merge(self, path: Path, entries: list[Entry]) -> None:
        po = polib.pofile(str(path))
        by_msgid: dict[tuple, polib.POEntry] = {(e.msgctxt, e.msgid): e for e in po}

        for entry in entries:
            if entry.extra.get("is_plural"):
                po_entry = None
                for (ctxt, msgid), candidate in by_msgid.items():
                    if ctxt == entry.context_key and candidate.msgid_plural and (
                        msgid == entry.source or candidate.msgid_plural == entry.source
                    ):
                        po_entry = candidate
                        break
                if po_entry is None:
                    continue
                po_entry.msgstr_plural[entry.extra["plural_index"]] = entry.target
            else:
                po_entry = by_msgid.get((entry.context_key, entry.source))
                if po_entry is None:
                    continue
                po_entry.msgstr = entry.target

            if entry.target.strip() and "fuzzy" in po_entry.flags:
                po_entry.flags.remove("fuzzy")  # only remove on an actual confirmed translation

        path.parent.mkdir(parents=True, exist_ok=True)
        po.save(str(path))
