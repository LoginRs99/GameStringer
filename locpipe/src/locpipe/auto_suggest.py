"""AI-powered auto-discovery for project style presets, character voices, and glossary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from .adapters.registry import get_adapter
from .config import ProjectConfig
from .models import Entry
from .presets import LANG_STYLE_PRESETS
from .providers.base import TranslationProvider


@dataclass
class SuggestionResult:
    recommended_preset: str
    preset_rationale: str
    style_guide_content: str
    glossary_items: list[dict[str, str]]
    character_voices: list[dict[str, str]]


async def analyze_project_and_suggest(
    config: ProjectConfig,
    provider: TranslationProvider,
    sample_size: int = 40,
) -> SuggestionResult:
    adapter = get_adapter(config.format, config.format_options)
    all_entries: List[Entry] = []

    for path in config.batch_files:
        try:
            entries = adapter.extract(path)
            all_entries.extend(entries)
        except Exception:
            continue

    if not all_entries:
        raise ValueError(f"No entries could be extracted from batch files in '{config.project}'.")

    # Sample representative strings
    sample_entries = all_entries[:sample_size]
    sample_texts = [
        {"source": e.source, "notes": e.notes, "category": e.category}
        for e in sample_entries
        if e.source and len(e.source.strip()) > 1
    ]

    preset_names = list(LANG_STYLE_PRESETS.keys())
    preset_list_str = "\n".join(f"- {name}" for name in preset_names)

    system_prompt = (
        "You are an expert video game localization director for English -> Hungarian.\n"
        "Analyze the provided sample game strings and game title to determine the optimal localization resources.\n\n"
        "Available Language Style Presets:\n"
        f"{preset_list_str}\n\n"
        "Respond ONLY with a JSON object with this exact schema:\n"
        "{\n"
        '  "recommended_preset": "Exact name of one of the available presets above",\n'
        '  "preset_rationale": "Short explanation of why this preset fits the game",\n'
        '  "glossary": [\n'
        '    {"source": "English term/name", "target": "Hungarian translation/proper noun", "category": "Proper noun/UI/Mechanics", "note": "Context"}\n'
        "  ],\n"
        '  "character_voices": [\n'
        '    {"character": "Character name", "register": "informal/formal", "traits": "Short description of speech style"}\n'
        "  ]\n"
        "}"
    )

    user_payload = json.dumps(
        {
            "game_title": config.project,
            "sample_strings": sample_texts,
        },
        ensure_ascii=False,
        indent=2,
    )

    raw_response = await provider.complete(system_prompt, user_payload, effort="low")

    text = raw_response.strip().strip("`")
    if text.startswith("json"):
        text = text[4:].strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1:
        text = text[start_idx : end_idx + 1]

    data = json.loads(text)

    rec_preset = data.get("recommended_preset", preset_names[0])
    if rec_preset not in LANG_STYLE_PRESETS:
        # Match closest
        for name in preset_names:
            if name.split()[0].lower() in rec_preset.lower():
                rec_preset = name
                break
        else:
            rec_preset = preset_names[0]

    style_guide_content = LANG_STYLE_PRESETS[rec_preset]

    return SuggestionResult(
        recommended_preset=rec_preset,
        preset_rationale=data.get("preset_rationale", ""),
        style_guide_content=style_guide_content,
        glossary_items=data.get("glossary", []),
        character_voices=data.get("character_voices", []),
    )
