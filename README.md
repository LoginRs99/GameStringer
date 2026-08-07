# GameStringer CLI

> **Standalone Python CLI tool** játékszöveg kinyerésére és visszapattintására több játékengine-ből.
> Forkolva a [GameStringer](https://github.com/LoginRs99/GameStringer) Tauri appból — lecsupaszítva csak a kinyerés/visszaírás pipeline-ra.

---

## 🎯 Mit csinál?

A GameStringer CLI **kinyeri a játékok szöveges tartalmát** (dialógus, UI, menü, quest szövegek) és **XLIFF 1.2** formátumba exportálja. A lefordított XLIFF-et később **vissza is írja** az eredeti játékfájlokba.

- ❌ **Nincs benne:** AI fordítás, grafikus játék library, Tauri/Rust, web UI
- ✅ **Van benne:** 5 engine támogatás, XLIFF/PO export, automatikus backup, dry-run, batch mód, Tkinter GUI

---

## 🎮 Támogatott Engine-ek

| Engine | Fájlok | Státusz | Leírás |
|--------|--------|---------|--------|
| **`unity`** | `.assets`, `.bundle` | ✅ Kész | Unity Mono — StringTable, SharedTableData, TextAsset (UnityPy) |
| **`il2cpp`** | `GameAssembly.dll`, `global-metadata.dat` | ✅ Kész | Unity IL2CPP Hybrid — asset kinyerés + metadata stringek + XUnity pre-trans |
| **`unreal`** | `.locres` | ✅ Kész | Unreal Engine 4/5 bináris `.locres` táblák (v0–v3) |
| **`renpy`** | `.rpy`, `.rpa`, `game/` | ✅ Kész | Ren'Py Visual Novel — dialógus, narration, `translate <lang>` blokk generálás |
| **`cri`** | `.msg`, `.bmd`, `.ftd`, `.cpk` | ✅ Kész | CRI Middleware — Persona, Yakuza, Tales of (Shift-JIS, UTF-8, UTF-16) |

---

## 📦 Telepítés

```bash
# Repo klónozása
git clone https://github.com/LoginRs99/GameStringer.git
cd GameStringer/gamestringer_cli

# Telepítés pip-pel (fejlesztői mód)
pip install -e .

# GUI indítása
gamestringer-gui
```

### Függőségek

- Python 3.11+
- `click` vagy `typer` (CLI)
- `lxml` (XLIFF kezelés)
- `UnityPy` (Unity asset parsolás)
- `polib` (PO export)
- Opcionális: `IL2CppDumper` (IL2CPP metadata kinyeréshez)

---

## 🚀 Gyorsindítás

### 1. Engine detektálás

```bash
gamestringer detect --input "/path/to/game"
```

### 2. Szöveg kinyerése XLIFF-be

```bash
# Unity Mono játék
gamestringer extract --engine unity --input "/path/to/unity_game" --output game.xliff

# Unreal Engine
gamestringer extract --engine unreal --input "Game.locres" --output game.xliff

# Ren'Py
gamestringer extract --engine renpy --input "/path/to/renpy_game" --output game.xliff

# IL2CPP (auto-detect IL2CppDumper-rel)
gamestringer extract --engine il2cpp --input "/path/to/il2cpp_game" --output game.xliff --il2cppdumper-path "C:/Tools/IL2CppDumper/IL2CppDumper.exe"
```

### 3. XLIFF lefordítása

A pipeline-od vagy CAT tool-od (OmegaT, memoQ, stb.) lefordítja az XLIFF-et. A `<target>` mezőkbe kerül a fordítás.

### 4. Visszapattintás

```bash
# Unity Mono — in-place patch backup-kel
gamestringer patch --engine unity --input "/path/to/unity_game" --xliff game_hu.xliff --output game_patched

# Ren'Py — `game/tl/hu/` mappa generálás
gamestringer patch --engine renpy --input "/path/to/renpy_game" --xliff game_hu.xliff

# IL2CPP — asset patch + XUnity pre-trans fájl generálás
gamestringer patch --engine il2cpp --input "/path/to/il2cpp_game" --xliff game_hu.xliff --output game_patched
```

---

## 🖥️ Tkinter GUI

```bash
gamestringer-gui
```

A GUI a CLI köré épült wrapper:
- **Browse** gombok mappa/fájl kiválasztáshoz
- **Auto-detect** engine felismerés
- **Dry-run** mód — kinyerés szimulálása fájlírás nélkül
- **Progress bar** + real-time log ablak
- **Open XLIFF** / **Open Folder** gombok
- Beállítások mentése (`%APPDATA%/GameStringer/gui_settings.json`)

---

## 🛠️ CLI Parancsok

| Parancs | Leírás |
|---------|--------|
| `detect` | Engine auto-detektálás |
| `extract` | Szöveg kinyerése XLIFF-be |
| `patch` | Fordított XLIFF visszaírása |
| `validate` | XLIFF ellenőrzés — untranslated count, token mismatch |
| `update` | Diff mód Steam patch után (csak új/módosult sztringek) |
| `batch` | Több játék feldolgozása JSON config alapján |
| `setup-il2cppdumper` | IL2CppDumper keresése/beállítása |
| `gamestringer-gui` | Tkinter GUI indítása |

### Hasznos flag-ek

```bash
--dry-run          # Szimuláció, nem ír fájlt
--verbose          # Részletes logolás
--quiet            # Csak hibák
--skip-garbage     # IL2CPP metadata szemétszűrés (ajánlott)
--il2cppdumper-path # Egyedi IL2CppDumper útvonal
```

---

## 🔧 Pipeline Integráció

A tool **exit code 0/1**-et ad vissza, így shell scriptekbe és CI pipeline-okba könnyen beépíthető:

```bash
# Bash példa
gamestringer extract --engine unity --input "$GAME_PATH" --output "$XLIFF_PATH" || exit 1

# Validálás — ha nincs 100%-os fordítás, hiba
gamestringer validate --xliff "$XLIFF_PATH" || echo "Nem minden sztring fordított!"
```

### A pipeline feladata (nem a CLI-é)

| Feladat | Ki csinálja? |
|---------|-------------|
| Szöveg kinyerése | ✅ GameStringer CLI |
| Fordítás (HU) | 🔧 A te pipeline-od / CAT tool-od |
| Nyelvszűrés (pl. csak angol) | 🔧 Pipeline |
| Visszapattintás | ✅ GameStringer CLI |
| Batch feldolgozás | ✅ Mindkettő (CLI batch vagy pipeline loop) |

---

## 🛡️ Robustness Feature-ök

- **Automatikus backup** minden patch előtt (`.bak_<timestamp>`)
- **Corrupt file skip** — egy sérült fájl nem állítja meg az egész kinyerést
- **Smart String token validáció** — figyelmeztet, ha `{0}` vagy `{player_name}` hiányzik a fordításból
- **NFC Unicode normalizálás** — kritikus magyar ékezetekhez (ő/ű)
- **300MB file size limit** — OOM védelem nagy asset bundle-öknél
- **UTF-16 surrogate protection** — nem crashel furcsa Unicode karaktereknél
- **C# Type Reference szűrés** — `AssemblyQualifiedName` és namespace szemét kiszűrése
- **IL2CPP metadata garbage filter** — 375k nyers sztring → ~14k valódi sztring

---

## 🎮 Tesztelt Játékok

| Játék | Engine | Sztringek | Státusz |
|-------|--------|-----------|---------|
| **Children of Morta** | Unity Mono | ~50k–134k | ✅ Extract + Patch OK |
| **Sunderfolk** | Unity IL2CPP | ~14k–31k (filtered) | ✅ IL2CppDumper + fallback OK |

---

## 📁 Projekt Struktúra

```
gamestringer_cli/
├── gamestringer/
│   ├── cli.py                 # CLI entry point (Click/Typer)
│   ├── gui.py                 # Tkinter GUI wrapper
│   ├── core/
│   │   ├── base_engine.py     # Abstract BaseEngine (detect/extract/patch)
│   │   ├── xliff_exporter.py  # XLIFF 1.2 olvasás/írás
│   │   ├── po_exporter.py     # GNU PO fallback
│   │   └── backup.py          # Backup kezelés
│   └── engines/
│       ├── unity_mono.py      # Unity Mono (UnityPy)
│       ├── il2cpp_hybrid.py   # Unity IL2CPP Hybrid
│       ├── unreal.py          # Unreal .locres bináris
│       ├── renpy.py           # Ren'Py .rpy szkriptek
│       └── cri.py             # CRI Middleware MSG/BMD/FTD
├── tests/
│   └── test_cli.py            # Unit és integration tesztek
├── pyproject.toml             # Package config + entry points
└── README.md                  # Ez a fájl
```

---

## ⚠️ Ismert Limitációk

| Limitáció | Magyarázat |
|-----------|------------|
| **UE3** | Nem támogatott (`.upk`, `.int` — teljesen más formátum) |
| **IL2CPP runtime** | A kódban lévő sztringekhez XUnity.AutoTranslator + BepInEx 6 IL2CPP kell (pre-trans fájl generálás működik) |
| **AES titkosított `.pak`** | Unreal-nél előbb ki kell nyerni a `.pak`-ot (QuickBMS / unrealpak), utána megy a tool |
| **Anti-cheat** | Csak single-player/offline játékokhoz! EAC/BattlEye/Vanguard tiltja a módosítást |

---

## 📝 License

Source-Available License v1.1 (ugyanaz, mint az eredeti GameStringer).

---

## 🙏 Eredeti Projekt

Ez a tool a [GameStringer](https://github.com/LoginRs99/GameStringer) projektből lett forkolva és lecsupaszítva. Köszönet az eredeti fejlesztőnek (Davide / @rouges78) a parser logikáért és az inspirációért.
