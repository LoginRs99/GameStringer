# GameStringer CLI — Session Context

> Paste this into new AI sessions to maintain context.

## Project Goal
Standalone Python CLI tool for extracting and repatching game text.
Forked from GameStringer Tauri app — stripped to extraction/patch pipeline only.
No AI translation, no UI library scanner, no Tauri/Rust.

## Supported Engines (5)
| Engine | Files | Status |
|--------|-------|--------|
| unity | .assets, .bundle | Unity Mono — StringTable, SharedTableData, TextAsset |
| il2cpp | GameAssembly.dll, global-metadata.dat | Hybrid — assets + metadata + XUnity pre-trans |
| unreal | .locres | Unreal 4/5 binary .locres (v0–v3) |
| renpy | .rpy, .rpa | Visual Novel — dialogue, translate blocks |
| cri | .msg, .bmd, .ftd, .cpk | CRI Middleware — Persona, Yakuza, Tales of |

## Core Features
- XLIFF 1.2 primary output, PO fallback
- NFC Unicode normalization (critical for Hungarian ő/ű)
- Dry-run, validate, batch, update/diff
- Backup before every patch
- Corrupt file skip + Smart String token check + exit codes
- IL2CppDumper auto-detect + pure-Python fallback
- Metadata garbage filter: 375k raw → ~14k filtered strings
- Unity scanner: 300MB file limit, fast header scanner, C# type ref filter, UTF-16 surrogate protection

## Quality Assurance Features
- `check-quotes` — quote consistency between source/target
- `check-fonts` — Hungarian ő/ű glyph support detection
- `fix-catalog` — Addressables CRC32 recalculation after patch

## CLI Commands
```bash
gamestringer detect --input <path>
gamestringer extract --engine <name> --input <path> --output <xliff>
gamestringer patch --engine <name> --input <path> --xliff <path> --output <path>
gamestringer validate --xliff <path>
gamestringer update --input <path> --old-xliff <path> --output <path>
gamestringer batch --config <json>
gamestringer check-quotes --xliff <path>
gamestringer check-fonts --input <path> --engine <name>
gamestringer fix-catalog --input <path>
gamestringer setup-il2cppdumper
gamestringer-gui  # Tkinter GUI
```

## Tested Games
| Game | Engine | Strings | Result |
|------|--------|---------|--------|
| Children of Morta | Unity Mono | ~50k–134k | ✅ Extract + Patch OK |
| Sunderfolk | Unity IL2CPP | ~14k–31k filtered | ✅ IL2CppDumper + fallback OK |

## Architecture
```
gamestringer_cli/
├── gamestringer/
│   ├── cli.py / gui.py
│   ├── core/          # base_engine, xliff_exporter, po_exporter, backup
│   ├── engines/       # unity_mono, il2cpp_hybrid, unreal, renpy, cri
│   └── qa/            # quote_checker, font_checker, addressables_crc
├── tests/test_cli.py
└── pyproject.toml
```

## Pipeline Integration
CLI = dumb extractor/injector. Translation and language filtering handled by separate pipeline.

## Known Limitations
- UE3 not supported (.upk, .int)
- IL2CPP code strings need XUnity.AutoTranslator + BepInEx 6 IL2CPP
- AES-encrypted .pak needs manual extraction first (UnrealPak/QuickBMS)
- Anti-cheat (EAC/BattlEye/Vanguard) blocks modifications — single-player only

## Install
```bash
cd gamestringer_cli
pip install -e .
gamestringer-gui
```
