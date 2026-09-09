"""Protected Token Detection & Validation Module for LocPipe.

Identifies and validates game-specific protected tokens, placeholders,
markup tags, and formatting sequences that must survive translation
unchanged (e.g. @primary attack@, {comma}, {0}, <color=#FF0000>, %s, etc.).

Extraction is strictly READ-ONLY: source text is never destructively modified.
"""

from __future__ import annotations

import re
from typing import List, Tuple
from ..models import Severity, ValidationIssue, ValidationResult

# Protected token patterns
PROTECTED_PATTERNS = [
    # 1. Game marker tags (@primary attack@, @damage@, @maximum health@)
    re.compile(r"@[^@\n]+@"),
    # 2. Placeholders and variables ({comma}, {0}, {player}, {0:N0}, {fs|ella})
    re.compile(r"\{[^{}\n]+\}"),
    # 3. HTML & Unity rich-text tags (<color=#FF0000>, </color>, <b>, </i>)
    re.compile(r"</?[a-zA-Z0-9_\-=\#\.\s\"]+>"),
    # 4. Printf format specifiers (%s, %d, %f, %.2f, %1$s, %2$d)
    re.compile(r"%(?:\d+\$)?[0-9\.\-\+]*[sdfuxXgGcping]"),
    # 5. Game tag bracket identifiers ([ITEM_ID], [KEY_NAME])
    re.compile(r"\[[A-Z0-9_\-\:\.]+\]"),
]


def extract_protected_tokens(text: str) -> List[str]:
    """Extract all protected game tokens from a string. Read-only, no side effects."""
    if not text:
        return []

    tokens: List[str] = []
    seen = set()

    for pattern in PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            tok = match.group(0)
            if tok not in seen:
                seen.add(tok)
                tokens.append(tok)

    return tokens


def validate_protected_tokens(source: str, target: str) -> Tuple[List[str], List[str]]:
    """Validate that all protected tokens present in source are preserved in target.

    Returns:
        (missing_tokens, modified_tokens)
    """
    if not source:
        return [], []

    source_tokens = extract_protected_tokens(source)
    if not source_tokens:
        return [], []

    target_tokens = extract_protected_tokens(target)
    target_token_set = set(target_tokens)

    missing: List[str] = []
    modified: List[str] = []

    for src_tok in source_tokens:
        if src_tok not in target_token_set:
            # Check if token was partially modified/translated (e.g. @primary attack@ -> @támadás@)
            if src_tok.startswith("@") and src_tok.endswith("@"):
                # Check for partial @ match in target
                if re.search(r"@[^@\n]+@", target):
                    modified.append(src_tok)
                else:
                    missing.append(src_tok)
            elif src_tok.startswith("{") and src_tok.endswith("}"):
                missing.append(src_tok)
            else:
                missing.append(src_tok)

    return missing, modified


def audit_entry_tokens(source: str, target: str) -> List[ValidationIssue]:
    """Perform a deterministic token audit on a source/target pair.

    Returns a list of ValidationIssue objects.
    """
    issues: List[ValidationIssue] = []
    if not source or not target:
        return issues

    missing, modified = validate_protected_tokens(source, target)

    for tok in missing:
        issues.append(
            ValidationIssue(
                severity=Severity.CRITICAL,
                code="PROTECTED_TOKEN_MISSING",
                message=f"Protected game token '{tok}' missing from translation.",
            )
        )

    for tok in modified:
        issues.append(
            ValidationIssue(
                severity=Severity.CRITICAL,
                code="PROTECTED_TOKEN_MODIFIED",
                message=f"Protected game token '{tok}' was improperly modified/translated.",
            )
        )

    # Count check for exact matches
    src_tokens = extract_protected_tokens(source)
    tgt_tokens = extract_protected_tokens(target)
    if len(src_tokens) != len(tgt_tokens) and not missing and not modified:
        issues.append(
            ValidationIssue(
                severity=Severity.MAJOR,
                code="PROTECTED_TOKEN_COUNT_MISMATCH",
                message=f"Protected token count mismatch: source has {len(src_tokens)}, target has {len(tgt_tokens)}.",
            )
        )

    return issues
