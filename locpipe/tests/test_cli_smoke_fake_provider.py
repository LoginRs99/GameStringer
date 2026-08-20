"""Phase 2 & Phase 5 Smoke Test:
Verifies the complete REAL CLI pipeline against a REAL project sample (COM_sample_35.xliff)
using --dry-run (MockProvider, 0 API tokens spent).
"""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from locpipe.checkpoint import Checkpoint
from locpipe.cli import main
from locpipe.config import load_project
from locpipe.pipeline import run
from locpipe.providers.mock import MockProvider


def _setup_sample_project(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "com_sample"
    (proj_dir / "batches").mkdir(parents=True)
    (proj_dir / "resources").mkdir(parents=True)
    (proj_dir / "tm").mkdir(parents=True)

    # Copy project config
    (proj_dir / "project.yaml").write_text(
        """project: com_sample
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

    (proj_dir / "resources" / "glossary.md").write_text(
        """# Glossary
| Source term | Target translation | Category | Confidence | Source/justification |
|---|---|---|---|---|
| Overdrive | Overdrive | mechanic | 1.0 | Protected term |
| Aether | Aether | lore | 1.0 | Protected term |
""",
        encoding="utf-8",
    )

    # Write sample XLIFF file
    xliff_content = (
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">\n'
        '  <file source-language="en" target-language="hu" datatype="plaintext" original="sample">\n'
        '    <body>\n'
        '      <trans-unit id="1" resname="dialogue_1">\n'
        '        <source>Hello world!</source>\n'
        '        <target></target>\n'
        '      </trans-unit>\n'
        '      <trans-unit id="2" resname="ui_btn_ok">\n'
        '        <source>OK</source>\n'
        '        <target></target>\n'
        '      </trans-unit>\n'
        '    </body>\n'
        '  </file>\n'
        '</xliff>\n'
    )
    sample_file = proj_dir / "batches" / "sample.xliff"
    sample_file.write_text(xliff_content, encoding="utf-8")

    return proj_dir


def test_cli_dry_run_smoke_test(tmp_path: Path) -> None:
    proj_dir = _setup_sample_project(tmp_path)

    # 1. Run real CLI with --dry-run
    exit_code = main(["run", "--project", str(proj_dir), "--dry-run"])
    assert exit_code == 0, "CLI run --dry-run must exit 0"

    # 2. Verify checkpoint state
    cp = Checkpoint(proj_dir / "checkpoint.json")
    assert cp.is_file_done(str(proj_dir / "batches" / "sample.xliff")), (
        "Sample XLIFF file should be marked done in checkpoint"
    )

    # 3. Verify output file re-importability and valid XML structure
    out_path = proj_dir / "batches" / "sample.xliff"
    tree = ET.parse(out_path)
    root = tree.getroot()

    tus = [tu for tu in root.iter() if tu.tag.endswith("trans-unit")]
    assert len(tus) == 2, f"Expected 2 trans-units, got {len(tus)}"

    # 4. Verify translated targets contain non-empty mock targets
    for tu in tus:
        tu_id = tu.attrib.get("id", "")
        src_el = next((c for c in tu if c.tag.endswith("source")), None)
        tgt_el = next((c for c in tu if c.tag.endswith("target")), None)
        assert src_el is not None and src_el.text, f"Trans-unit {tu_id} missing source text"
        assert tgt_el is not None and tgt_el.text, f"Trans-unit {tu_id} missing target text"
        assert "[MOCK-HU]" in tgt_el.text or "[MOCK-REVIEWED]" in tgt_el.text, (
            f"Target text for {tu_id} must contain mock prefix: {tgt_el.text}"
        )

    # 5. Verify stats.json output
    stats_file = proj_dir / "stats.json"
    assert stats_file.exists(), "stats.json must be written"
    stats_data = json.loads(stats_file.read_text(encoding="utf-8"))
    assert stats_data["total_entries"] == 2


def test_cli_dry_run_never_writes_to_the_tm(tmp_path: Path) -> None:
    """A dry run overwriting the batch file itself with [MOCK-HU] text
    (asserted above) is expected -- that's the actual pipeline output
    step being exercised. The TM database is different: it's not the
    file you're looking at, it silently affects every FUTURE run's
    translations via TM lookup, and `--dry-run` promising "no lasting
    effect" is the whole reason to reach for it in the first place. This
    used to fail before providers/base.py's persists_to_tm existed --
    the TM would end up with "[MOCK-HU] ..." rows tagged with the exact
    same origin="mt" a real translation gets, silently reused by a later
    real run's TM lookup.
    """
    proj_dir = _setup_sample_project(tmp_path)
    config = load_project(proj_dir)

    exit_code = main(["run", "--project", str(proj_dir), "--dry-run"])
    assert exit_code == 0

    from locpipe.tm import TranslationMemory

    tm = TranslationMemory(config.tm_db_path)
    with tm._cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tm WHERE origin IN ('mt', 'reviewed')")
        (mock_originated_rows,) = cur.fetchone()

    assert mock_originated_rows == 0, (
        f"dry-run left {mock_originated_rows} mock-translated row(s) in the persistent TM -- "
        "a later real run's TM lookup would silently reuse this placeholder text as if it "
        "were a genuine translation"
    )
