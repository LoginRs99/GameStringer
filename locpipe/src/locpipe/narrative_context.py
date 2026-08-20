"""Narrative-boundary grouping + preceding-context injection.

Ported from a parallel implementation's idea (see README's "Bugs found
and fixed"), with one deliberate change from how they built it: they
computed "preceding context" globally, as simply whatever N entries
came right before this one in raw file order. That can pull context
from a *different* scene into a batch if a scene is short — this
version computes preceding context *within* a boundary group instead,
so a scene's dialogue only ever sees prior lines from the same scene.

Two independent things happen here, both opt-in per category via
project.yaml (narrative_boundary_field / narrative_context_window):

  1. Entries sharing a boundary value (e.g. the same context_screen,
     the same Quest ID -- whatever field a project's format actually
     carries) get tagged so batcher.py can keep them together instead
     of splitting a scene across two unrelated batches.

  2. Each entry optionally gets the last N entries *from the same
     boundary group*, in order, attached as {speaker, source} pairs --
     surrounding dialogue context for pronoun resolution, tone
     continuity, etc. Sent to the LLM via schemas.build_user_payload();
     never affects TM/dedup keys (that's still content_hash + category
     + context_key, unchanged) -- this is prompt context, not identity.
"""

from __future__ import annotations

from .config import CategoryRule, ProjectConfig
from .models import Entry


def _boundary_value(entry: Entry, field_name: str) -> str:
    if hasattr(entry, field_name):
        val = getattr(entry, field_name)
    else:
        val = entry.extra.get(field_name)
    return str(val) if val not in (None, "") else "_no_boundary_"


def attach_narrative_context(entries: list[Entry], config: ProjectConfig) -> None:
    by_category: dict[str, list[Entry]] = {}
    for e in entries:
        by_category.setdefault(e.category or "default", []).append(e)

    for category_name, category_entries in by_category.items():
        rule = next((c for c in config.categories if c.name == category_name), None)
        if rule is None or not rule.narrative_boundary_field:
            for e in category_entries:
                e.extra["_boundary_group"] = None
            continue

        groups: dict[str, list[Entry]] = {}
        for e in category_entries:
            boundary = _boundary_value(e, rule.narrative_boundary_field)
            e.extra["_boundary_group"] = boundary
            groups.setdefault(boundary, []).append(e)

        if not rule.narrative_context_window:
            continue
        window = rule.narrative_context_window
        for group_entries in groups.values():
            for i, e in enumerate(group_entries):
                preceding = group_entries[max(0, i - window) : i]
                if preceding:
                    e.preceding_context = [
                        {"speaker": p.speaker or "", "source": p.source} for p in preceding
                    ]


def group_key_for_batching(entry: Entry, rule: CategoryRule) -> str:
    """What batcher.py groups representatives by before chunking. Falls
    back to a single implicit group when a category has no boundary
    field configured, which makes "group then chunk" a strict
    generalization of the old "just chunk" behavior, not a special case.
    """
    if not rule.narrative_boundary_field:
        return "_all_"
    return entry.extra.get("_boundary_group") or "_no_boundary_"
