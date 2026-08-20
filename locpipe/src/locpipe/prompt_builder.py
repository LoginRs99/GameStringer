"""PromptBuilder: loads locpipe/agents/*.md and substitutes %%TOKEN%%
placeholders. The templates are static, project-agnostic English text
at rest — same principle as glossary.md/lang-style.md living outside
Python for a *project*, just applied to the instructions themselves.
Changing how the translator or reviewer is instructed is now a
markdown edit, not a Python edit.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_AGENTS_DIR = Path(__file__).parent / "agents"


def load_template(name: str) -> str:
    return _load_template_cached(name)


@lru_cache(maxsize=None)
def _load_template_cached(name: str) -> str:
    """Templates under agents/ are static for the lifetime of a process --
    they're read-only prompt text shipped with locpipe, never edited by a
    running pipeline. Caching means a project with thousands of batches
    reads translate.md/review.md off disk once instead of once per batch.
    """
    path = _AGENTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(f"%%{key.upper()}%%", value)
    return template


def toggle_section(template: str, start_marker: str, end_marker: str, *, keep: bool) -> str:
    """A %%SECTION_START%% ... %%SECTION_END%% block: keep=True unwraps
    it (removes just the marker lines, leaves the content), keep=False
    removes the whole block. Used for translate.md's character-voice
    section, which only applies to categories that need it.
    """
    start_idx = template.find(start_marker)
    end_idx = template.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        return template
    before = template[:start_idx]
    after = template[end_idx + len(end_marker):]
    if keep:
        middle = template[start_idx + len(start_marker):end_idx]
        return before + middle + after
    return before + after
