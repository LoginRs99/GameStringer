# GameStringer CLI — Session Context

> Másold be ezt az új AI session első üzeneteként, hogy a kontextus megmaradjon.

---

## 🎯 Projekt Cél

A [GameStringer](https://github.com/LoginRs99/GameStringer) Tauri desktop appjából épített **standalone Python CLI tool**, ami csak játékszöveget nyer ki és patchel vissza. Nincs benne AI fordítás, UI, vagy library scanner.

---

## ✅ Kész Engine-ek (5 db)

| Engine | Fájlok | Státusz |
|--------|--------|---------|
| **unity** | `.assets`, `.bundle` | Unity Mono — StringTable, SharedTableData, TextAsset (UnityPy) |
| **il2cpp** | `GameAssembly.dll`, `global-metadata.dat` | Unity IL2CPP Hybrid — asset + metadata + XUnity pre-trans |
| **unreal** | `.locres` | Unreal 4/5 bináris .locres (v0–v3) |
| **renpy** | `.rpy`, `.rpa` | Ren'Py — dialógus, narration, `translate <lang>` blokk |
| **cri** | `.msg`, `.bmd`, `.ftd`, `.cpk` | CRI Middleware — Shift-JIS, UTF-8, UTF-16 |

---

## ✅ Kész Feature-ök

- **XLIFF 1.2** elsődleges kimenet, **PO** fallback
- **NFC Unicode normalizálás** (ő/ű kezelése)
- **Dry-run**, **validate**, **batch**, **update/diff**
- **Backup** minden patch előtt
- **Corrupt file skip** + **Smart String token check** + **exit codes**
- **IL2CppDumper** auto-detect + fallback pure-Python metadata reader
- **Metadata garbage filter**: 375k nyers → ~14k szűrt sztring
- **Unity scanner fejlesztések**: 300MB limit, fast header scanner, C# type ref filter, UTF-16 surrogate protection
- **Tkinter GUI** (`gamestringer-gui`) — browse, auto-detect, progress bar, real-time log

---

## 🚀 CLI Parancsok

```bash
gamestringer detect --input <path>
gamestringer extract --engine <unity|il2cpp|unreal|renpy|cri> --input <path> --output <xliff>
gamestringer patch --engine <name> --input <path> --xliff <xliff> --output <path>
gamestringer validate --xliff <path>
gamestringer update --input <path> --old-xliff <path> --output <path>
gamestringer batch --config <json>
gamestringer setup-il2cppdumper
gamestringer-gui  # Tkinter GUI
```

---

## 🎮 Tesztelt Játékok

| Játék | Engine | Sztringek | Eredmény |
|-------|--------|-----------|----------|
| **Children of Morta** | Unity Mono | ~50k–134k | ✅ Extract + Patch OK |
| **Sunderfolk** | Unity IL2CPP | ~14k–31k (filtered) | ✅ IL2CppDumper + fallback OK |

---

## 🔧 Architektúra

```
gamestringer_cli/
├── gamestringer/
│   ├── cli.py / gui.py
│   ├── core/          # base_engine, xliff_exporter, po_exporter, backup
│   └── engines/       # unity_mono, il2cpp_hybrid, unreal, renpy, cri
├── tests/test_cli.py
└── pyproject.toml
```

**CLI = buta kinyerő/visszaíró.** Fordítás és nyelvszűrés a különálló pipeline feladata.

---

## ⚠️ Fontos Limitációk

- **UE3** nem támogatott (más formátum)
- **IL2CPP** kódsztringekhez XUnity.AutoTranslator + BepInEx 6 IL2CPP kell (pre-trans generálás működik)
- **AES titkosított .pak** Unreal-nél előbb ki kell nyerni
- **Anti-cheat** (EAC/BattlEye/Vanguard) tiltja — csak single-player!

---

## 📦 Telepítés

```bash
cd gamestringer_cli
pip install -e .
gamestringer-gui
```

---

## 🔗 Eredeti Repo

https://github.com/LoginRs99/GameStringer
