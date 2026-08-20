# GameStringer — LocPipe Desktop Preflight & Translation Manager

> **Unified Localization Pipeline & Preflight GUI** wrapping the `locpipe` deterministic translation engine with **Google Antigravity CLI** (`gemini-3.7-flash`) as the sole LLM provider.

---

## 🎯 Architecture & Scope

GameStringer consolidates game localization into a clean, deterministic pipeline:
- **No binary parsing / extraction inside this tool**: Game-file extraction and reimporting is done externally via standard community tools (e.g. **UABEA** for Unity asset dumps, **Unreal Localization Dashboard** PO export for Unreal Engine).
- **Sole LLM Provider**: Hardened Antigravity CLI (`agy --print`) integration with automatic retry, exponential backoff, and subprocess safety.
- **Tkinter Desktop GUI (`gamestringer-gui`)**: 4 focused tabs for managing projects, inspecting engine noise, checking font glyphs, and streaming live translations.

---

## 🔄 End-to-End Workflow

```
1. Manual Extraction (External)
   ├── Unity: UABEA JSON export (Case 1 CSV-in-m_Script or Case 2/3 typetree dump)
   └── Unreal: Localization Dashboard .po export (ue4_5_po)
           │
           ▼
2. Project Setup (`gamestringer-gui` -> Projects Tab)
   ├── Scaffold project under locpipe/projects/<name>/
   ├── Configure source_lang, target_lang, format, batch_glob
   └── Drop extracted batch files into locpipe/projects/<name>/batches/
           │
           ▼
3. Preflight & Noise Audit (Preflight & Audit Tabs)
   ├── Check Hungarian font glyph compatibility (ő/ű/Ő/Ű via check-fonts)
   └── Run non-LLM extraction audit to inspect noise & 1-click exclude junk paths
           │
           ▼
4. Plan (Run Tab)
   └── Run `locpipe plan` for dry-run deduplication, batch counts & token estimates (0 API cost)
           │
           ▼
5. Translation (Run Tab)
   └── Run `locpipe run` via Antigravity CLI (Gemini 3.7 Flash) with live log streaming
           │
           ▼
6. Reimport & Post-Patch Fix
   ├── Manually reimport translated files into the game (UABEA / Unreal)
   └── Run Catalog CRC Fixer (`gamestringer fix-catalog`) for Unity Addressables
```

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/LoginRs99/GameStringer.git
cd GameStringer

# Install in editable mode (Python 3.10+)
pip install -e .

# Launch Desktop GUI
gamestringer-gui
```

### Dependencies
- Python 3.10+
- `click>=8.0.0`
- `pyyaml>=6.0`
- `jsonschema>=4.20`
- `polib>=1.2`
- **Antigravity CLI** (`agy` on PATH, authenticated via `agy auth login`)

---

## 🖥️ Desktop GUI Tabs (`gamestringer-gui`)

1. **📁 Projects Tab**: List, scaffold, and configure `project.yaml` files (languages, format adapters, batch globs, character replacements, category rules).
2. **🔍 Preflight & Fixes Tab**: Run Hungarian font compatibility checks on Unity/IL2CPP assets and recalculate Addressables `catalog.json` CRC32 checksums.
3. **🔇 Audit Noise Tab**: Run `locpipe audit` to view translatable text vs. engine noise, and one-click append exclusion patterns to `project.yaml`.
4. **🚀 Plan & Run Tab**: Run dry pre-flight token estimates (`locpipe plan`) and execute live Antigravity CLI translation (`locpipe run`) with real-time log streaming.

---

## ⚙️ CLI Reference

### LocPipe CLI (`locpipe`)
```bash
# Scaffold a new project
locpipe init <project_name>

# Pre-flight plan and token estimate (dry run, 0 API tokens)
locpipe plan --project locpipe/projects/<project_name>

# Audit extraction noise and format excludes (no LLM calls)
locpipe audit --project locpipe/projects/<project_name>

# Run translation pipeline with Antigravity CLI
locpipe run --project locpipe/projects/<project_name>
```

### GameStringer Utilities (`gamestringer`)
```bash
# Check Unity/IL2CPP font assets for Hungarian ő/ű glyph support
gamestringer check-fonts --input "path/to/game_dir" --engine unity

# Recalculate CRC32 checksums for modified AssetBundles and update catalog.json
gamestringer fix-catalog --input "path/to/game_dir"
```

---

## 📂 Project Structure

```
GameStringer-main/
├── gamestringer/                  # GUI and standalone preflight/post-patch utilities
│   ├── cli.py                     # check-fonts & fix-catalog Click commands
│   ├── __main__.py                # CLI / GUI entry point
│   ├── core/                      # font_checker, addressables_crc, backup, quote_checker, logger
│   └── desktop_gui/               # 4-tab Tkinter GUI (app.py, theme.py, tabs/)
├── locpipe/                       # LocPipe deterministic translation engine
│   ├── pyproject.toml             # Standalone locpipe package spec
│   ├── src/locpipe/               # Pipeline, adapters (uabea_json, po, unity, xliff), providers (antigravity_cli)
│   └── tests/                     # LocPipe test suite
├── archive/                       # Archived legacy extraction scripts & test packs
├── pyproject.toml                 # Root unified package configuration
└── test_cli.py                    # GameStringer utility test suite
```
