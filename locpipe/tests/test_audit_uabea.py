"""Tests for `locpipe audit`: the read-only extraction-report tool that
shows what uabea_json's typetree/array walk would keep vs. filter as
engine noise vs. filter via a configured path exclude, with zero LLM calls.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from locpipe.audit import build_audit_report, render_report_markdown, run_audit
from locpipe.adapters.registry import get_adapter
from locpipe.cli import main
from locpipe.config import load_project

FIXTURE = Path(__file__).parent / "fixtures" / "demo_project"

_TYPETREE_JSON = {
    "m_Name": "LocalizedTextBank",
    "entries": {
        "Dodge": "You narrowly dodge the incoming blow!",
        "AmirKabir_greeting": "Welcome to the bazaar, traveler.",
        "internal_metadata": {
            "asset_guid": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            "sprite_ref": "icons/dodge_icon.png",
        },
        "state_flags": {
            "combat_state": "GAME_STATE_PAUSED",
            "node_id": "weight_001",
        },
    },
}


def _setup_uabea_project(tmp_path: Path) -> Path:
    proj = tmp_path / "uabea_demo"
    (proj / "batches").mkdir(parents=True)
    (proj / "resources").mkdir(parents=True)

    for name in ("glossary.md", "lang-style.md", "character-voices.md", "anti-fabrication-checklist.md"):
        (proj / "resources" / name).write_text("(none)\n", encoding="utf-8")

    (proj / "project.yaml").write_text(
        """project: uabea_demo
source_lang: en
target_lang: hu
format: uabea_json
format_options:
  source_column: EN
  target_column: HU
batches:
  glob: "batches/*.json"
resources:
  glossary: resources/glossary.md
  lang_style: resources/lang-style.md
  character_voices: resources/character-voices.md
  anti_fabrication_checklist: resources/anti-fabrication-checklist.md
categories:
  - name: default
    batch_size: 500
provider:
  name: antigravity_cli
  model: gemini-3.7-flash
""",
        encoding="utf-8",
    )
    (proj / "batches" / "LocalizedTextBank.json").write_text(json.dumps(_TYPETREE_JSON), encoding="utf-8")
    return proj


def test_build_audit_report_counts_and_groups(tmp_path: Path) -> None:
    proj = _setup_uabea_project(tmp_path)
    config = load_project(proj)
    adapter = get_adapter(config.format, config.format_options)

    report = build_audit_report(config, adapter)

    assert report["supported"] is True
    assert report["files_scanned"] == 1
    assert report["files_failed"] == []

    reasons = report["reason_counts"]
    assert reasons["kept"] == 2
    assert reasons["noise:guid"] == 1
    assert reasons["noise:asset-reference"] == 1
    assert reasons["noise:enum-constant"] == 1
    assert reasons["noise:indexed-identifier"] == 1
    assert "excluded_by_config" not in reasons  # no exclude patterns configured


def test_run_audit_matches_build_audit_report(tmp_path: Path) -> None:
    proj = _setup_uabea_project(tmp_path)
    config = load_project(proj)
    assert run_audit(config) == build_audit_report(config, get_adapter(config.format, config.format_options))


def test_render_report_markdown_mentions_kept_and_noise_examples(tmp_path: Path) -> None:
    proj = _setup_uabea_project(tmp_path)
    config = load_project(proj)
    report = run_audit(config)
    markdown = render_report_markdown(report, config.project)

    assert "You narrowly dodge the incoming blow!" in markdown
    assert "3f2504e0-4f89-11d3-9a0c-0305e82c3301" in markdown
    assert "noise:guid" in markdown
    assert "noise:asset-reference" in markdown


def test_cli_audit_writes_report_and_prints_summary(tmp_path: Path, capsys) -> None:
    proj = _setup_uabea_project(tmp_path)

    rc = main(["audit", "--project", str(proj)])

    assert rc == 0
    report_path = proj / "audit_report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "kept, sent to the LLM" in content
    assert "filtered as engine noise" in content

    captured = capsys.readouterr()
    assert "kept (would be sent to the LLM):        2" in captured.out


def test_cli_audit_custom_out_path(tmp_path: Path) -> None:
    proj = _setup_uabea_project(tmp_path)
    out_path = tmp_path / "custom_report.md"

    rc = main(["audit", "--project", str(proj), "--out", str(out_path)])

    assert rc == 0
    assert out_path.exists()
    assert not (proj / "audit_report.md").exists()


def test_uabea_json_path_exclude_shows_up_as_its_own_bucket(tmp_path: Path) -> None:
    proj = _setup_uabea_project(tmp_path)
    project_yaml = proj / "project.yaml"
    project_yaml.write_text(
        project_yaml.read_text(encoding="utf-8").replace(
            "format_options:\n  source_column: EN\n  target_column: HU\n",
            "format_options:\n  source_column: EN\n  target_column: HU\n"
            "  uabea_json_path_exclude:\n    - \"^entries\\\\.internal_metadata\"\n",
        ),
        encoding="utf-8",
    )
    config = load_project(proj)
    adapter = get_adapter(config.format, config.format_options)
    report = build_audit_report(config, adapter)

    assert report["reason_counts"]["excluded_by_config"] == 2
    # Those two were previously counted as noise:guid / noise:asset-reference;
    # excluded_by_config takes priority, so those noise buckets are now empty.
    assert "noise:guid" not in report["reason_counts"]
    assert "noise:asset-reference" not in report["reason_counts"]


def test_audit_unsupported_format_is_graceful(tmp_path: Path) -> None:
    dest = tmp_path / "demo_project"
    shutil.copytree(FIXTURE, dest)

    rc = main(["audit", "--project", str(dest)])

    assert rc == 0
    content = (dest / "audit_report.md").read_text(encoding="utf-8")
    assert "doesn't support extraction auditing yet" in content
