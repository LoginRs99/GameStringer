"""Phase 16 / Advisory Consistency Checker.
Zero-cost, stdlib difflib-based scan for near-duplicate source strings with differing translations.
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable

from .models import TMRecord
from .normalize import normalize_source


def _simple_norm(text: str) -> str:
    """Lowercase and whitespace-collapsed text for similarity comparison."""
    return re.sub(r"\s+", " ", text.lower().strip())


def find_consistency_issues(
    tm_records: Iterable[tuple[str, TMRecord] | TMRecord],
    threshold: float = 0.85,
    min_length: int = 6,
) -> list[dict]:
    """Find source strings in TM that are highly similar (>= threshold) but have different translations.

    Uses stdlib difflib.SequenceMatcher.
    Buckets candidates by approximate length to avoid O(N^2) explosion on large projects.
    Guards against noisy short strings via min_length.

    Returns:
        List of dicts: [
            {
                'source_a': str,
                'source_b': str,
                'target_a': str,
                'target_b': str,
                'similarity': float,
                'category_a': str,
                'category_b': str,
            },
            ...
        ]
    """
    # 1. Collect unique source strings from TM records
    unique_entries: dict[str, TMRecord] = {}
    for item in tm_records:
        rec = item[1] if isinstance(item, tuple) else item
        src_norm = _simple_norm(rec.source)
        if len(src_norm) < min_length or not rec.translation.strip():
            continue
        if src_norm not in unique_entries:
            unique_entries[src_norm] = rec

    items = list(unique_entries.items())  # list of (norm_src, TMRecord)
    if len(items) < 2:
        return []

    # Sort items by normalized length for windowed comparison
    items.sort(key=lambda x: len(x[0]))

    issues: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Compare items within length tolerance:
    # If len(A) and len(B) differ by more than (1 - threshold) * max(len(A), len(B)),
    # their difflib similarity cannot reach threshold.
    n = len(items)
    for i in range(n):
        src_a_norm, rec_a = items[i]
        len_a = len(src_a_norm)
        max_len_b = len_a / threshold if threshold > 0 else len_a * 2

        for j in range(i + 1, n):
            src_b_norm, rec_b = items[j]
            len_b = len(src_b_norm)
            if len_b > max_len_b:
                break

            # Check if targets are identical (if identical, no inconsistency)
            tgt_a_norm = _simple_norm(rec_a.translation)
            tgt_b_norm = _simple_norm(rec_b.translation)
            if tgt_a_norm == tgt_b_norm:
                continue

            pair_key = (min(src_a_norm, src_b_norm), max(src_a_norm, src_b_norm))
            if pair_key in seen_pairs:
                continue

            # Quick quick-ratio filter before full ratio
            matcher = difflib.SequenceMatcher(None, src_a_norm, src_b_norm)
            if matcher.quick_ratio() < threshold:
                continue

            ratio = matcher.ratio()
            if ratio >= threshold:
                seen_pairs.add(pair_key)
                issues.append({
                    'source_a': rec_a.source,
                    'source_b': rec_b.source,
                    'target_a': rec_a.translation,
                    'target_b': rec_b.translation,
                    'similarity': round(ratio, 3),
                    'category_a': rec_a.category or '',
                    'category_b': rec_b.category or '',
                })

    # Sort descending by similarity
    issues.sort(key=lambda x: (x['similarity'], len(x['source_a'])), reverse=True)
    return issues
