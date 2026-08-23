# AGENTS.md — GameStringer & LocPipe Instruction Guide for AI Agents

Welcome, Agent. This repository contains **GameStringer** (GUI & core translation tools) and **LocPipe** (a deterministic, LLM-powered video game localization pipeline).

When working on game translation projects or running localization pipelines, follow this guide strictly.

---

## 1. Primary Reference
The authoritative, complete manual for all project setup, configuration fields, and CLI commands is:
👉 `locpipe/HASZNALAT.md`

Whenever you need exact field definitions or commands, consult `locpipe/HASZNALAT.md` first.

---

## 2. Standard Staged Workflow for Agents

When a user asks you to translate or verify a game project under `locpipe/projects/<Project Name>/`:

### Step 1: Validate `project.yaml` & Resources
1. **Format:** Verify that `format` (e.g. `uabea_json`, `unity`, `generic_kv`, `po_gettext`) matches the actual file structure inside `batches/`.
2. **Provider:** Ensure `provider.name: antigravity_cli`, `model: gemini-3.7-flash` (effort: `low`), and `review_model: gemini-3.7-flash` (effort: `high`).
3. **Register:** Set `target_register: informal` (tegeződés, standard for gaming).
4. **Style Guide (`resources/lang-style.md`):** Ensure it is NOT empty. Apply one of the 4 standard presets from `locpipe/src/locpipe/presets.py`:
   - `Modern, laza` (action / adventure)
   - `Fantasy/archaikus` (RPGs / fantasy)
   - `Semleges/technikai` (simulators / UI-heavy)
   - `Humoros/ironikus` (comedy / parody / stylized action)
5. **Anti-Fabrication (`resources/anti-fabrication-checklist.md`):** Ensure standard anti-fabrication rules are present.
6. **Batch Size:** Keep `batch_size: 200` (default) for fast calls and zero token-truncation retries.

### Step 2: Run Audit (Zero Cost)
Always run `locpipe audit` before calling any LLMs to check classification:
```bash
locpipe audit --project "locpipe/projects/<Project Name>"
```
- Review the kept vs noise breakdown.
- Ensure no game dialogue/UI strings are mistakenly caught in noise filters.

### Step 3: Staged Test Run (Mandatory Checkpoint)
**Never jump directly into a full unattended run on a new or modified project.**
Always run a small, bounded test first:
```bash
locpipe run --project "locpipe/projects/<Project Name>" --limit 1 --max-api-calls 20
```
- Report the results to the user with sample translated lines (Source → Target).
- Confirm control codes and tags (`{0}`, `%s`, `<ctrl:...>`, etc.) are preserved.
- **STOP and wait for the user's explicit go-ahead** before running the full project.

### Step 4: Full Project Run
Once approved by the user, execute the full run:
```bash
locpipe run --project "locpipe/projects/<Project Name>"
```

### Step 5: Post-Run Inspection
Verify the output:
- Check `batches/` files (target strings filled).
- Check `review/full_bilingual_report.md` (complete translation table).
- Check `review/review_report.md` (flagged items needing attention).
- Check `tm/translation_memory.sqlite3` stats.

---

## 3. Strict Safety & DMCA Rules
- **Never push game assets / dumps to git:** All `projects/`, `locpipe/projects/`, and `*.sqlite3` databases are gitignored to prevent DMCA violations.
- **Always quote paths:** Folder names often contain spaces (e.g. `"locpipe/projects/Bayonetta PC"`).
- **Preserve format metadata:** Never alter raw files inside `batches/` by hand; always let the pipeline adapters handle extraction and merging.
