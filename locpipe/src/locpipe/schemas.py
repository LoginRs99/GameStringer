"""Phase 9. The LLM only ever sees `source` (never file/namespace/key)
and only ever returns {id, translation} pairs (never free text) — the
two constraints that make Phase 8's big batches possible at all.

The system prompt is built PER CATEGORY, not per batch, and is
identical for every batch that shares a category — that's what makes
it a stable prefix a caching-aware provider can reuse instead of
re-paying for it on every one of a project's batches (see
providers/gemini_provider.py).
It also uses the FULL glossary and character-voices file by default,
rather than per-batch pruning, when speakers=None -- pruning made
sense when every batch paid full price for those tokens; once a cache
picks up that cost after the first call in a category, sending the
whole thing once and reusing it is strictly cheaper for any project
with more than a couple of batches per category, which is every real
project. pipeline.py passes an actual (possibly per-batch) glossary
and speakers set instead for providers with no caching continuity
between calls -- see TranslationProvider.prefers_per_batch_context.

Assembled from a project's actual resource files at call time — this
module has no MindsEye-specific text in it, only assembly logic.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import jsonschema

from .batcher import TranslationBatch
from .character_voices import load_character_voice_rows, prune_character_voices_for_batch
from .config import ProjectConfig
from .glossary import GlossaryTerm, format_for_prompt
from .models import Entry
from .prompt_builder import fill, load_template, toggle_section, get_register_instruction

RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "translation": {"type": "string"},
        },
        "required": ["id", "translation"],
        "additionalProperties": False,
    },
}


@lru_cache(maxsize=None)
def _read(path: Optional[Path]) -> str:
    """Cached: lang-style.md / anti-fabrication-checklist.md are static
    project resources for the lifetime of a run -- re-reading them off
    disk on every single batch (this used to happen once per batch call,
    not once per category) was pure waste on a project with hundreds or
    thousands of batches.
    """
    if path is None or not path.exists():
        return "(none provided)"
    text = path.read_text(encoding="utf-8").strip()
    return text if text else "(none provided)"


def build_system_prompt_for_category(
    config: ProjectConfig,
    category_name: str,
    glossary: list[GlossaryTerm],
    speakers: Optional[set[str]] = None,
) -> str:
    """speakers=None (the default) means "use the full character-voices
    file, unpruned" -- correct for a cache-capable provider, where the
    category-level system prompt is a stable string reused across every
    batch in that category and a cache picks up the repeat cost, same
    reasoning as the full glossary above. Pass an actual set (even an
    empty one) to prune the voice bible down to just those characters --
    what pipeline.py does for providers with no caching continuity
    between calls (see TranslationProvider.prefers_per_batch_context),
    where sending the whole cast's bible on every one-shot call would be
    paying full price for characters that aren't even in this batch.
    """
    rule = next((c for c in config.categories if c.name == category_name), None)
    needs_voice = bool(rule and rule.needs_character_voice)

    template = load_template("translate.md")
    template = toggle_section(
        template, "%%CHARACTER_VOICE_SECTION_START%%", "%%CHARACTER_VOICE_SECTION_END%%", keep=needs_voice
    )

    character_voices = ""
    if needs_voice:
        cv_path = config.resources.get("character_voices")
        if speakers is not None:
            preamble, rows = load_character_voice_rows(cv_path)
            character_voices = prune_character_voices_for_batch(preamble, rows, speakers)
        else:
            character_voices = _read(cv_path)

    return fill(
        template,
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        register_instruction=get_register_instruction(getattr(config, "target_register", "informal")),
        category=category_name,
        glossary=format_for_prompt(glossary),
        style_guide=_read(config.resources.get("lang_style")),
        anti_fabrication=_read(config.resources.get("anti_fabrication_checklist")),
        character_voices=character_voices,
    )


def build_user_payload(batch: TranslationBatch) -> str:
    items = []
    for i, e in enumerate(batch.representatives):
        item = {"id": i, "source": e.source}
        if e.speaker:
            item["speaker"] = e.speaker
        if e.max_length:
            item["max_length"] = e.max_length
        if e.notes:
            item["notes"] = e.notes
        if e.preceding_context:
            item["preceding_context"] = e.preceding_context
        items.append(item)
    return json.dumps(items, ensure_ascii=False)


def build_retry_payload(entries: list[Entry], issues_by_key: dict[str, list[str]]) -> str:
    """Same shape as build_user_payload, plus previous_attempt/issue on
    each item -- see translate.md's CORRECTION MODE section. Used for
    Tier-1 deterministic-validation retries only (pipeline.py's
    _tier1_repair): a mechanical, no-judgment-required correction
    request that reuses the cheap bulk-translate call instead of routing
    straight to the expensive review agent for something a validator
    already pinned down exactly.
    """
    items = []
    for i, e in enumerate(entries):
        item = {"id": i, "source": e.source, "previous_attempt": e.target}
        if e.speaker:
            item["speaker"] = e.speaker
        if e.max_length:
            item["max_length"] = e.max_length
        issues = issues_by_key.get(e.key)
        if issues:
            item["issue"] = "; ".join(issues)
        items.append(item)
    return json.dumps(items, ensure_ascii=False)


def parse_and_validate_response(raw_text: str) -> tuple[Optional[list[dict]], Optional[str]]:
    """Returns (parsed, error). error is None on success."""
    import re
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        text_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
        try:
            data = json.loads(text_clean, strict=False)
        except json.JSONDecodeError:
            # Fallback 1: repair unescaped trailing backslashes before closing quotes, e.g. "foo\" -> "foo\\"
            text_bs = re.sub(r'\\(?="[,\s\}\]])', r'\\\\', text_clean)
            try:
                data = json.loads(text_bs, strict=False)
            except json.JSONDecodeError:
                t_strip = text_bs.rstrip()
                if not t_strip.endswith("]"):
                    if t_strip.endswith("}"):
                        t_strip += "]"
                    elif t_strip.endswith('"'):
                        t_strip += "}]"
                    else:
                        t_strip += '"}]'
                try:
                    data = json.loads(t_strip, strict=False)
                except json.JSONDecodeError as e:
                    return None, f"invalid JSON: {e}"
    try:
        jsonschema.validate(data, RESPONSE_SCHEMA)
    except jsonschema.ValidationError as e:
        return None, f"schema mismatch: {e.message}"
    ids = [item["id"] for item in data]
    if len(ids) != len(set(ids)):
        return None, "duplicate ids in response"
    return data, None
