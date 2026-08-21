"""Deterministic fake provider so the rest of the pipeline (dedup, TM,
validation, confidence scoring, merge) can be exercised end-to-end in
tests and `locpipe run --dry-run` without hitting a real API or
needing a key configured. Not meant for real translation output.

Handles both payload shapes the pipeline actually sends — this was a
real bug (not a hypothetical one) until it was caught in testing:
schemas.build_user_payload() sends a flat list for bulk translation,
reviewer.build_review_payload() sends a {"glossary", "items"} dict for
the repair step. A provider that only understood one shape would crash
--dry-run the first time anything got routed to review.
"""

from __future__ import annotations

import json

from .base import TranslationProvider


class MockProvider(TranslationProvider):
    """Echoes each source string with a marker prefix, preserving
    placeholders exactly (so downstream placeholder validation has
    something meaningful to check against either way).
    """

    persists_to_tm = False

    async def complete(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        max_tokens: int = 8192,
        effort: Optional[str] = None,
    ) -> str:
        parsed = json.loads(user_payload)

        if isinstance(parsed, list):  # bulk-translation shape: [{"id","source",...}, ...]
            out = [{"id": item["id"], "translation": f"[MOCK-HU] {item['source']}"} for item in parsed]
            return json.dumps(out, ensure_ascii=False)

        if isinstance(parsed, dict) and "items" in parsed:  # review shape
            out = [
                {
                    "key": item["key"],
                    "translation": f"[MOCK-REVIEWED] {item['source']}",
                    "flag_for_human": False,
                    "reason": "",
                }
                for item in parsed["items"]
            ]
            return json.dumps(out, ensure_ascii=False)

        raise ValueError(f"MockProvider got an unrecognized payload shape: {type(parsed).__name__}")
