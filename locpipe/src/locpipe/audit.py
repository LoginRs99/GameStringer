"""`locpipe audit` -- for adapters that support it (currently uabea_json's
Case 2/3 typetree/array walk -- see adapters/uabea_json.py's audit_sink
parameter), runs extraction across every pending batch file WITHOUT calling
an LLM, and reports what got kept, what the built-in engine-noise heuristic
dropped, and what a configured uabea_json_path_exclude pattern dropped.

The point: instead of guessing what a project's noise looks like, run this
once, skim the report, and either (a) confirm the built-in filter isn't
dropping anything real, or (b) add a path pattern for whatever junk it
missed to format_options.uabea_json_path_exclude in project.yaml. Both are
one-time, per-project decisions -- every extraction after that benefits for
free.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from pathlib import Path
from typing import Any

from .adapters.base import FormatAdapter
from .adapters.registry import get_adapter
from .config import ProjectConfig

_EXAMPLES_PER_GROUP = 4
_GROUP_PATH_SEGMENTS = 2  # group report rows by the first N dotted path segments
_VALUE_PREVIEW_LEN = 80


def _group_key(asset_name: str, json_path: str) -> str:
    segments = json_path.split(".")[:_GROUP_PATH_SEGMENTS]
    return f"{asset_name}:" + ".".join(segments)


def build_audit_report(config: ProjectConfig, adapter: FormatAdapter) -> dict[str, Any]:
    if "audit_sink" not in inspect.signature(adapter.extract).parameters:
        return {"supported": False}

    group_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    group_examples: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    reason_counts: dict[str, int] = defaultdict(int)
    files_scanned = 0
    files_failed: list[str] = []

    for path in config.batch_files:
        sink: list[tuple[str, str, str]] = []
        try:
            adapter.extract(path, audit_sink=sink)
        except Exception as e:
            files_failed.append(f"{path.name}: {type(e).__name__}: {e}")
            continue
        files_scanned += 1
        asset_name = path.stem
        for json_path, value, action in sink:
            key = _group_key(asset_name, json_path)
            group_counts[key][action] += 1
            reason_counts[action] += 1
            bucket = group_examples[key][action]
            if len(bucket) < _EXAMPLES_PER_GROUP:
                bucket.append((json_path, value))

    return {
        "supported": True,
        "files_scanned": files_scanned,
        "files_failed": files_failed,
        "reason_counts": dict(reason_counts),
        "group_counts": {k: dict(v) for k, v in group_counts.items()},
        "group_examples": {k: dict(v) for k, v in group_examples.items()},
    }


def run_audit(config: ProjectConfig) -> dict[str, Any]:
    adapter = get_adapter(config.format, config.format_options)
    return build_audit_report(config, adapter)


def _preview(value: str) -> str:
    value = value.replace("\n", "\\n")
    if len(value) > _VALUE_PREVIEW_LEN:
        return value[: _VALUE_PREVIEW_LEN - 3] + "..."
    return value


def render_report_markdown(report: dict[str, Any], project_name: str) -> str:
    if not report["supported"]:
        return (
            f"# Extraction audit -- {project_name}\n\n"
            "This project's format adapter doesn't support extraction "
            "auditing yet (only uabea_json's typetree/array walk does, "
            "currently -- everything else either has a much narrower, "
            "already-precise extraction path, like uabea_json's own CSV-"
            "in-m_Script case, or hasn't needed this yet).\n"
        )

    lines: list[str] = [f"# Extraction audit -- {project_name}", ""]
    lines.append(f"Files scanned: {report['files_scanned']}")
    if report["files_failed"]:
        lines.append(f"Files that failed to parse (skipped): {len(report['files_failed'])}")
    lines.append("")

    reasons = report["reason_counts"]
    kept = reasons.get("kept", 0)
    excluded = reasons.get("excluded_by_config", 0)
    noise_reasons = {k: v for k, v in reasons.items() if k.startswith("noise:")}
    noise_total = sum(noise_reasons.values())
    scanned_total = kept + excluded + noise_total

    lines.append("## Totals")
    lines.append(f"- **kept, sent to the LLM:** {kept}")
    lines.append(f"- **filtered by uabea_json_path_exclude:** {excluded}")
    lines.append(f"- **filtered as engine noise (built-in heuristic):** {noise_total}")
    for reason, count in sorted(noise_reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"    - {reason.removeprefix('noise:')}: {count}")
    if scanned_total:
        skipped_pct = 100 * (excluded + noise_total) / scanned_total
        lines.append(f"- **strings kept out of every LLM call this run:** {skipped_pct:.1f}%")
    lines.append("")

    lines.append("## By asset / path group")
    lines.append("")
    lines.append(
        "Each group is `asset:first-two-path-segments`. Skim the **kept** "
        "rows for anything that still looks like engine junk -- add a "
        "pattern for it to `format_options.uabea_json_path_exclude` in "
        "project.yaml. Skim the **noise:*** rows for anything that should "
        "actually be translated -- if the built-in heuristic gets your "
        "project wrong, set `format_options.noise_filter: false` and rely "
        "on explicit excludes instead (see uabea_json_path_exclude)."
    )
    lines.append("")

    for group_key in sorted(report["group_counts"].keys()):
        counts = report["group_counts"][group_key]
        examples = report["group_examples"][group_key]
        lines.append(f"### {group_key}")
        for action in sorted(counts.keys()):
            n = counts[action]
            shown = examples.get(action, [])
            more = f" ({n} total)" if n > len(shown) else ""
            lines.append(f"- **{action}**{more}:")
            for json_path, value in shown:
                lines.append(f"  - `{json_path}` = {_preview(value)!r}")
        lines.append("")

    return "\n".join(lines)
