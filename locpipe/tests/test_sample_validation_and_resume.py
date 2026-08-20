"""Comprehensive test suite for Phase 6 & Phase 7:
Validates a representative game translation sample containing:
- short UI strings
- normal dialogue
- long RPG dialogue
- multiline strings
- placeholders ({count}, {location})
- variables (%s, %d)
- formatting tags (<color>, <b>)
- special characters & punctuation
- duplicate strings
- protected mechanic terms
- checkpoint & resumability safety
"""

from __future__ import annotations

import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from locpipe.checkpoint import Checkpoint
from locpipe.config import load_project
from locpipe.pipeline import plan, run
from locpipe.providers.base import TranslationProvider


class _MockSampleProvider(TranslationProvider):
    """Predictable mock provider that translates strings while preserving
    placeholders, formatting tags, and newlines accurately.
    """

    def __init__(self, fail_on_id: str | None = None):
        self.fail_on_id = fail_on_id
        self.calls: list[str] = []

    async def complete(self, system_prompt: str, user_payload: str, *, max_tokens: int = 8192) -> str:
        self.calls.append(user_payload)
        parsed = json.loads(user_payload)

        out = []
        for item in parsed:
            src = item["source"]
            item_id = item["id"]
            if self.fail_on_id and (str(item_id) == str(self.fail_on_id) or self.fail_on_id in src):
                raise RuntimeError(f"Simulated failure on item {item_id} ({src})")

            # Translate plain words while preserving placeholders, tags, and newlines
            target = f"[HU] {src}"
            out.append({"id": item_id, "translation": target})

        return json.dumps(out, ensure_ascii=False)


def _create_sample_project(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "sample_game"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "tm").mkdir(parents=True)

    # Write project.yaml
    (proj_dir / "project.yaml").write_text(
        """project: sample_game
source_lang: en
target_lang: hu
format: xliff

batches:
  glob: "batches/*.xliff"

resources:
  glossary: resources/glossary.md

categories:
  - name: dialogue
    match_speaker_present: true
    needs_character_voice: false
    batch_size: 50
  - name: ui
    default: true
    needs_character_voice: false
    batch_size: 50

provider:
  name: antigravity_cli
  model: gemini-3.7-flash
  mode: sync

confidence:
  review_threshold: 0.75
  tier1_repair_attempts: 2
""",
        encoding="utf-8",
    )

    # Write glossary.md with protected terms
    (proj_dir / "resources" / "glossary.md").write_text(
        """# Glossary
| Source term | Target translation | Category | Confidence | Source/justification |
|---|---|---|---|---|
| Overdrive | Overdrive | mechanic | 1.0 | Protected mechanic term |
| Aether | Aether | lore | 1.0 | Protected lore term |
""",
        encoding="utf-8",
    )

    # Create sample XLIFF file 1
    xliff_content_1 = """<?xml version="1.0" encoding="utf-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file original="sample_ui.csv" source-language="en" target-language="hu" datatype="plaintext">
    <body>
      <trans-unit id="ui_ok">
        <source>OK</source>
        <target></target>
      </trans-unit>
      <trans-unit id="ui_cancel_1">
        <source>Cancel</source>
        <target></target>
      </trans-unit>
      <trans-unit id="ui_cancel_2">
        <source>Cancel</source>
        <target></target>
      </trans-unit>
      <trans-unit id="msg_items_found">
        <source>Found {count} item(s) in {location}.</source>
        <target></target>
      </trans-unit>
      <trans-unit id="fmt_player_score">
        <source>Player %s scored %d points.</source>
        <target></target>
      </trans-unit>
      <trans-unit id="ui_critical_hit">
        <source>&lt;color=#FF0000&gt;&lt;b&gt;CRITICAL HIT!&lt;/b&gt;&lt;/color&gt; You dealt {damage} damage.</source>
        <target></target>
      </trans-unit>
    </body>
  </file>
</xliff>"""
    (proj_dir / "batches" / "sample_file1.xliff").write_text(xliff_content_1, encoding="utf-8")

    # Create sample XLIFF file 2 (dialogue + RPG dialogue)
    xliff_content_2 = """<?xml version="1.0" encoding="utf-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file original="sample_dialogue.csv" source-language="en" target-language="hu" datatype="plaintext">
    <body>
      <trans-unit id="dlg_hero_01">
        <source>We must reach the fortress before nightfall.</source>
        <target></target>
        <note>speaker: Hero</note>
      </trans-unit>
      <trans-unit id="dlg_sage_long">
        <source>Long ago, when the ancient Aether fires still burned across the realm of Eldoria, the guardians forged three artifacts of immense power. Do not underestimate what lies ahead.</source>
        <target></target>
        <note>speaker: Sage</note>
      </trans-unit>
      <trans-unit id="quest_desc_01">
        <source>Objective 1: Speak to the innkeeper.
Objective 2: Retrieve the lost key from the dungeon.</source>
        <target></target>
      </trans-unit>
      <trans-unit id="dlg_elena_dots">
        <source>Wait... is that... a dragon?! 'Run!' she yelled.</source>
        <target></target>
        <note>speaker: Elena</note>
      </trans-unit>
      <trans-unit id="ui_overdrive">
        <source>Activate Overdrive mode using 100 Aether points.</source>
        <target></target>
      </trans-unit>
    </body>
  </file>
</xliff>"""
    (proj_dir / "batches" / "sample_file2.xliff").write_text(xliff_content_2, encoding="utf-8")

    return proj_dir


def test_representative_sample_end_to_end(tmp_path: Path) -> None:
    proj_dir = _create_sample_project(tmp_path)
    config = load_project(proj_dir)

    # 1. Test plan command
    plan_res = plan(config)
    assert plan_res["total_entries"] == 11
    assert plan_res["unique_strings_needing_translation"] == 10  # 1 duplicate "Cancel"

    # 2. Test run command
    provider = _MockSampleProvider()
    stats = run(config, provider)

    assert stats.total_entries == 11
    assert stats.unique_strings_sent_to_llm == 10

    # Verify XLIFF file 1 merged output
    tree1 = ET.parse(proj_dir / "batches" / "sample_file1.xliff")
    root1 = tree1.getroot()
    targets1 = {tu.attrib["id"]: list(tu.iter())[-1].text for tu in root1.iter() if tu.tag.endswith("trans-unit")}

    assert "ui_ok" in targets1
    assert targets1["ui_ok"] == "[HU] OK"
    # Verify duplicates share identical translation
    assert targets1["ui_cancel_1"] == "[HU] Cancel"
    assert targets1["ui_cancel_2"] == "[HU] Cancel"
    # Verify placeholders preserved
    assert "{count}" in targets1["msg_items_found"] and "{location}" in targets1["msg_items_found"]
    assert "%s" in targets1["fmt_player_score"] and "%d" in targets1["fmt_player_score"]
    assert "{damage}" in targets1["ui_critical_hit"]

    # Verify XLIFF file 2 merged output
    tree2 = ET.parse(proj_dir / "batches" / "sample_file2.xliff")
    root2 = tree2.getroot()
    targets2 = {tu.attrib["id"]: list(tu.iter())[-1].text for tu in root2.iter() if tu.tag.endswith("trans-unit")}

    assert "dlg_hero_01" in targets2
    assert "dlg_sage_long" in targets2
    # Verify multiline string newline preserved
    assert "\n" in targets2["quest_desc_01"]
    # Verify protected mechanic terms preserved
    assert "Overdrive" in targets2["ui_overdrive"]
    assert "Aether" in targets2["ui_overdrive"]

    # Verify checkpoint state
    cp = Checkpoint(proj_dir / "checkpoint.json")
    assert cp.is_file_done(str(proj_dir / "batches" / "sample_file1.xliff"))
    assert cp.is_file_done(str(proj_dir / "batches" / "sample_file2.xliff"))


def test_checkpoint_interrupt_and_resume(tmp_path: Path) -> None:
    proj_dir = _create_sample_project(tmp_path)
    config = load_project(proj_dir)

    # First run fails on file 2 (contains string 'Eldoria')
    failing_provider = _MockSampleProvider(fail_on_id="Eldoria")
    run(config, failing_provider)

    cp = Checkpoint(proj_dir / "checkpoint.json")
    # File 1 completed
    assert cp.is_file_done(str(proj_dir / "batches" / "sample_file1.xliff"))
    # File 2 did not complete
    assert not cp.is_file_done(str(proj_dir / "batches" / "sample_file2.xliff"))

    # Second run with working provider
    working_provider = _MockSampleProvider()
    stats2 = run(config, working_provider)

    # Checkpoint marks both done after re-loading state
    cp2 = Checkpoint(proj_dir / "checkpoint.json")
    assert cp2.is_file_done(str(proj_dir / "batches" / "sample_file1.xliff"))
    assert cp2.is_file_done(str(proj_dir / "batches" / "sample_file2.xliff"))

    # File 1 should not have been re-requested from provider during second run
    file1_sources = ["OK", "Cancel", "Found {count} item(s) in {location}."]
    for call_payload in working_provider.calls:
        for s in file1_sources:
            assert s not in call_payload, f"File 1 string '{s}' was retransmitted on resume!"
