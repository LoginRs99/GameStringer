"""Bootstrap resource files (glossary, lang-style, character-voices) from TM and batch files.

All outputs are strictly written to *.draft.md sibling files — never overwriting real resource files.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from .adapters.registry import get_adapter
from .config import ProjectConfig
from .models import Entry, TMRecord
from .providers.base import TranslationProvider
from .tm import TranslationMemory

ANTI_FABRICATION_DEFAULT = (
    "# Anti-fabrication checklist\n"
    "Never invent numbers, names, or quantities not present in the source.\n"
    "Never drop content present in the source without a clear formatting reason.\n\n"
    "This is about content, not sentence shape: restructuring word order, splitting or joining clauses, "
    "or moving a preverb for natural Hungarian focus (see lang-style.md) is not fabrication or dropped content "
    "as long as the same information survives. Judge by meaning preserved, not by how closely the sentence "
    "structure mirrors the source.\n"
)


def update_existing_anti_fabrication_checklist(config: ProjectConfig) -> bool:
    """Update existing anti-fabrication-checklist.md if it matches the empty bare header."""
    res_path = config.resources.get("anti_fabrication_checklist") or (config.root / "resources" / "anti-fabrication-checklist.md")
    if res_path and res_path.exists():
        content = res_path.read_text(encoding="utf-8").strip()
        if content in ("# Anti-fabrication checklist", "# Anti-fabrication checklist\n"):
            res_path.write_text(ANTI_FABRICATION_DEFAULT, encoding="utf-8")
            return True
    return False


def filter_glossary_candidates(
    records: Iterable[tuple[str, TMRecord] | TMRecord]
) -> tuple[list[dict[str, str]], int]:
    """Pre-filter candidates from TM to measurably shrink LLM input.
    
    Filters out full narrative sentences and extracts high-value terminology:
    proper nouns, keyword tags, combat actions, mechanics, and recurring UI terms.
    """
    candidates: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    total_records = 0

    tag_pattern = re.compile(r"<[^>]+>|@[^@]+@|\{[^}]+\}|\[[^\]]+\]")

    for item in records:
        rec = item[1] if isinstance(item, tuple) else item
        total_records += 1
        src = rec.source.strip()
        tgt = rec.translation.strip()
        if not src or not tgt or src in seen_sources:
            continue

        src_clean = tag_pattern.sub("", src).strip()
        word_count = len(src_clean.split())

        # Include if:
        # 1. Contains rich tags (keywords, sprites, tokens)
        has_tags = bool(tag_pattern.search(src))
        # 2. Short phrase/term (1 to 4 words, <= 45 chars)
        is_short_term = 1 <= word_count <= 4 and len(src) <= 45
        # 3. Capitalized entity / proper noun / title
        is_capitalized = bool(src_clean and src_clean[0].isupper() and word_count <= 5 and len(src) <= 50)
        # 4. UI category
        is_ui = (rec.category == "ui") and word_count <= 4

        if has_tags or is_short_term or is_capitalized or is_ui:
            # Exclude obvious sentence punctuation unless tagged
            if not has_tags and src.endswith((".", "!", "?")) and word_count > 3:
                continue
            seen_sources.add(src)
            candidates.append({
                "source": src,
                "translation": tgt,
                "category": rec.category or "ui",
            })

    return candidates, total_records


def _load_agent_template(template_name: str) -> str:
    template_path = Path(__file__).parent / "agents" / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Agent template '{template_name}' not found at {template_path}")
    return template_path.read_text(encoding="utf-8")


async def bootstrap_glossary(
    config: ProjectConfig,
    provider: TranslationProvider,
    candidates: Optional[list[dict[str, str]]] = None,
) -> Optional[Path]:
    """Draft a canonical glossary.draft.md from TM candidates using LLM (effort=high)."""
    tm = TranslationMemory(config.tm_db_path)
    try:
        if candidates is None:
            candidates, _ = filter_glossary_candidates(tm.iter_all())
    finally:
        tm.close()

    if not candidates:
        return None

    system_prompt = _load_agent_template("glossary-bootstrap.md")
    batch_candidates = candidates[:350]
    user_payload = json.dumps(batch_candidates, ensure_ascii=False, indent=2)

    raw_response = await provider.complete(system_prompt, user_payload, effort="high")

    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text.startswith("# Glossary"):
        text = "# Glossary\n\n" + text

    out_path = config.root / "resources" / "glossary.draft.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return out_path


async def bootstrap_lang_style(
    config: ProjectConfig,
    provider: TranslationProvider,
    max_samples: int = 60,
) -> Optional[Path]:
    """Draft a lang-style.draft.md from a representative sample of TM entries."""
    tm = TranslationMemory(config.tm_db_path)
    samples: list[dict[str, str]] = []
    try:
        seen = set()
        for _, rec in tm.iter_all():
            src = rec.source.strip()
            tgt = rec.translation.strip()
            if src and tgt and src not in seen and len(src) >= 3:
                seen.add(src)
                samples.append({
                    "source": src,
                    "translation": tgt,
                    "category": rec.category or "dialogue",
                })
                if len(samples) >= max_samples:
                    break
    finally:
        tm.close()

    if not samples:
        return None

    system_prompt = (
        "You are an expert game localization style director (English -> Hungarian).\n"
        "Analyze the provided sample of translated game strings and draft a clean, practical Language Style Guide.\n\n"
        "--- INSTRUCTIONS ---\n"
        "1. Identify the register (e.g. informal tegezés vs formal exceptions).\n"
        "2. Detail Hungarian focus rules, word order, preverb placement, and natural sentence restructuring.\n"
        "3. Document formatting conventions: punctuation, capitalization, tag preservation (<keyword=...>, <style=...>).\n"
        "4. Note tone guidelines for fantasy/adventure dialog, UI brevity, and item descriptions.\n\n"
        "Output ONLY a valid Markdown document starting with `# Language style guide`."
    )
    user_payload = json.dumps(samples, ensure_ascii=False, indent=2)

    raw_response = await provider.complete(system_prompt, user_payload, effort="high")

    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text.startswith("# Language style guide"):
        text = "# Language style guide\n\n" + text

    out_path = config.root / "resources" / "lang-style.draft.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return out_path


async def bootstrap_character_voices(
    config: ProjectConfig,
    provider: TranslationProvider,
) -> tuple[Optional[Path], Optional[str]]:
    """Draft character-voices.draft.md if speaker metadata is present in batch files."""
    adapter = get_adapter(config.format, config.format_options)
    speaker_entries: dict[str, list[Entry]] = {}

    for path in config.batch_files:
        try:
            entries = adapter.extract(path)
        except Exception:
            continue
        for e in entries:
            if e.speaker and e.speaker.strip():
                speaker_entries.setdefault(e.speaker.strip(), []).append(e)

    if not speaker_entries:
        msg = "this project's format doesn't carry speaker metadata — skipping character-voices bootstrap"
        return None, msg

    # Cross-reference speaker lines against TM
    tm = TranslationMemory(config.tm_db_path)
    speaker_corpora: list[dict[str, Any]] = []
    try:
        for speaker, entries in speaker_entries.items():
            lines_sample: list[dict[str, str]] = []
            for e in entries[:15]:
                rec = tm.get(e.tm_key) if e.tm_key else None
                tgt = rec.translation if rec else e.target
                lines_sample.append({
                    "source": e.source,
                    "translation": tgt or "",
                })
            speaker_corpora.append({
                "character": speaker,
                "line_count": len(entries),
                "samples": lines_sample,
            })
    finally:
        tm.close()

    system_prompt = (
        "You are an expert game narrative localization director (English -> Hungarian).\n"
        "Analyze the dialogue lines spoken by each character and draft a character voice bible table.\n\n"
        "Output format MUST be ONLY a Markdown table with these exact headers:\n\n"
        "# Character voice bible\n\n"
        "| Character | Register | Traits | Avoid |\n"
        "|---|---|---|---|\n\n"
        "Columns:\n"
        "- Character: exact character name\n"
        "- Register: informal (tegezés) | formal (magázódás/önözés) | archaic | slang\n"
        "- Traits: key tone, speech habits, catchphrases, temperament\n"
        "- Avoid: phrases or tone out of character\n"
    )
    user_payload = json.dumps(speaker_corpora, ensure_ascii=False, indent=2)

    raw_response = await provider.complete(system_prompt, user_payload, effort="high")

    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text.startswith("# Character voice bible"):
        text = "# Character voice bible\n\n" + text

    out_path = config.root / "resources" / "character-voices.draft.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return out_path, None
