"""Phase 13. This is deliberately the slow, expensive, careful path —
that's fine, because confidence.py's whole job was making sure only a
small minority of entries ever reach it. The priority order below
(structural integrity first, style last) mirrors how MindsEye's
original loc-qa-reviewer skill already ranked issues; this step is
its natural home in the new pipeline, just invoked on ~5% of entries
instead of 100%.
"""

from __future__ import annotations

import asyncio
import json

from .glossary import GlossaryTerm, format_for_prompt
from .prompt_builder import fill, load_template
from .providers.base import TranslationProvider
from .review_queue import ReviewItem


def build_review_payload(items: list[ReviewItem], glossary: list[GlossaryTerm]) -> str:
    payload = []
    for item in items:
        payload.append(
            {
                "key": item.entry.key,
                "source": item.entry.source,
                "current_translation": item.entry.target,
                "speaker": item.entry.speaker,
                "category": item.entry.category,
                "issues": [i.message for i in item.validation.all_issues],
            }
        )
    return json.dumps(
        {"glossary": format_for_prompt(glossary), "items": payload}, ensure_ascii=False
    )


async def review_batch(
    items: list[ReviewItem],
    glossary: list[GlossaryTerm],
    provider: TranslationProvider,
    source_lang: str,
    target_lang: str,
    chunk_size: int = 20,
    max_output_tokens: int = 16384,
) -> list[dict]:
    if not items:
        return []
    system_prompt = fill(load_template("review.md"), source_lang=source_lang, target_lang=target_lang)

    async def _review_chunk(chunk: list[ReviewItem]) -> list[dict]:
        user_payload = build_review_payload(chunk, glossary)
        try:
            raw = await provider.complete(system_prompt, user_payload, max_tokens=max_output_tokens)
            text = raw.strip().strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
            start_idx = text.find("[")
            end_idx = text.rfind("]")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx : end_idx + 1]
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    # Concurrent, not sequential: each chunk is an independent network call,
    # and the provider already owns its own concurrency limit (see e.g.
    # AntigravityCLIProvider's internal asyncio.Semaphore) -- awaiting chunks
    # one at a time here just added idle wall-clock time on top of that for
    # no benefit, since nothing about chunk N's review depends on chunk N-1.
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
    results = await asyncio.gather(*(_review_chunk(c) for c in chunks))
    all_repairs: list[dict] = []
    for r in results:
        all_repairs.extend(r)
    return all_repairs
