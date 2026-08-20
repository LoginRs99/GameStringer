"""Phase 11. Turns a ValidationResult + a few cheap heuristics into a
0-1 score. Everything below config.review_threshold goes to Phase 12's
review queue; everything above merges straight through. This is the
lever that keeps LLM review down to the ~5% that actually need it
instead of the 100% the old per-batch QA agent re-read every time.
"""

from __future__ import annotations

from typing import Optional

from .models import Entry, ValidationResult


def _expansion_ratio_limit(entry: Entry, config) -> float:
    """Project-wide confidence.max_expansion_ratio, overridden per-category
    if that category set its own (see config.CategoryRule.max_expansion_ratio).
    Falls back to 1.6 if no config was passed at all (keeps this callable
    standalone, e.g. from a REPL or a future unit test, without requiring
    a full ProjectConfig just to call score()).
    """
    if config is None:
        return 1.6
    if entry.category:
        for rule in config.categories:
            if rule.name == entry.category and rule.max_expansion_ratio is not None:
                return rule.max_expansion_ratio
    return config.max_expansion_ratio


def score(entry: Entry, validation: ValidationResult, config: Optional[object] = None) -> float:
    if validation.critical:
        return 0.0

    s = 1.0
    s -= 0.25 * len(validation.major)
    s -= 0.05 * len(validation.minor)

    if entry.extra.get("_speaker_uncertain"):
        s -= 0.3  # category needed a character voice and none could be found

    if entry.extra.get("_disputed_glossary_term_used"):
        s -= 0.2  # e.g. "Network" — Hálózat/Tévéadó — needs a human or reviewer call

    if (
        entry.target.strip()
        and entry.target.strip() == entry.source.strip()
        and not entry.extra.get("_expected_identity")
    ):
        s -= 0.4  # came back unchanged and nothing in the glossary says it should have

    if entry.max_length and len(entry.target) > entry.max_length:
        s -= 0.3  # a real, known hard limit was exceeded -- always penalize this

    src_len, tgt_len = len(entry.source.strip()), len(entry.target.strip())
    # Ratio math is noisy on short strings regardless of category: a single
    # extra syllable on a 2-7 char word ("OK" -> "Rendben") produces a huge
    # ratio despite being a completely normal translation, while the same
    # absolute overhead barely moves the ratio on a full sentence. Below this
    # length, only max_length (an absolute, known limit) is a meaningful
    # guard -- the ratio ceiling below is skipped entirely rather than
    # flagging routine short-word expansion as if it were bloat.
    _MIN_SOURCE_LEN_FOR_RATIO_CHECK = 10
    if src_len >= _MIN_SOURCE_LEN_FOR_RATIO_CHECK:
        ratio = tgt_len / src_len
        limit = _expansion_ratio_limit(entry, config)
        # Hungarian tends to run a bit longer than English, but not by huge
        # margins, and it should never come back empty or wildly padded.
        # The floor (0.3) stays fixed -- "much shorter than source" is a
        # fabrication/omission smell regardless of category; the ceiling is
        # the configurable, category-aware guard against UI-breaking bloat.
        if ratio < 0.3 or ratio > limit:
            s -= 0.3

    return max(0.0, min(1.0, s))


def needs_review(entry: Entry, validation: ValidationResult, threshold: float, config: Optional[object] = None) -> bool:
    return not validation.passed or score(entry, validation, config) < threshold


def confidence_flags(entry: Entry, config: Optional[object] = None) -> list[str]:
    """Human-readable reasons for every *heuristic* (non-validator) deduction
    score() applied -- speaker uncertainty, disputed glossary term, identity
    passthrough, max_length overrun, expansion-ratio overrun.

    These heuristics never produced a ValidationIssue, so before this an
    entry could land in the review queue with confidence 0.7 and an empty
    `issues` list -- correct behavior, but silent: the reviewer-LLM (or a
    human skimming review_queue.json) had no way to tell *why* without
    re-deriving it by eye. review_queue.py's ReviewItem.to_dict() surfaces
    this list alongside the validator issues so the reason is always
    explicit, whichever stage produced it.
    """
    flags: list[str] = []

    if entry.extra.get("_tier1_retry_exhausted"):
        flags.append(
            "Tier 1 (deterministic-validation retry) already tried once and failed to fix this "
            "mechanically -- see the issues list for what's still wrong. A second identical "
            "attempt is unlikely to help; consider whether the fix needs a different approach "
            "than what was already tried, not just another try at the same one."
        )

    if entry.extra.get("_speaker_uncertain"):
        flags.append("speaker/character voice could not be determined for this category")

    if entry.extra.get("_disputed_glossary_term_used"):
        flags.append("uses a context-dependent (⚠) glossary term — verify the sense applied is correct")

    if (
        entry.target.strip()
        and entry.target.strip() == entry.source.strip()
        and not entry.extra.get("_expected_identity")
    ):
        flags.append("translation is identical to source and nothing marks that as expected")

    if entry.max_length and len(entry.target) > entry.max_length:
        flags.append(f"exceeds max_length: {len(entry.target)} chars > limit {entry.max_length}")

    src_len, tgt_len = len(entry.source.strip()), len(entry.target.strip())
    if src_len >= 10:
        ratio = tgt_len / src_len
        limit = _expansion_ratio_limit(entry, config)
        if ratio > limit:
            flags.append(
                f"translation is {ratio:.1f}x the source length (limit {limit:.1f}x for "
                f"category '{entry.category or 'default'}') -- rephrase more concisely"
            )
        elif ratio < 0.3:
            flags.append(f"translation is only {ratio:.1f}x the source length -- looks truncated or incomplete")

    return flags
