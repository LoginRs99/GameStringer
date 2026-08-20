"""Comprehensive QA Escalation Strategy Tests:
Verifies Tier 0 (0-token Python), Tier 1 (Gemini 3.6 Flash Low), and Tier 2 (Gemini 3.6 Flash High escalation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from locpipe.cli import main
from locpipe.config import load_project
from locpipe.models import Entry, EntryStatus, ValidationIssue, ValidationResult, Severity
from locpipe.pipeline import run, should_escalate_to_high
from locpipe.providers.base import TranslationProvider
from locpipe.review_queue import ReviewItem


class TrackedMockProvider(TranslationProvider):
    def __init__(self, name: str, fail_keys: set[str] | None = None):
        self.name = name
        self.fail_keys = fail_keys or set()
        self.call_count = 0

    async def complete(self, system_prompt: str, user_payload: str, *, max_tokens: int = 8192) -> str:
        self.call_count += 1
        parsed = json.loads(user_payload)
        items = parsed.get("items", [])
        out = []
        for item in items:
            key = item["key"]
            if key in self.fail_keys:
                out.append({"key": key, "translation": item["current_translation"], "flag_for_human": True})
            else:
                out.append({"key": key, "translation": f"[{self.name}-FIXED] {item['source']}", "flag_for_human": False})
        return json.dumps(out, ensure_ascii=False)


def test_normal_valid_translation_no_high_call(tmp_path: Path) -> None:
    proj_dir = tmp_path / "proj1"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("project: p1\nsource_lang: en\ntarget_lang: hu\nformat: xliff\nbatches:\n  glob: \"batches/*.xliff\"\nprovider:\n  name: antigravity_cli\n", encoding="utf-8")
    (proj_dir / "batches" / "b.xliff").write_text('<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2"><file><trans-unit id="1"><source>Attack</source><target></target></trans-unit></file></xliff>', encoding="utf-8")

    config = load_project(proj_dir)
    provider = TrackedMockProvider("base")
    review_provider = TrackedMockProvider("low")
    escalation_provider = TrackedMockProvider("high")

    stats = run(config, provider, review_provider=review_provider, escalation_provider=escalation_provider)
    assert stats.high_qa_calls == 0
    assert stats.escalated_to_high_count == 0


def test_escalation_condition_functions(tmp_path: Path) -> None:
    proj_dir = tmp_path / "proj2"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("project: p2\nsource_lang: en\ntarget_lang: hu\nformat: xliff\nbatches:\n  glob: \"batches/*.xliff\"\nprovider:\n  name: antigravity_cli\n", encoding="utf-8")

    config = load_project(proj_dir)

    # 1. Short simple entry -> Low QA default
    e_simple = Entry(file="f", key="k1", source="Attack")
    vr_pass = ValidationResult(entry_key="k1")
    item_simple = ReviewItem(entry=e_simple, validation=vr_pass, confidence=0.85)
    esc, reason = should_escalate_to_high(item_simple, config)
    assert not esc
    assert reason == "low_qa_default"

    # 2. Structural issue with confidence > threshold -> Low QA
    vr_err = ValidationResult(entry_key="k1", major=[ValidationIssue(Severity.MAJOR, "xliff", "placeholder mismatch")])
    item_markup = ReviewItem(entry=e_simple, validation=vr_err, confidence=0.75)
    esc, reason = should_escalate_to_high(item_markup, config)
    assert not esc
    assert reason == "low_qa_default"

    # 3. High structural complexity (> 3 tags/placeholders) -> Escalates
    e_complex = Entry(file="f", key="k2", source="{a} {b} {c} {d} Press button")
    item_complex = ReviewItem(entry=e_complex, validation=vr_pass, confidence=0.85)
    esc, reason = should_escalate_to_high(item_complex, config)
    assert esc
    assert reason == "high_structural_complexity"

    # 4. Long dialogue (> 250 chars) -> Escalates
    e_long = Entry(file="f", key="k3", source="A" * 260)
    item_long = ReviewItem(entry=e_long, validation=vr_pass, confidence=0.85)
    esc, reason = should_escalate_to_high(item_long, config)
    assert esc
    assert reason == "long_dialogue"

    # 5. Low confidence (< 0.30) -> Escalates
    item_low_conf = ReviewItem(entry=e_simple, validation=vr_pass, confidence=0.20)
    esc, reason = should_escalate_to_high(item_low_conf, config)
    assert esc
    assert reason == "low_confidence"


class CorruptingMockProvider(TranslationProvider):
    async def complete(self, system_prompt: str, user_payload: str, *, max_tokens: int = 8192) -> str:
        parsed = json.loads(user_payload)
        out = [{"id": item["id"], "translation": "Corrupted text without placeholder"} for item in parsed]
        return json.dumps(out, ensure_ascii=False)


def test_low_repair_fails_escalates_to_high(tmp_path: Path) -> None:
    proj_dir = tmp_path / "proj3"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("project: p3\nsource_lang: en\ntarget_lang: hu\nformat: xliff\nbatches:\n  glob: \"batches/*.xliff\"\nprovider:\n  name: antigravity_cli\n", encoding="utf-8")
    (proj_dir / "batches" / "b.xliff").write_text('<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2"><file><trans-unit id="k1"><source>{playerName} text</source><target></target></trans-unit></file></xliff>', encoding="utf-8")

    config = load_project(proj_dir)

    # Low QA fails on k1, High QA succeeds
    provider = CorruptingMockProvider()
    low_qa = TrackedMockProvider("low", fail_keys={"k1"})
    high_qa = TrackedMockProvider("high")

    stats = run(config, provider, review_provider=low_qa, escalation_provider=high_qa)
    assert stats.low_qa_calls >= 1
    assert stats.high_qa_calls >= 1
    assert stats.high_qa_repairs >= 1


def test_high_disabled_low_remains_maximum_tier(tmp_path: Path) -> None:
    proj_dir = tmp_path / "proj4"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("project: p4\nsource_lang: en\ntarget_lang: hu\nformat: xliff\nbatches:\n  glob: \"batches/*.xliff\"\nprovider:\n  name: antigravity_cli\n  escalation_enabled: false\n", encoding="utf-8")
    (proj_dir / "batches" / "b.xliff").write_text('<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2"><file><trans-unit id="k1"><source>{playerName} text</source><target>Corrupted text</target></trans-unit></file></xliff>', encoding="utf-8")

    config = load_project(proj_dir)
    assert not config.provider.escalation_enabled

    low_qa = TrackedMockProvider("low", fail_keys={"k1"})
    high_qa = TrackedMockProvider("high")

    stats = run(config, TrackedMockProvider("base"), review_provider=low_qa, escalation_provider=high_qa)
    assert stats.high_qa_calls == 0
