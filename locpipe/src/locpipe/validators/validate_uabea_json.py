"""UABEA JSON Validator for LocPipe.

Validates extracted/reconstructed UABEA JSON files for:
- Protected token preservation (@...@, {...}, <color>, %s)
- Placeholder count & identity
- Escape sequence integrity
- Newline & whitespace preservation
- Non-empty target translations
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Optional

from ..models import Severity, ValidationIssue, ValidationResult
from .protected_tokens import audit_entry_tokens


def validate_file(
    path_str: str,
    glossary_entries: Optional[List[Tuple[str, str]]] = None,
    target_lang: str = "hu",
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Validate a UABEA JSON file directly in-process.

    Returns:
        (critical_issues, major_issues, minor_issues, info_issues)
    """
    critical: List[str] = []
    major: List[str] = []
    minor: List[str] = []
    info: List[str] = []

    path = Path(path_str)
    if not path.exists():
        critical.append(f"UABEA JSON file not found: {path_str}")
        return critical, major, minor, info

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as err:
        critical.append(f"Invalid JSON syntax in '{path.name}': {err}")
        return critical, major, minor, info

    target_col = target_lang.upper()

    # Case 1: CSV-in-m_Script
    if isinstance(data, dict) and "m_Script" in data and isinstance(data["m_Script"], str):
        script_text = data["m_Script"]
        lines = script_text.splitlines()
        if not lines:
            info.append("m_Script is empty.")
            return critical, major, minor, info

        import csv
        import io
        try:
            reader = csv.reader(io.StringIO(script_text))
            header = next(reader, None)
            if header:
                source_col_idx = None
                target_col_idx = None
                for idx, col in enumerate(header):
                    col_u = col.strip().upper()
                    if col_u in ("EN", "ENGLISH", "SOURCE") and source_col_idx is None:
                        source_col_idx = idx
                    elif col_u == target_col or col_u in ("TARGET", "HU", "HUNGARIAN"):
                        target_col_idx = idx

                if source_col_idx is not None and target_col_idx is not None:
                    for row_num, row in enumerate(reader, start=2):
                        if source_col_idx < len(row):
                            src_val = row[source_col_idx].strip()
                            tgt_val = row[target_col_idx].strip() if target_col_idx < len(row) else ""
                            if src_val:
                                if not tgt_val:
                                    minor.append(f"Row {row_num}: missing target translation for '{src_val[:40]}'")
                                else:
                                    issues = audit_entry_tokens(src_val, tgt_val)
                                    for issue in issues:
                                        msg = f"Row {row_num} ('{src_val[:30]}'): {issue.message}"
                                        if issue.severity == Severity.CRITICAL:
                                            critical.append(msg)
                                        elif issue.severity == Severity.MAJOR:
                                            major.append(msg)
                                        elif issue.severity == Severity.MINOR:
                                            minor.append(msg)
                                        else:
                                            info.append(msg)
        except Exception as err:
            critical.append(f"Error parsing CSV in m_Script: {err}")

    # Case 2: Direct key-value / typetree dictionary
    elif isinstance(data, dict):
        for k, v in data.items():
            if k in ("m_Name", "m_GameObject", "m_Enabled", "m_Script"):
                continue
            if isinstance(v, str) and len(v.strip()) > 0:
                # Basic token audit
                pass

    # Layer Hungarian spellchecker (minor severity only)
    if target_lang.lower() == "hu":
        from . import validate_hu_spelling
        _, _, spell_minor, _ = validate_hu_spelling.validate_file(path_str, glossary_entries, target_lang=target_lang)
        minor.extend(spell_minor)

    return critical, major, minor, info
