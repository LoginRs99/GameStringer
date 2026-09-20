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
    # 1. Group records by normalized source string to detect exact-source conflicts
    entries_by_src: dict[str, list[TMRecord]] = {}
    for item in tm_records:
        rec = item[1] if isinstance(item, tuple) else item
        src_norm = _simple_norm(rec.source)
        if len(src_norm) < min_length or not rec.translation.strip():
            continue
        entries_by_src.setdefault(src_norm, []).append(rec)

    issues: list[dict] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()

    # Step 1: Detect identical source strings that have conflicting translations
    unique_items: list[tuple[str, TMRecord]] = []
    for src_norm, recs in entries_by_src.items():
        unique_items.append((src_norm, recs[0]))
        if len(recs) > 1:
            first_tgt = _simple_norm(recs[0].translation)
            for r in recs[1:]:
                if _simple_norm(r.translation) != first_tgt:
                    pair_key = (min(recs[0].source, r.source), max(recs[0].source, r.source),
                                min(recs[0].translation, r.translation), max(recs[0].translation, r.translation))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        issues.append({
                            'source_a': recs[0].source,
                            'source_b': r.source,
                            'target_a': recs[0].translation,
                            'target_b': r.translation,
                            'similarity': 1.0,
                            'category_a': recs[0].category or '',
                            'category_b': r.category or '',
                        })

    if len(unique_items) < 2:
        return issues

    # Step 2: Sort items by normalized length for windowed fuzzy comparison
    unique_items.sort(key=lambda x: len(x[0]))
    n = len(unique_items)
    fuzzy_seen: set[tuple[str, str]] = set()

    # Compare items within length tolerance and bounded search window to prevent CPU stall
    for i in range(n):
        src_a_norm, rec_a = unique_items[i]
        len_a = len(src_a_norm)
        max_len_b = len_a / threshold if threshold > 0 else len_a * 2
        max_j = min(n, i + 80)

        for j in range(i + 1, max_j):
            src_b_norm, rec_b = unique_items[j]
            len_b = len(src_b_norm)
            if len_b > max_len_b:
                break

            tgt_a_norm = _simple_norm(rec_a.translation)
            tgt_b_norm = _simple_norm(rec_b.translation)
            if tgt_a_norm == tgt_b_norm:
                continue

            pair_key = (min(src_a_norm, src_b_norm), max(src_a_norm, src_b_norm))
            if pair_key in fuzzy_seen:
                continue

            matcher = difflib.SequenceMatcher(None, src_a_norm, src_b_norm)
            if matcher.quick_ratio() < threshold:
                continue

            ratio = matcher.ratio()
            if ratio >= threshold:
                fuzzy_seen.add(pair_key)
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
