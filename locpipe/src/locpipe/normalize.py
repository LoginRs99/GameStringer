"""Normalize source strings before anything else touches them.

Order matters: normalize -> hash. The hash is what makes incremental
runs possible (Phase 5) — a source string that hashes the same as last
run is skipped entirely, regardless of which project or language pair
it belongs to.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_PLACEHOLDER_PATTERNS = [
    re.compile(r"\{[^{}]*\}"),      # {0}, {playerName}
    re.compile(r"%[sd@]"),          # %s, %d, %@
    re.compile(r"<[^<>]+>"),        # <color=red>, </color>
]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def normalize_escapes(text: str) -> str:
    # Collapse the two common ways of writing a literal newline/tab in
    # exported KV/CSV formats so identical strings hash identically.
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    return text


def normalize_source(text: str) -> str:
    text = normalize_unicode(text)
    text = normalize_escapes(text)
    text = normalize_whitespace(text)
    return text


def content_hash(normalized_source: str) -> str:
    return hashlib.sha256(normalized_source.encode("utf-8")).hexdigest()[:16]


def extract_placeholders(text: str) -> list[str]:
    """Best-effort placeholder inventory, used by classify.py and confidence.py
    for quick signal — the authoritative check is still each format's
    validator in locpipe/validators/, which understands ICU plural blocks,
    tags, etc. properly. This is a cheap heuristic, not a validator.
    """
    found: list[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        found.extend(pattern.findall(text))
    return found
