# LocPipe — Használati útmutató & Munkafolyamat

Ez a leírás a GameStringer és LocPipe rendszer napi használatát mutatja be gyakorlati lépésekkel és konkrét parancsokkal. A rendszer felépítésének elméleti leírása a `README.md`-ben található — ez a dokumentum a gyakorlati "hogyan használd" útmutató magyar nyelven.

---

## 1. Telepítés & Előkészületek

A rendszer a Google Antigravity CLI (`agy`) motorját használja a Gemini 3.7 Flash modellel. Nincs szükség külön API kulcsok kezelésére, amennyiben a gépén már be van jelentkezve az Antigravity CLI-be.

```bash
# Repository gyökerében vagy a locpipe mappában:
pip install -e .
```

Ellenőrizd az Antigravity CLI állapotát:
```bash
agy --version
```

A grafikus kezelőfelület (GUI) indítása:
```bash
gamestringer-gui
# vagy:
python -m gamestringer.desktop_gui.app
```

---

## 2. Az Erőforrás-fájlok szerepe (resources/)

Egy projekt `resources/` mappájában 4 kulcsfontosságú Markdown fájl található. Nem szükséges mindet kézzel megírni:

| Fájl | Mi ez? | Hogyan kell kitölteni? |
|---|---|---|
| **`anti-fabrication-checklist.md`** | Hallucináció- és torzításgátló szabályok az LLM számára. | **Automatikus:** a projekt létrehozásakor készen létrejön, nem kell módosítani. |
| **`lang-style.md`** | Magyar nyelvi stílusútmutató (hangvétel, tegezés/magázás, szórend, szleng). | **Preset vagy Kézi:** A GUI Projects fülén 1 kattintással választhatsz a 4 előre beépített stíluspreset közül, vagy a `bootstrap-resources` automatikusan legenerálja. |
| **`glossary.md`** | Kötött terminológia (tulajdonnevek, skillek, tárgyak, UI gombok). | **Bootstrap vagy Kézi:** Egy kis tesztfutás után a `bootstrap-resources` automatikusan kigyűjti a TM-ből a `glossary.draft.md`-be, amit ellenőrzés után véglegesíthetsz. |
| **`character-voices.md`** | Szereplők egyedi hangneme és beszédstílusa. | **Bootstrap vagy Kézi:** Ha a játékformátum hordoz beszélő-metaadatot (`speaker`), a `bootstrap-resources` automatikusan elkészíti a `character-voices.draft.md` tervezetet. |

### Elérhető Stíluspresetek (Language Style Presets):
1. **Modern, laza (kortárs akció/kaland)** — Rövid, pergő mondatok, bevett gamer szleng megtartása (loot, buff, spawn).
2. **Fantasy/archaikus (RPG, epikus fantasy)** — Emelkedett stílus, magyarosított szakkifejezések (zsákmány, küldetés), irodalmibb mondatszerkezetek.
3. **Semleges/technikai (szimulátor, stratégia, UI-nehéz)** — Tömör, pontos, funkcionális megfogalmazások, szakzsargon megőrzése.
4. **Humoros/ironikus (comedy/paródia)** — Szabadabb fordítói mozgástér a magyar poénok és szójátékok érvényesüléséhez.

---

## 3. Ajánlott Munkafolyamat (Lépésről lépésre)

A legbiztonságosabb és legköltséghatékonyabb lokalizációs sorrend:

### 1. Lépés: Adatkinyerés (Dump)
Exportáld ki a játék szövegeit a megfelelő formátumban:
- **Unity:** UABEA JSON dump (MonoBehaviour vagy TextAsset CSV) vagy Unity Localization CSV.
- **Unreal Engine 4/5:** Localization Dashboard `.po` fájlok.
- **Egyéb:** Standard `.po` vagy egyszerű `.json` kulcs-érték párok.

### 2. Lépés: Projekt létrehozása
A **Projects** fülön kattints az **+ Új Projekt** gombra (vagy CLI-ben: `locpipe init JatekNev`).
- Állítsd be a formátumot (pl. `uabea_json`, `ue4_5_po`).
- Válaszd ki a kívánt **Language Style Preset**-et.
- Másold be a kinyert fájlokat a projekt mappájába (pl. `projects/JatekNev/batches/`).

### 3. Lépés: Audit vizsgálat (Zajszűrés ellenőrzése)
Nyisd meg az **Audit** fület, vagy futtasd:
```bash
locpipe audit --project "projects/JatekNev"
```
Ellenőrizd az `audit_report.md` jelentést. Ha motor-belső technikai azonosítók (GUID, belső elérési utak) maradtak a megtartott (`kept`) sorok között, vedd fel a regex mintát a `uabea_json_path_exclude` listába.

### 4. Lépés: Preflight Terv (Költség- és tokenszámítás)
A **Run** fülön kattints a **📋 Run Plan (Dry Estimate)** gombra (vagy CLI-ben: `locpipe plan --project "projects/JatekNev"`).
Ez **0 API hívással** és 0 költséggel pontosan megmutatja a bejegyzések számát, a dedup arányt és a becsült tokenszükségletet.

### 5. Lépés: Kis tesztfutás & Erőforrás-generálás (Bootstrap)
Futtass le egy tesztet pl. 1 batch-re vagy 50 API hívásos korláttal:
```bash
locpipe run --project "projects/JatekNev" --limit 1
```
A sikeres próba után generáld le az erőforrás-vázlatokat:
- Kattints a Projects fülön a **⚡ Bootstrap Resources (from TM)** gombra (vagy CLI-ben: `locpipe bootstrap-resources --project "projects/JatekNev"`).
- Nyisd meg a `resources/` mappát, nézd át a `glossary.draft.md` és `character-voices.draft.md` fájlokat.
- Ha elégedett vagy velük, nevezd át őket végleges `glossary.md` és `character-voices.md` névre.

### 6. Lépés: Teljes fordítási futás
Indítsd el a teljes projekt fordítását a **Run** fülön (vagy CLI-ben):
```bash
locpipe run --project "projects/JatekNev" --max-api-calls 500
```
- A folyamat valós időben menti az eredményeket a `checkpoint.json`-ba és a közös Translation Memory-ba (`tm/translation_memory.sqlite3`).
- Megszakítás esetén egyszerűen indítsd újra a parancsot: automatikusan ott folytatja, ahol abbahagyta.

### 7. Lépés: Utólagos integritás-ellenőrzés
Bizonyítsd be, hogy a motor-specifikus és kizárt adatok 100%-ban érintetlenek maradtak:
```bash
locpipe verify --project "projects/JatekNev"
```

### 8. Lépés: Minőségellenőrzés & Riportok
A futás végén a `review/` mappában három elemző riport áll rendelkezésre:
- **`review/full_bilingual_report.md`** — Teljes kétnyelvű (angol-magyar) táblázat az összes lefordított szövegről lektoráláshoz.
- **`review/consistency_report.md`** — Hasonló angol forrásszövegek eltérő magyar fordításainak összehasonlítása.
- **`review/review_report.md`** — A hibás vagy javításra szorult sorok részletes naplója.

### 9. Lépés: Visszaimportálás a játékba
Importáld vissza az elkészült JSON / CSV / PO fájlokat a játékba (pl. UABEA-val a `.assets` fájlba). Unity IL2CPP játékok esetén a GUI **Fix CRC** gombjával állítsd helyre a bináris integritást.

---

## 4. `project.yaml` Konfigurációs Referencia

```yaml
project: Sunderfolk PC
source_lang: en
target_lang: hu
target_register: informal   # informal (tegeződés — alapértelmezett) | formal (magázódás)
format: uabea_json          # uabea_json | unity | ue4_5_po | po_gettext | generic_kv | xliff

batches:
  glob: "*/*.json"          # bemeneti fájlok mintázata

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
    max_expansion_ratio: 1.8
  - name: ui
    default: true
    needs_character_voice: false
    batch_size: 350
    max_expansion_ratio: 1.3

provider:
  name: antigravity_cli     # Google Antigravity CLI motor
  model: gemini-3.7-flash   # fordítási modell
  effort: low               # low | high (gondolkodási szint)
  review_model: gemini-3.7-flash
  review_effort: high       # magasabb effort a minőségi QA javításhoz
  max_concurrency: 2

format_options:
  noise_filter: true
  character_replacements:
    ő: ô
    ű: û
    Ő: Ô
    Ű: Û
  uabea_json_path_exclude:
    - "^m_LocaleId\.m_Code$"
    - "^m_Identifier\.m_Code$"
    - "^m_LocaleName$"
    - "^references\."

tm:
  db_path: tm/translation_memory.sqlite3

confidence:
  review_threshold: 0.75
  tier1_repair_attempts: 2
```

---

## 5. LocPipe Parancsok Gyorsreferenciája

| Parancs | Leírás | LLM Hívás? |
|---|---|:---:|
| `locpipe init <név>` | Új projektstruktúra és konfigurációs sablon létrehozása | ❌ |
| `locpipe plan --project <útvonal>` | Előzetes token-, duplikáció- és batch-számítás | ❌ |
| `locpipe audit --project <útvonal>` | Formátum zajszűrésének vizsgálata (`audit_report.md`) | ❌ |
| `locpipe verify --project <útvonal>` | Fordítás utáni integritás-ellenőrzés (bizonyítja a zaj érintetlenségét) | ❌ |
| `locpipe run --project <útvonal>` | Fordítási folyamat futtatása | ✔️ |
| `locpipe run ... --dry-run` | Pipeline tesztelés mock providerrel (fájlba ír, TM-et nem szennyez) | ❌ |
| `locpipe run ... --pseudo-loc` | Pszeudo-lokalizáció UI túlcsordulások tesztelésére (+30% hossz) | ❌ |
| `locpipe run ... --limit <N>` | Csak az első N fájl feldolgozása teszteléshez | ✔️ |
| `locpipe run ... --max-api-calls <N>` | Szigorú felső korlát az elküldhető API kérések számára | ✔️ |
| `locpipe tm-invalidate --project <útvonal> --key <szó>` | Adott fordítás törlése a TM-ből újrafordítás kényszerítéséhez | ❌ |
| `locpipe bootstrap-resources --project <útvonal>` | Glosszárium, stílus és hangnem vázlatok készítése a TM-ből | ✔️ |
