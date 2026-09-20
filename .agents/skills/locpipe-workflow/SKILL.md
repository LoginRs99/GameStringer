---
name: locpipe-workflow
description: >-
  Step-by-step workflow guide and operational runbook for configuring, auditing,
  testing, and executing game and software translations in GameStringer and LocPipe.
---

# LocPipe Translation Workflow Runbook

When the user asks to translate, test, audit, or verify a game or software localization project in LocPipe:

## 1. Reference Manual
The authoritative documentation is located at `locpipe/HASZNALAT.md`.

## 2. Standard Workflow Checklist
1. **Config Verification**: Inspect `projects/<Name>/project.yaml`.
   - `project_type`: `game` or `software`.
   - `source_lang` and `target_lang`: Any pair supported (e.g. `en`, `ja`, `hu`, `de`, `fr`, `es`).
   - `format`: Must match the input format (`generic_kv`, `uabea_json`, `unity`, `po_gettext`, `ue4_5_po`, `xliff`).
   - `provider.name`: `antigravity_cli` with `gemini-3.8-flash` (bulk: `low`, review: `high`, max_concurrency: `2`).
   - `target_register`: `informal` (direct/tegezés) or `formal` (udvarias/magázás).
   - `resources/lang-style.md`: Apply appropriate preset from `locpipe/src/locpipe/presets.py`:
     - **Game:** `Modern, laza` | `Fantasy/archaikus` | `Semleges/technikai` | `Humoros/ironikus`
     - **Software:** `Szoftver UI / Asztali alkalmazás` | `Szoftver Műszaki / Dokumentáció` | `Szoftver Eszköz / CLI & Fejlesztői`
   - `resources/anti-fabrication-checklist.md`: Ensure standard anti-fabrication rules are present.
2. **Audit Check**: Run `locpipe audit --project "projects/<Name>"` (0 cost). Check kept vs noise strings and exclude engine junk.
3. **Staged Test Run**: Run `locpipe run --project "projects/<Name>" --limit 1 --max-api-calls 20`.
   - Inspect sample translated lines.
   - Confirm control codes (`\C[#]`, `\V[#]`, `\n`, `\t`), ruby tags, gender slots, access keys (`&File`), and shortcuts (`Ctrl+S`) are preserved.
   - Confirm physical `max_length` limits are respected.
   - **STOP** and report to the user for go-ahead.
4. **Full Execution**: On approval, **direct the user to execute the full run in an external PowerShell terminal** (`locpipe run --project "projects/<Name>"`). Do NOT run full unattended multi-batch jobs directly inside the agent runner to avoid flooding IDE conversation histories.
5. **Output Check**: Inspect `batches/`, `review/full_bilingual_report.md`, and `tm/translation_memory.sqlite3`.

