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
    # 3. HTML & Unity rich-text tags (<color=#FF0000>, </color>, <b>, </i>, <size=12>)
    re.compile(r"</?[a-zA-Z0-9_\-=\#\.\s\":/]+>"),
    # 4. Printf format specifiers (%s, %d, %f, %.2f, %1$s, %2$d)
    re.compile(r"%(?:\d+\$)?[0-9\.\-\+]*[sdfuxXgGcping]"),
    # 5. Game tag bracket identifiers and commands ([ITEM_ID], [KEY_NAME], [style=accent], [accent])
    re.compile(r"\[[A-Za-z0-9_\-\:\.=#]+\]"),
    # 6. RPG Maker / Visual Novel / game engine escape sequences (\C[1], \V[2], \I[3], \G, \!, \., \|, \>, \<, \{, \})
    re.compile(r"\\[A-Za-z]+\[\d+\]|\\[Gg]|\\[\.\!\^\|\>\<\{\}\$]"),
    # 7. Escaped string characters (\n, \r, \t)
    re.compile(r"\\n|\\r|\\t"),
    # 8. Ruby / Furigana markup (<ruby>, </ruby>, <rt>, </rt>, [ruby], [/ruby])
    re.compile(r"</?ruby(?:=[^>]+)?>|</?rt>|</?rp>|\[/?ruby(?:=[^\]]+)?\]|\[/?rt\]"),
    # 9. Keyboard shortcuts (Ctrl+S, Alt+F4, Ctrl+Shift+P)
    re.compile(r"\b(?:Ctrl|Alt|Shift|Cmd|Meta)\+[A-Za-z0-9\+]+"),
    # 10. Naninovel inline expression slot ($@)
    re.compile(r"\$@"),
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
        # Gender slot markers ({ms|...}, {fs|...}, {mp|...}, {fp|...}, {n|...})
        m_gender = re.match(r"^\{(ms|fs|mp|fp|n)\|", src_tok)
        if m_gender:
            slot_prefix = f"{{{m_gender.group(1)}|"
            if slot_prefix not in target:
                missing.append(src_tok)
            continue

        if src_tok not in target_token_set:
            # Check if token was partially modified/translated (e.g. @primary attack@ -> @támadás@)
            if src_tok.startswith("@") and src_tok.endswith("@"):
                if re.search(r"@[^@\n]+@", target):
                    modified.append(src_tok)
                else:
                    missing.append(src_tok)
            elif src_tok.startswith("{") and src_tok.endswith("}"):
                inner = src_tok[1:-1]
                if re.search(r"\{[^{}\n]+\}", target) and not re.search(r"\{" + re.escape(inner) + r"\}", target):
                    modified.append(src_tok)
                else:
                    missing.append(src_tok)
            elif src_tok.startswith("\\"):
                if re.search(re.escape(src_tok[0:2]), target):
                    modified.append(src_tok)
                else:
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
    for tok in src_tokens:
        if tok in missing or tok in modified:
            continue
        # Skip count check for gender markers where internal content varies
        if re.match(r"^\{(ms|fs|mp|fp|n)\|", tok):
            continue
        # Skip ruby markup tags if translating between different scripts/languages where ruby isn't duplicated
        if tok.startswith(("<ruby", "</ruby", "<rt", "</rt", "[ruby", "[/ruby")):
            continue
        c_src = source.count(tok)
        c_tgt = target.count(tok)
        if c_src != c_tgt:
            issues.append(
                ValidationIssue(
                    severity=Severity.MAJOR,
                    code="PROTECTED_TOKEN_COUNT_MISMATCH",
                    message=f"Protected token '{tok}' count mismatch: source has {c_src}, target has {c_tgt}.",
                )
            )

    # Accelerator / access key check: &File, &Open, Save &As
    has_src_acc = bool(re.search(r"(?<!&)&[A-Za-z0-9](?!&)", source))
    has_tgt_acc = bool(re.search(r"(?<!&)&[A-Za-z0-9áéíóöőúüűÁÉÍÓÖŐÚÜŰ](?!&)", target))
    if has_src_acc and not has_tgt_acc:
        issues.append(
            ValidationIssue(
                severity=Severity.MAJOR,
                code="ACCESS_KEY_MISSING",
                message="Source contains an access key accelerator ('&'), but none was found in translation.",
            )
        )

    return issues
