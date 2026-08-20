"""Phase 7 (context classification) + the context-key half of the
dedup fix, run together because a category's needs_character_voice
flag is what decides whether "no context key found" is worth flagging
as uncertain or is simply expected (most UI/system strings have no
speaker at all, and that's fine).
"""

from __future__ import annotations

from .config import ProjectConfig
from .context_key import derive_context_key
from .models import Entry


def classify_entries(
    entries: list[Entry], config: ProjectConfig, known_characters: set[str]
) -> list[Entry]:
    for entry in entries:
        rule = config.classify(entry)
        entry.category = rule.name

        if entry.max_length is None and rule.default_max_length is not None:
            entry.max_length = rule.default_max_length

        if entry.context_key is not None:
            continue  # adapter already supplied an authoritative one (e.g. gettext msgctxt) — don't override

        if rule.needs_character_voice:
            context_key, matched_via = derive_context_key(entry, known_characters)
            entry.context_key = context_key
            if context_key is None:
                entry.extra["_speaker_uncertain"] = True
        else:
            entry.context_key = None

    return entries
