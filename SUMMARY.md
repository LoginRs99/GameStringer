# GameStringer — Context & Session Summary

> Paste this into new AI sessions to maintain project context.

## Project Scope
Unified localization pipeline and desktop preflight GUI (`gamestringer-gui`) wrapping the `locpipe` translation engine with **Google Antigravity CLI** (`gemini-3.7-flash`) as the sole LLM provider.

- **No Game Binary Parsing**: Binary extraction is an external, manual step (UABEA for Unity, Unreal Localization Dashboard for Unreal).
- **Sole LLM Provider**: `antigravity_cli` (Gemini 3.7 Flash). Non-Antigravity providers are rejected at config load time. Subprocess calls are hardened with timeout, backoff retry, and stderr logging.
- **Tkinter GUI (`gamestringer-gui`)**: 4 focused tabs: Projects, Preflight, Audit, Run.
- **Engine-Independent Utilities**: Hungarian font glyph checker (`font_checker.py`, Unity/IL2CPP only) and Unity Addressables CRC fixer (`addressables_crc.py`).

## Supported Localization Adapters in LocPipe
| Format Adapter | Source Engine / Export Tool | Notes |
|---|---|---|
| `uabea_json` | Unity (UABEA export) | Supports CSV-in-m_Script and typetree object graph with noise filtering & path excludes |
| `unity` | Unity Localization Package | Official Unity Localization CSV tables |
| `po_gettext` / `ue4_5_po` | Unreal Engine Localization Dashboard | Standard PO format and Unreal plural/gender syntax |
| `generic_kv` | JSON / Key-Value localization dumps | Generic dictionary maps |
| `xliff` / `weblate_xliff` | Standard XLIFF 1.2 CAT tool files | Full trans-unit support |

## GUI & CLI Commands
```bash
# GUI Launch
gamestringer-gui

# GameStringer Preflight & Post-Patch CLI
gamestringer check-fonts --input <game_path> --engine <unity|il2cpp>
gamestringer fix-catalog --input <game_path>

# LocPipe CLI
locpipe init <project_name>
locpipe plan --project <project_path>
locpipe audit --project <project_path>
locpipe run --project <project_path>
```

## Standard Per-Game Workflow
1. **Extract**: Export text with UABEA (Unity) or Localization Dashboard (Unreal) into `locpipe/projects/<name>/batches/`.
2. **Configure**: Scaffold and edit `project.yaml` via Projects Tab.
3. **Preflight**: Verify font glyph support and audit extraction noise via Preflight & Audit Tabs.
4. **Plan**: Run `locpipe plan` to preview deduplication ratio and token estimates (0 API cost).
5. **Translate**: Run `locpipe run` with Antigravity CLI (`gemini-3.7-flash`).
6. **Reimport**: Reimport translated files back into the game, then run `fix-catalog` if Unity IL2CPP.
