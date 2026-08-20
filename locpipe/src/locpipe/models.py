"""Core data types shared across every pipeline stage.

These are format-agnostic and project-agnostic on purpose. A format
adapter's only job is to turn its native file into a list[Entry] and,
later, turn translated Entry objects back into that native file.
Nothing downstream of extraction needs to know what format produced
an Entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class EntryStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    TM_REUSED = "TM_REUSED"          # filled from translation memory, no LLM call
    MT_DRAFT = "MT_DRAFT"            # filled by the bulk translation call
    VALIDATED = "VALIDATED"          # passed deterministic validation
    NEEDS_REVIEW = "NEEDS_REVIEW"    # failed validation or low confidence
    REVIEWED = "REVIEWED"            # repaired by the intelligent-review step
    BLOCKED = "BLOCKED"              # needs a human decision the pipeline can't make


@dataclass
class Entry:
    """One localizable string, in a format-agnostic shape.

    file / namespace / key are provenance only — never sent to the LLM.
    context_screen, speaker, max_length are optional, format-supplied
    context used for classification, TM context-scoping, and validation.
    """

    file: str
    key: str
    source: str
    target: str = ""
    namespace: str = ""
    notes: list[str] = field(default_factory=list)
    speaker: Optional[str] = None
    context_screen: Optional[str] = None
    max_length: Optional[int] = None
    preceding_context: list[dict] = field(default_factory=list)  # [{"speaker":.., "source":..}, ...], set by narrative_context.py
    extra: dict[str, Any] = field(default_factory=dict)  # format-specific passthrough

    status: EntryStatus = EntryStatus.NOT_STARTED
    category: Optional[str] = None          # set by classify.py
    context_key: Optional[str] = None       # set by context_key.py — the TM disambiguator
    content_hash: Optional[str] = None      # set by normalize.py — incremental-update key
    tm_key: Optional[str] = None            # set by dedupe.py — (content_hash, category, context_key)
    confidence: Optional[float] = None
    validation_issues: list["ValidationIssue"] = field(default_factory=list)
    origin: Optional[str] = None            # "tm" | "mt" | "reviewed" | "human"

    @property
    def is_empty_or_stub(self) -> bool:
        return not self.target.strip() or self.target.strip() == self.source.strip()


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class ValidationResult:
    entry_key: str
    critical: list[ValidationIssue] = field(default_factory=list)
    major: list[ValidationIssue] = field(default_factory=list)
    minor: list[ValidationIssue] = field(default_factory=list)
    info: list[ValidationIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.critical and not self.major

    @property
    def all_issues(self) -> list[ValidationIssue]:
        return self.critical + self.major + self.minor + self.info


@dataclass
class GlossaryTerm:
    source_term: str
    target_term: str
    category: str            # brand | lore | mechanic | ui | person
    confidence: str          # high | medium | low
    justification: str = ""
    is_disputed: bool = False        # true for "Network -> Hálózat / Tévéadó" style dual entries
    context_hint: Optional[str] = None  # free text disambiguation hint from the notes column


@dataclass
class TMRecord:
    tm_key: str
    source: str
    translation: str
    source_lang: str
    target_lang: str
    category: str
    context_key: Optional[str]
    quality_score: float
    origin: str               # "human" | "reviewed" | "mt"
    times_used: int = 0
