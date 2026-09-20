#!/usr/bin/env python3
"""validate_naninovel.py — Mechanical integrity validator for Naninovel localization files.

Checks:
  1. Balanced HTML/TMPro tags (<color>, <b>, <i>, <size>, <br>, etc.)
  2. Placeholder variables ({0}, {pop}, {days}, etc.) match between source and target
  3. Inline command tags ([accent], [style=...], [br], etc.) preserved
  4. Pipe fragment count (|) matches between source and target
  5. Actor prefix (e.g. "Aoi: ") preserved if present in source
  6. Protected glossary terms (brand / lore / mechanic) preserved
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from ..adapters.naninovel import NaninovelAdapter
from .glossary_terms import check_protected_terms, load_glossary_for_check
from .html_tags import check_html_tags

CURLY_VAR_RE = re.compile(r"\{[^{}]+\}")
BRACKET_CMD_RE = re.compile(r"\[[a-zA-Z0-9_#=,.\s/+-]+\]")
ACTOR_PREFIX_RE = re.compile(r"^([^\s.:|]+):\s*")


def validate_file(
    path: str | Path,
    glossary_entries: list | None = None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    critical: list[str] = []
    major: list[str] = []
    minor: list[str] = []
    info: list[str] = []

    file_path = Path(path)
    if not file_path.exists():
        critical.append(f"File not found: {file_path}")
        return critical, major, minor, info

    adapter = NaninovelAdapter()
    entries = adapter.extract(file_path)

    glossary = glossary_entries or []

    for entry in entries:
        loc = f"[{entry.key}]"
        source = entry.source.strip()
        target = entry.target.strip()

        if not target:
            info.append(f"{loc}: Untranslated entry")
            continue

        # 1. HTML / TMPro tag checks
        tag_issues = check_html_tags(source, target, entry.key)
        for issue in tag_issues:
            major.append(f"{loc}: {issue}")

        # 2. Curly brace placeholders ({0}, {pop}, etc.)
        src_vars = Counter(CURLY_VAR_RE.findall(source))
        tgt_vars = Counter(CURLY_VAR_RE.findall(target))
        for var, cnt in src_vars.items():
            if tgt_vars[var] < cnt:
                critical.append(
                    f"{loc}: Missing placeholder '{var}' in target (source has {cnt}, target has {tgt_vars[var]})"
                )
        for var, cnt in tgt_vars.items():
            if var not in src_vars:
                major.append(f"{loc}: Extra placeholder '{var}' in target (not in source)")

        # 3. Bracket command tags ([accent], [style=accent], etc.)
        src_cmds = Counter(c for c in BRACKET_CMD_RE.findall(source) if not c.lower().startswith(("[reward", "[jutalom")))
        tgt_cmds = Counter(c for c in BRACKET_CMD_RE.findall(target) if not c.lower().startswith(("[reward", "[jutalom")))
        for cmd, cnt in src_cmds.items():
            if tgt_cmds[cmd] < cnt:
                major.append(
                    f"{loc}: Missing command tag '{cmd}' in target (expected {cnt}, found {tgt_cmds[cmd]})"
                )
        for cmd, cnt in tgt_cmds.items():
            if cmd not in src_cmds:
                minor.append(f"{loc}: Extra command tag '{cmd}' in target")

        # 4. Pipe fragments (|) count check
        src_pipes = source.count("|")
        tgt_pipes = target.count("|")
        if src_pipes != tgt_pipes:
            critical.append(
                f"{loc}: Pipe fragment count mismatch (source has {src_pipes} '|', target has {tgt_pipes})"
            )

        # 4b. Inline expression slot ($@) check
        src_at = source.count("$@")
        tgt_at = target.count("$@")
        if src_at != tgt_at:
            critical.append(
                f"{loc}: Inline expression slot '$@' count mismatch (source has {src_at}, target has {tgt_at})"
            )

        # 5. Actor prefix check (e.g. "Aoi: ")
        m_src_actor = ACTOR_PREFIX_RE.match(source)
        if m_src_actor:
            src_actor = m_src_actor.group(1)
            # Skip common non-actor UI prefixes (e.g. "Tip:", "Example:", "Exhibitionism:")
            if src_actor.lower() not in (
                "tip", "tipp", "example", "examples", "példa", "példák", "note", "megjegyzés",
                "exhibitionism", "cuckolding", "exposure", "reward", "jutalom"
            ):
                m_tgt_actor = ACTOR_PREFIX_RE.match(target)
                if not m_tgt_actor:
                    major.append(
                        f"{loc}: Missing actor prefix '{src_actor}:' in target dialogue"
                    )
                elif m_tgt_actor.group(1) != src_actor:
                    major.append(
                        f"{loc}: Actor prefix changed from '{src_actor}:' to '{m_tgt_actor.group(1)}:'"
                    )

    # 6. Glossary checks
    if glossary:
        pairs = [(e.source, e.target, f"[{e.key}]") for e in entries if e.target]
        glossary_issues = check_protected_terms(pairs, glossary)
        for g_issue in glossary_issues:
            major.append(g_issue)

    return critical, major, minor, info
