"""Phase 12. A thin, boring collector on purpose — the interesting
logic already happened in validators/ (Phase 10) and confidence.py
(Phase 11). This just gathers what they flagged and gives it a stable
on-disk shape so a run can be interrupted and resumed without losing
track of what still needs a human or a reviewer-LLM pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .glossary import GlossaryTerm
from .models import Entry, ValidationResult


@dataclass
class ReviewItem:
    entry: Entry
    validation: ValidationResult
    confidence: float
    nearby_notes: list[str] = field(default_factory=list)
    relevant_glossary_terms: list[GlossaryTerm] = field(default_factory=list)
    # Plain-text reasons from confidence.confidence_flags() -- covers the
    # heuristic deductions (length, identity passthrough, disputed glossary
    # term, speaker uncertainty) that never produced a ValidationIssue and
    # so wouldn't otherwise appear anywhere in this payload.
    confidence_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.entry.key,
            "file": self.entry.file,
            "category": self.entry.category,
            "speaker": self.entry.speaker,
            "source": self.entry.source,
            "current_translation": self.entry.target,
            "confidence": round(self.confidence, 3),
            "issues": [
                {"severity": i.severity.value, "code": i.code, "message": i.message}
                for i in self.validation.all_issues
            ],
            "confidence_flags": self.confidence_flags,
            "glossary_hits": [
                {"source_term": t.source_term, "target_term": t.target_term, "disputed": t.is_disputed}
                for t in self.relevant_glossary_terms
            ],
        }


def write_review_queue(items: list[ReviewItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
