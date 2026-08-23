---
name: locpipe-workflow
description: >-
  Step-by-step workflow guide and operational runbook for configuring, auditing,
  testing, and executing game translations in GameStringer and LocPipe.
---

# LocPipe Translation Workflow Runbook

When the user asks to translate, test, audit, or verify a game localization project in LocPipe:

## 1. Reference Manual
The complete documentation is located at `locpipe/HASZNALAT.md`.

## 2. Standard Workflow Checklist
1. **Config Verification**: Inspect `locpipe/projects/<Game Name>/project.yaml`.
   - `format`: Must match the JSON/CSV adapter (`uabea_json`, `unity`, `generic_kv`, `po_gettext`).
   - `provider.name`: `antigravity_cli` with `gemini-3.7-flash` (bulk: `low`, review: `high`).
   - `target_register`: `informal` (tegeződés).
   - `resources/lang-style.md`: Apply one of the 4 presets from `locpipe/src/locpipe/presets.py`.
   - `resources/anti-fabrication-checklist.md`: Ensure standard rules are present.
2. **Audit Check**: Run `locpipe audit --project "locpipe/projects/<Game Name>"` (0 cost). Check kept vs noise strings.
3. **Staged Test Run**: Run `locpipe run --project "locpipe/projects/<Game Name>" --limit 1 --max-api-calls 20`.
   - Inspect sample translated lines.
   - Confirm tag & control code preservation.
   - **STOP** and report to the user for go-ahead.
4. **Full Execution**: On approval, run `locpipe run --project "locpipe/projects/<Game Name>"`.
5. **Output Check**: Inspect `batches/`, `review/full_bilingual_report.md`, and `tm/translation_memory.sqlite3`.
