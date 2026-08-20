#!/usr/bin/env python3
"""validate_ue4_5_po.py -- adds one Unreal-specific check on top of the
standard GNU gettext .po validator (validate_po_gettext.py), for .po files
exported from Unreal's Localization Dashboard (format: ue4_5_po in
project.yaml, same file structure as po_gettext -- see adapters/registry.py,
this format aliases straight to PoGettextAdapter).

Why this exists as its own layer instead of folding into
validate_po_gettext.py: standard gettext .po files (Weblate, a plain
software project, ...) never contain this syntax, and running an
Unreal-specific check against them would be pure overhead with zero
value. This format-specific validator only fires for ue4_5_po.

The gap this closes: Unreal's FText argument-formatting syntax lets a
{ArgumentName} reference be followed directly by a modifier --

    "{Number}{Number}|ordinal(one=st,two=nd,few=rd,other=th)!"
    "{Gender}|gender(He,She,They) said hello."
    "{Count}|plural(one=You have {Count} item,other=You have {Count} items)"

-- where the key=value (plural/ordinal) or positional (gender) clauses
inside the parentheses are themselves translatable prose. The existing
placeholder check in validate_po_gettext.py already tracks bare {Name}
references and would catch one going missing entirely, but it has no
notion of what follows a reference -- so a translation that keeps
"{Number}" but loses "|ordinal(...)" entirely, or drops one of the
plural/ordinal branches (e.g. "few" vanishes), passes that check clean
and would only surface as a broken string at runtime in-game. This is
the same "does the mechanical skeleton survive, regardless of what the
prose inside says" principle validate_unity_csv.py already applies to
Unity's (differently-shaped, brace-nested) SmartFormat plural syntax.

What this deliberately does NOT try to do: verify that the prose INSIDE
each clause is a faithful translation (that's what the review/fidelity
sampling in pipeline.py is for) -- only that the argument name, modifier
keyword, and set of plural/ordinal branches survived intact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import polib

_MODIFIER_HEAD_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}\|(plural|ordinal|gender)\(")

# CLDR plural categories Unreal's plural/ordinal modifier keys are drawn
# from -- not enforced (a language can legitimately use a subset), just
# used to sanity-check that a bare positional value wasn't mistaken for a
# key by the key=value splitter below.
_KNOWN_PLURAL_KEYS = {"zero", "one", "two", "few", "many", "other"}


@dataclass
class ModifierClause:
    arg_name: str
    modifier: str
    keys: list[str] = field(default_factory=list)
    unbalanced: bool = False


def _find_matching_close_paren(text: str, open_paren_idx: int) -> int | None:
    """Scan forward from an opening '(' to its matching ')', respecting
    Unreal's own quoted-string escaping (\\" for a literal quote inside a
    quoted clause value, \\\\ for a literal backslash) so a ')' or ','
    inside a quoted value isn't mistaken for structure. Returns None if
    the parens never balance before the string ends."""
    depth = 0
    in_quotes = False
    i = open_paren_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if not in_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def _split_top_level(clause: str) -> list[str]:
    """Split a modifier's inner argument list on top-level commas,
    respecting the same quoting rules as _find_matching_close_paren."""
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    i = 0
    n = len(clause)
    while i < n:
        ch = clause[i]
        if ch == "\\" and i + 1 < n:
            current.append(clause[i : i + 2])
            i += 2
            continue
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
            i += 1
            continue
        if ch == "," and not in_quotes:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return [p for p in parts if p != "" or len(parts) == 1]


def extract_modifier_clauses(text: str) -> list[ModifierClause]:
    """Find every {ArgName}|plural(...)/ordinal(...)/gender(...) construct
    in `text` and return its argument name, modifier keyword, and the
    list of plural/ordinal keys (or, for gender, one placeholder key per
    positional form -- gender's forms aren't named, only counted)."""
    clauses: list[ModifierClause] = []
    if not text:
        return clauses
    for m in _MODIFIER_HEAD_RE.finditer(text):
        arg_name, modifier = m.group(1), m.group(2)
        open_idx = m.end() - 1
        close_idx = _find_matching_close_paren(text, open_idx)
        if close_idx is None:
            clauses.append(ModifierClause(arg_name, modifier, unbalanced=True))
            continue
        inner = text[open_idx + 1 : close_idx]
        parts = _split_top_level(inner)
        if modifier in ("plural", "ordinal"):
            keys = [p.split("=", 1)[0].strip() if "=" in p else p.strip() for p in parts]
        else:  # gender: positional, unnamed forms -- just count them
            keys = [str(i) for i in range(len(parts))]
        clauses.append(ModifierClause(arg_name, modifier, keys=keys))
    return clauses


def check_entry(source: str, target: str) -> tuple[list[str], list[str]]:
    """Returns (critical_messages, major_messages) for one msgid/msgstr pair."""
    critical: list[str] = []
    major: list[str] = []
    if not source or not target:
        return critical, major

    src_clauses = extract_modifier_clauses(source)
    if not src_clauses:
        return critical, major
    tgt_clauses = extract_modifier_clauses(target)
    tgt_by_key: dict[tuple[str, str], list[ModifierClause]] = {}
    for c in tgt_clauses:
        tgt_by_key.setdefault((c.arg_name, c.modifier), []).append(c)

    for sc in src_clauses:
        if sc.unbalanced:
            # Malformed in the SOURCE file itself -- not a translation bug,
            # nothing to compare against. Skip rather than false-flag.
            continue
        head = f"{{{sc.arg_name}}}|{sc.modifier}(...)"
        candidates = tgt_by_key.get((sc.arg_name, sc.modifier))
        if not candidates:
            critical.append(
                f"Unreal argument modifier '{head}' is missing from the translation "
                "-- this breaks in-game text formatting for this string."
            )
            continue
        tc = candidates[0]
        if tc.unbalanced:
            critical.append(
                f"Unreal argument modifier '{head}' has unbalanced parentheses/quoting "
                "in the translation -- likely corrupted during translation."
            )
            continue
        if sc.modifier in ("plural", "ordinal"):
            missing = [k for k in sc.keys if k not in tc.keys]
            if missing:
                critical.append(
                    f"Plural/ordinal form(s) {missing} missing from '{head}' in the translation "
                    f"(source has: {sc.keys})."
                )
            # Extra keys beyond the source's aren't flagged: a language can
            # legitimately need a plural category ("few", "many", ...)
            # English's source text didn't require.
        else:  # gender
            if len(sc.keys) != len(tc.keys):
                major.append(
                    f"'{head}' has {len(sc.keys)} form(s) in the source but "
                    f"{len(tc.keys)} in the translation -- verify this matches what "
                    "the gender modifier expects at this call site."
                )
    return critical, major


def validate_file(path: str, glossary_entries: list) -> tuple[list[str], list[str], list[str], list[str]]:
    from . import validate_po_gettext

    critical, major, minor, info = validate_po_gettext.validate_file(path, glossary_entries)

    po = polib.pofile(path)
    for entry in po:
        if entry.obsolete:
            continue
        targets = entry.msgstr_plural.values() if entry.msgid_plural else [entry.msgstr]
        source = entry.msgid_plural if entry.msgid_plural else entry.msgid
        for target in targets:
            c, m = check_entry(source, target)
            critical.extend(c)
            major.extend(m)

    return critical, major, minor, info
