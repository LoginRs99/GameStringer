# GameStringer — Context & Session Summary

> Paste this into new AI sessions to maintain complete project context.

## Project Scope
Unified localization pipeline and desktop preflight GUI (`gamestringer-gui`) wrapping the `locpipe` translation engine with **Google Antigravity CLI** (`gemini-3.8-flash`) as the sole LLM provider.

- **Dual Localization Modes**: Supports both Video Game localization (`project_type: game`) with character voices/dialogue and Professional Software localization (`project_type: software`) with action verbs, menus, access keys, and dialogs.
- **Full Multilingual & Cross-Translation**: Any language pair (`ja`, `en`, `hu`, `de`, `fr`, `es`, `zh`, etc.) with language-aware register rules (informal/formal), script-aware expansion ratios, and quote balancing (Japanese corner brackets `「...」`).
- **Engine Rules & Format Protections**: Deterministic protection for control codes, escape characters (`\n`, `\r`, `\t`), RPG Maker/VN tags (`\C[#]`, `\V[#]`, `\N[#]`, etc.), Ruby markup, gender slots (`{ms|...}{fs|...}`), accelerator keys (`&File`), keyboard shortcuts (`Ctrl+S`), and strict physical `max_length` enforcement.
- **Sole LLM Provider**: `antigravity_cli` (Gemini 3.8 Flash, effort: `low` bulk, `high` review). Subprocess calls are hardened with backoff retry, stderr logging, and startup orphan DB/session sweeps.
- **Tkinter GUI (`gamestringer-gui`)**: 4 focused tabs: Projects, Preflight, Audit, Run.
- **Engine-Independent Utilities**: Hungarian font glyph checker (`font_checker.py`, Unity/IL2CPP) and Unity Addressables CRC fixer (`addressables_crc.py`).

## Supported Localization Adapters in LocPipe
| Format Adapter | Source Engine / Export Tool | Notes |
|---|---|---|
| `generic_kv` | JSON / Key-Value localization dumps | Generic dictionary maps (Universal Default) |
| `uabea_json` | Unity (UABEA export) | Supports CSV-in-m_Script and typetree object graph with noise filtering & path excludes |
| `unity` | Unity Localization Package | Official Unity Localization CSV tables |
| `po_gettext` / `ue4_5_po` | Unreal Engine Localization Dashboard / GNU gettext | Standard PO format and Unreal plural/gender syntax |
| `xliff` / `weblate_xliff` | Standard XLIFF 1.2 CAT tool files | Full trans-unit support |

## GUI & CLI Commands
```bash
# GUI Launch
gamestringer-gui

# GameStringer Preflight & Post-Patch CLI
gamestringer check-fonts --input <game_path> --engine <unity|il2cpp>
gamestringer fix-catalog --input <game_path>

# LocPipe CLI
locpipe init <project_name> [--type game|software] [--source en] [--target hu] [--format generic_kv]
locpipe plan --project <project_path>
locpipe audit --project <project_path>
locpipe run --project <project_path> [--limit N] [--max-api-calls N]
locpipe verify --project <project_path>
locpipe bootstrap-resources --project <project_path>
```

## Standard Per-Game / Software Workflow
1. **Extract**: Export text with UABEA (Unity), Localization Dashboard (Unreal), or standard JSON/PO into `projects/<name>/batches/`.
2. **Configure**: Scaffold and edit `project.yaml` via Projects Tab (NewProjectDialog) or CLI `locpipe init`.
3. **Preflight**: Verify font glyph support and audit extraction noise via Preflight & Audit Tabs.
4. **Plan**: Run `locpipe plan` to preview deduplication ratio and token estimates (0 API cost).
5. **Translate**: Run `locpipe run` with Antigravity CLI (`gemini-3.8-flash`). (Run full jobs in external PowerShell to avoid flooding IDE chats).
6. **Reimport**: Reimport translated files back into the game/software, then run `fix-catalog` if Unity IL2CPP.
