"""Derive the context key that scopes translation-memory reuse.

This exists because of a real gap in the naive "translate a unique
string once, reuse it everywhere" design: identical source text can
legitimately need different target text depending on who says it or
what sense of the word is meant. Two concrete examples already
documented in MindsEye's own project files (not hypothetical):

  * character-voices.md gives a character's register priority over
    the default project tone — so "Thanks!" from a blunt character
    and "Thanks!" from a formal narrator are not the same translation
    problem even though the source string is identical.
  * glossary-schema.md documents "Network" as a dual entry: "Hálózat"
    in an infrastructure context, "Tévéadó" in a content-discovery
    context. A pure source-string key can't tell those apart.

The fix: reuse (and cache) by (content_hash, category, context_key),
not by source text alone. context_key defaults to None for content
that has no notion of "speaker" (most UI/system strings), which is
exactly the common case where reuse is safe.

The lookup order below mirrors character-voice-schema.md's own
"how do we know who's speaking" priority list, so behavior here
matches what MindsEye's translator/QA skills already did by hand:
  1. an explicit speaker field on the entry
  2. the notes field's text
  3. the key/id naming pattern
  4. none of the above -> no context key (don't guess)
"""

from __future__ import annotations

import re
from typing import Optional

from .models import Entry

MatchedVia = str  # "speaker_field" | "notes_match" | "key_pattern" | "none"


def derive_context_key(
    entry: Entry, known_characters: set[str]
) -> tuple[Optional[str], MatchedVia]:
    if entry.speaker and entry.speaker.strip():
        return entry.speaker.strip(), "speaker_field"

    notes_text = " ".join(entry.notes or [])
    for name in known_characters:
        if name and re.search(rf"\b{re.escape(name)}\b", notes_text, re.IGNORECASE):
            return name, "notes_match"

    key_lower = (entry.key or "").lower()
    for name in known_characters:
        slug = name.lower().replace(" ", "_")
        if slug and slug in key_lower:
            return name, "key_pattern"

    return None, "none"


def build_tm_key(content_hash: str, category: str, context_key: Optional[str]) -> str:
    """The actual reuse/dedup key. Two entries only ever share a
    translation if they agree on all three components.
    """
    return f"{content_hash}:{category}:{context_key or '-'}"
