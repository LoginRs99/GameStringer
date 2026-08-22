from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_project
from .audit import run_audit, render_report_markdown
from .adapters.registry import get_adapter
from .pipeline import plan, run

_INIT_TEMPLATE = """\
project: {name}
source_lang: en
target_lang: hu
target_register: informal   # informal (tegez — default) | formal (magáz)

format: generic_kv   # ported: generic_kv, po_gettext, ue4_5_po (Unreal Localization
                     # Dashboard .po export), unity (official Localization Package CSV
                     # export), uabea_json (UABEA asset-dump export), xliff/weblate_xliff
                     # -- see locpipe/adapters/registry.py for details on each

batches:
  glob: "batches/*.json"

resources:
  glossary: resources/glossary.md
  lang_style: resources/lang-style.md
  character_voices: resources/character-voices.md
  anti_fabrication_checklist: resources/anti-fabrication-checklist.md

categories:
  - name: dialogue
    match_speaker_present: true
    needs_character_voice: true
    batch_size: 200
    max_expansion_ratio: 1.8   # dialogue usually has room to run a bit longer
  # Uncomment for a ue4_5_po project: routes Unreal's {{Arg}}|plural(...)/
  # gender(...)/ordinal(...) argument-modifier syntax to its own category
  # BEFORE the dialogue/ui rules below get a chance to claim it, since a
  # smaller batch_size here means fewer of these structurally-sensitive
  # entries share a single LLM call/failure -- see validators/
  # validate_ue4_5_po.py for the mechanical check that runs on these either
  # way, but keeping the batch small limits the blast radius of one bad
  # response and makes them easier to spot-check by hand if flagged.
  # - name: format_sensitive
  #   match_source_regex: '\\|(plural|gender|ordinal)\\('
  #   batch_size: 80
  #   max_expansion_ratio: 2.0
  # Uncomment for a Unity CSV project with a Type/content_type column -- the
  # unity adapter puts that column's value into notes as "type:<value>"
  # (e.g. "type:dialogue"), reachable here via match_notes_regex.
  # - name: dialogue
  #   match_notes_regex: 'type:dialogue'
  #   needs_character_voice: true
  #   batch_size: 200
  - name: ui
    default: true
    needs_character_voice: false
    batch_size: 350
    max_expansion_ratio: 1.3   # tighter: buttons/labels are the ones that actually clip
    default_max_length: 40     # only if you know real UI limits and the format has no
                               # native length column (e.g. Unity CSV/.po usually don't) --
                               # set from something you actually measured, not a guess

provider:
  name: antigravity_cli   # antigravity_cli (default) | gemini -- see providers/
                          # antigravity_cli needs no separate API key if you're already
                          # signed in via `agy auth login`. gemini is an opt-in
                          # alternative (free-tier key at aistudio.google.com/apikey) --
                          # just swap this line, nothing else changes.
  model: gemini-3.7-flash # bulk-translate model
  effort: low             # low | high -- antigravity_cli only, ignored by other providers
  review_model: gemini-3.7-flash # Phase 13 repair; null falls back to `model`. Verified
                                 # (Artificial Analysis, Aug 2026): gemini-3.7-flash at
                                 # high effort scores ABOVE gemini-3.1-pro on their
                                 # Intelligence Index (56 vs 48) while costing meaningfully
                                 # less per token -- Pro isn't the automatic "stronger model"
                                 # pick anymore for this generation. escalation_model (below)
                                 # falls back to THIS if left unset, so changing review_model
                                 # also moves escalation unless you override it separately.
  review_effort: high     # low is equally valid here -- high is just the more thorough default
                          # for a low-volume QA pass
  mode: sync        # or "batch" for large non-urgent runs (50% cheaper on either provider)
  max_concurrency: 5

tm:
  db_path: tm/translation_memory.sqlite3

confidence:
  review_threshold: 0.75
  max_expansion_ratio: 1.6  # global default; a category above can override this
  tier1_repair_attempts: 2  # deterministic-validation failures get this many cheap
                            # retries through the bulk-translate call (with the
                            # validator's own message attached) before falling
                            # through to the expensive review agent. 0 disables this.
"""


def cmd_init(args: argparse.Namespace) -> int:
    root = Path("projects") / args.name
    if root.exists():
        print(f"projects/{args.name} already exists.", file=sys.stderr)
        return 1
    (root / "batches").mkdir(parents=True)
    (root / "resources").mkdir(parents=True)
    (root / "project.yaml").write_text(_INIT_TEMPLATE.format(name=args.name), encoding="utf-8")
    for fname, header in [
        ("glossary.md", "# Glossary\n\n| Source term | Target translation | Category | Confidence | Source/justification |\n|---|---|---|---|---|\n"),
        ("lang-style.md", "# Language style guide\n"),
        ("character-voices.md", "# Character voice bible\n\n| Character | Register | Traits | Avoid |\n|---|---|---|---|\n"),
        ("anti-fabrication-checklist.md", "# Anti-fabrication checklist\n"),
    ]:
        (root / "resources" / fname).write_text(header, encoding="utf-8")
    print(f"Created projects/{args.name}/. Edit project.yaml, drop batch files in batches/, then:")
    print(f"  locpipe plan --project projects/{args.name}   # check the numbers first")
    print(f"  locpipe run --project projects/{args.name}")
    return 0


def _build_provider(
    config,
    dry_run: bool,
    pseudo_loc: bool = False,
    model_override: str | None = None,
    effort_override: str | None = None,
):
    if pseudo_loc:
        from .providers.pseudoloc import PseudoLocProvider

        return PseudoLocProvider()

    if dry_run:
        from .providers.mock import MockProvider

        return MockProvider()

    name = config.provider.name
    model = model_override or config.provider.model
    if name == "antigravity_cli":
        from .providers.antigravity_cli_provider import AntigravityCLIProvider

        return AntigravityCLIProvider(
            model=model,
            max_concurrency=config.provider.max_concurrency,
            timeout_s=config.provider.sync_call_timeout_s,
            effort=effort_override or config.provider.effort,
        )
    raise ValueError(f"Unsupported provider.name '{name}' in project.yaml (only antigravity_cli is supported)")


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_project(args.project)
    limit = args.limit or args.sample
    result = plan(config, limit_batches=limit)

    print("=== PRE-FLIGHT PLAN & TOKEN ESTIMATE ===")
    print(f"  Project:                      {config.project}")
    print(f"  Provider & Model:             {config.provider.name} ({config.provider.model}, effort: {config.provider.effort})")
    print(f"  Pending Batch Files:          {result.get('pending_files_count', 0):,}")
    print(f"  Total Scanned Entries:        {result['total_entries']:,}")
    print(f"  Already Translated in Source: {result['already_translated']:,}")
    print(f"  Filled from TM (0 LLM Calls):  {result['tm_hits']:,}")
    print(f"  Unique Strings to Translate:  {result['unique_strings_needing_translation']:,}")
    print(f"  LLM Calls Needed:             {result['llm_calls_needed']:,}")
    for cat, n in sorted(result["calls_by_category"].items()):
        print(f"    - {cat}: {n} call(s)")
    print()
    print("Token Estimates (Heuristic char/4 calculation):")
    print(f"  Estimated Input Tokens (caching-optimistic): ~{result['estimated_uncached_input_tokens']:,}")
    print(f"  Estimated System Prompt Tokens (cached):    ~{result['estimated_cache_read_tokens']:,} (reused across {result['llm_calls_needed']} calls)")
    if "estimated_realistic_input_tokens" in result:
        print(f"  Estimated Realistic Input Tokens (no-cache): ~{result['estimated_realistic_input_tokens']:,}")
    print(f"  Estimated Target Output Tokens:              ~{result['estimated_output_tokens']:,}")
    print()
    if result.get("caching_note"):
        print(f"Note: {result['caching_note']}")
    else:
        print("Note: Gemini models automatically cache long context prompts.")
    print("Check current per-token pricing at ai.google.dev/pricing before sizing your billing expectations.")
    print("=======================================")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    config = load_project(args.project)
    report = run_audit(config)
    markdown = render_report_markdown(report, config.project)

    out_path = Path(args.out) if args.out else config.root / "audit_report.md"
    out_path.write_text(markdown, encoding="utf-8")

    if not report["supported"]:
        print(f"'{config.format}' doesn't support extraction auditing yet -- see {out_path} for details.")
        return 0

    reasons = report["reason_counts"]
    kept = reasons.get("kept", 0)
    excluded = reasons.get("excluded_by_config", 0)
    noise_total = sum(v for k, v in reasons.items() if k.startswith("noise:"))
    print(f"Scanned {report['files_scanned']} file(s).")
    print(f"  kept (would be sent to the LLM):        {kept}")
    print(f"  filtered as engine noise (built-in):    {noise_total}")
    print(f"  filtered by uabea_json_path_exclude:    {excluded}")
    if report["files_failed"]:
        print(f"  files that failed to parse (skipped):   {len(report['files_failed'])}")
    print(f"Full breakdown by asset/path: {out_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_project(args.project)
    limit = args.limit or args.sample
    pseudo_loc = getattr(args, "pseudo_loc", False)

    # Pre-flight report (Phase 10)
    mode_str = "PSEUDO-LOC (PseudoLocProvider)" if pseudo_loc else ("DRY-RUN (MockProvider)" if args.dry_run else config.provider.mode)
    print("=== PRE-FLIGHT TRANSLATION REPORT ===")
    print(f"  Project:        {config.project}")
    print(f"  Source -> Target: {config.source_lang} -> {config.target_lang}")
    print(f"  Format:         {config.format}")
    print(f"  Provider:       {config.provider.name} (model: {config.provider.model}, effort: {config.provider.effort})")
    print(f"  Mode:           {mode_str}")
    if args.max_api_calls:
        print(f"  Safety Budget:  Max {args.max_api_calls} API call(s)")
    if limit:
        print(f"  File Limit:     Only processing first {limit} file(s)")
    print("=====================================")
    print()

    provider = _build_provider(config, args.dry_run, pseudo_loc=pseudo_loc)

    review_model = config.provider.review_model or config.provider.model
    review_effort = config.provider.review_effort or "high"
    review_provider = _build_provider(
        config,
        args.dry_run,
        pseudo_loc=pseudo_loc,
        model_override=review_model,
        effort_override=review_effort,
    )

    escalation_model = config.provider.escalation_model or review_model
    escalation_effort = config.provider.escalation_effort or "high"
    escalation_provider = _build_provider(
        config,
        args.dry_run,
        pseudo_loc=pseudo_loc,
        model_override=escalation_model,
        effort_override=escalation_effort,
    )

    stats = run(
        config,
        provider,
        review_provider=review_provider,
        escalation_provider=escalation_provider,
        limit_batches=limit,
        max_api_calls=args.max_api_calls,
    )
    print(stats.summary())
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    config = load_project(args.project)
    adapter = get_adapter(config.format, config.format_options)

    snapshot_dir = config.root / "tm" / "pre_merge_snapshots"
    if not snapshot_dir.exists() or not any(snapshot_dir.iterdir()):
        print("=== POST-RUN INTEGRITY VERIFICATION ===")
        print(f"  Project: {config.project}")
        print()
        print("  [ERROR] No pre-merge snapshots found in 'tm/pre_merge_snapshots'.")
        print("  Verification requires snapshots created before merge during 'locpipe run'.")
        print("  Historical runs completed prior to snapshot support cannot be retroactively verified.")
        print("=======================================")
        return 1

    import inspect
    supports_sink = "audit_sink" in inspect.signature(adapter.extract).parameters

    if not supports_sink:
        print("=== POST-RUN INTEGRITY VERIFICATION ===")
        print(f"  Project: {config.project}")
        print(f"  Format '{config.format}' does not support extraction classification auditing.")
        print("=======================================")
        return 0

    batch_files = config.batch_files
    files_verified = 0
    clean_untouched_count = 0
    kept_changed_count = 0
    kept_unchanged_count = 0
    anomalies: list[dict[str, Any]] = []

    for path in batch_files:
        snapshot_file = snapshot_dir / path.name
        if not snapshot_file.exists():
            continue

        snap_sink: list[tuple[str, str, str]] = []
        try:
            adapter.extract(snapshot_file, audit_sink=snap_sink)
        except Exception as e:
            anomalies.append({
                "file": path.name,
                "path": "<file-level>",
                "action": "parse_error",
                "expected": f"Valid snapshot {snapshot_file.name}",
                "actual": f"Snapshot extraction error: {e}",
            })
            continue

        curr_sink: list[tuple[str, str, str]] = []
        try:
            adapter.extract(path, audit_sink=curr_sink)
        except Exception as e:
            anomalies.append({
                "file": path.name,
                "path": "<file-level>",
                "action": "parse_error",
                "expected": f"Valid merged file {path.name}",
                "actual": f"Current file extraction error: {e}",
            })
            continue

        curr_values = {json_path: val for json_path, val, _ in curr_sink}
        files_verified += 1

        for json_path, orig_val, action in snap_sink:
            curr_val = curr_values.get(json_path)

            if action.startswith("noise:") or action == "excluded_by_config":
                if curr_val != orig_val:
                    anomalies.append({
                        "file": path.name,
                        "path": json_path,
                        "action": action,
                        "expected": orig_val,
                        "actual": curr_val,
                    })
                else:
                    clean_untouched_count += 1
            elif action == "kept":
                if curr_val != orig_val:
                    kept_changed_count += 1
                else:
                    kept_unchanged_count += 1

    print("=== POST-RUN INTEGRITY VERIFICATION ===")
    print(f"  Project:                               {config.project}")
    print(f"  Batch Files Verified:                  {files_verified}")
    print(f"  Untouched Noise / Excluded Strings:    {clean_untouched_count} (100% verified clean)")
    print(f"  Translated Kept Strings Modified:      {kept_changed_count}")
    if kept_unchanged_count > 0:
        print(f"  Kept Strings Unchanged:                {kept_unchanged_count}")
    print(f"  Anomalies Found:                       {len(anomalies)}")

    if anomalies:
        print("\n--- ANOMALIES DETECTED ---")
        for a in anomalies:
            print(f"  • [{a['file']}] {a['path']}")
            print(f"      Classification:   {a['action']}")
            print(f"      Pre-merge Value:  {a['expected']!r}")
            print(f"      Post-merge Value: {a['actual']!r}")
        print("=======================================")
        return 1

    print("  Status: All noise and excluded paths remained perfectly untouched.")
    print("=======================================")
    return 0


def cmd_tm_invalidate(args: argparse.Namespace) -> int:
    config = load_project(args.project)
    from .tm import TranslationMemory
    from .normalize import content_hash, normalize_source

    tm = TranslationMemory(config.tm_db_path)
    try:
        raw_key = args.key
        deleted = tm.invalidate(raw_key)
        if not deleted:
            h = content_hash(normalize_source(raw_key))
            deleted = tm.invalidate(h)

        if deleted:
            print(f"✅ Successfully invalidated TM entry for '{raw_key}' in {config.project}.")
            return 0
        else:
            print(f"⚠ No matching TM entry found for '{raw_key}' in {config.project}.", file=sys.stderr)
            return 1
    finally:
        tm.close()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="locpipe")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold a new project under projects/<name>/")
    p_init.add_argument("name")
    p_init.set_defaults(func=cmd_init)

    p_plan = sub.add_parser("plan", help="read-only: dedup/batch/token estimate, no LLM calls, no writes")
    p_plan.add_argument("--project", required=True, help="path to the project directory")
    p_plan.add_argument("--limit", type=int, default=None, help="only scan the first N batch files")
    p_plan.add_argument("--sample", type=int, default=None, help="alias for --limit")
    p_plan.set_defaults(func=cmd_plan)

    p_audit = sub.add_parser(
        "audit",
        help="read-only: report what extraction would keep vs. filter as engine noise (uabea_json only, for now), no LLM calls, no writes",
    )
    p_audit.add_argument("--project", required=True, help="path to the project directory")
    p_audit.add_argument("--out", default=None, help="report path (default: <project>/audit_report.md)")
    p_audit.set_defaults(func=cmd_audit)

    p_verify = sub.add_parser(
        "verify",
        help="post-run integrity verification: diffs merged batch files against pre-merge snapshots to prove noise/excluded paths were untouched",
    )
    p_verify.add_argument("--project", required=True, help="path to the project directory")
    p_verify.set_defaults(func=cmd_verify)

    p_run = sub.add_parser("run", help="run the pipeline for a project")
    p_run.add_argument("--project", required=True, help="path to the project directory")
    p_run.add_argument("--dry-run", action="store_true", help="use the mock provider, no API calls")
    p_run.add_argument("--pseudo-loc", action="store_true", help="run deterministic pseudo-localization with ~30% expansion and accented glyphs, no API calls")
    p_run.add_argument("--limit", type=int, default=None, help="only process the first N batch files")
    p_run.add_argument("--sample", type=int, default=None, help="alias for --limit")
    p_run.add_argument("--max-api-calls", type=int, default=None, help="hard ceiling on total LLM API completion requests")
    p_run.set_defaults(func=cmd_run)

    p_inv = sub.add_parser("tm-invalidate", help="invalidate a TM entry to force retranslation on next run")
    p_inv.add_argument("--project", required=True, help="path to the project directory")
    p_inv.add_argument("--key", required=True, help="source string or content hash to invalidate")
    p_inv.set_defaults(func=cmd_tm_invalidate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
