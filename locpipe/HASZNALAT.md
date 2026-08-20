# LocPipe — Használati utasítás

Ez a leírás a napi használatot mutatja be, konkrét parancsokkal. Az architektúra és a tervezési döntések indoklása a `README.md`-ben van (angolul) — ez itt a "mit gépeljek be" verzió, magyarul.

---

## 1. Telepítés

```bash
cd locpipe
pip install -e .                # antigravity_cli-hoz (alapértelmezett) semmi extra nem kell --
                                 # csak a meglévő `agy` binárist hívja subprocess-ből
# vagy: pip install -e ".[gemini]"     ha a gemini providert (opcionális fallback) is akarod
```

A tiszta pipeline-hoz (kivonatolás, validálás, TM stb.) nem kell API-kulcs. Csak akkor, ha ténylegesen fordíttatni akarsz.

---

## 2. Új projekt létrehozása

```bash
locpipe init projektnev
```

Ez létrehozza a `projects/projektnev/` mappát:

```
projects/projektnev/
├── project.yaml              <- itt állítasz be mindent
├── batches/                  <- ide kerülnek a fordítandó fájlok
└── resources/
    ├── glossary.md
    ├── lang-style.md
    ├── character-voices.md
    └── anti-fabrication-checklist.md
```

Töltsd fel a `resources/` alatti fájlokat (glosszárium, stílusútmutató, szereplő-hangnem), majd másold be a fordítandó batch-fájljaidat a `batches/` mappába.

---

## 3. `project.yaml` kitöltése

A legfontosabb mezők:

```yaml
project: projektnev
source_lang: en
target_lang: hu
format: generic_kv              # generic_kv | po_gettext | ue4_5_po | unity | uabea_json | xliff

batches:
  glob: "batches/batch_*.json"  # milyen fájlneveket keressen

categories:
  - name: dialogue
    match_speaker_present: true # ha a bejegyzésnek van "speaker" mezője
    needs_character_voice: true
    batch_size: 200               # dialógusnál kisebb batch: hosszabb sorok, több
                                   # kontextust visz -- lásd lejjebb a méretezésről

  - name: ui
    default: true                # minden más ide esik
    needs_character_voice: false
    batch_size: 350

provider:
  name: antigravity_cli          # antigravity_cli (alapértelmezett) | gemini
  model: gemini-3.7-flash        # bulk fordításhoz
  effort: low                    # low | high -- csak antigravity_cli-nél számít
  review_model: gemini-3.7-flash # a review-lépéshez (13. fázis) -- ugyanaz a modell, csak
                                 # magasabb effort-tal, nem külön Pro-modell (ld. lent, miért)
  review_effort: high            # low is jó, ha inkább költséget optimalizálnál itt is
  mode: batch                   # sync | batch -- lásd 6. pont
  max_concurrency: 5
  max_retries: 5                 # hány próbálkozás egy adott batch/hívás sikertelensége
                                 # (rate limit, timeout, hibás válasz) esetén, mielőtt a
                                 # fájl "befejezetlen"-nek számít -- mindkét providerre
                                 # vonatkozik
  sync_call_timeout_s: 300       # csak sync módnál: mennyi ideig várjon EGY fordítási/
                                 # review-hívásra, mielőtt időtúllépésnek veszi és
                                 # újrapróbálja. NE keverd a lenti timeout_s-szel -- az
                                 # kizárólag batch-módban, egy beküldött job végére várásra
                                 # vonatkozik (24-48 óra is lehet, ott ez helyes)

translate_file_window: 8        # csak sync módnál (antigravity_cli): ennyi pending
                                 # fájl batch-eit fordítja EGYÜTT, egy konkurens
                                 # körben, mielőtt bármelyiket lezárná (validál/
                                 # review/merge/TM-commit). Sok kisfájlos projektnél
                                 # (fájlonként 1-2 batch) ez tartja folyamatosan
                                 # kihasználva a max_concurrency-t -- fájlonkénti
                                 # fordítással a legtöbb slot ürességben állt.
                                 # Nagyobb = jobb konkurencia-kihasználás, de több
                                 # fájl RAM-ban egyszerre, és tovább tart, míg az
                                 # első fájl ténylegesen elkészül. 8 jó alapérték
                                 # tipikus batch_size mellett.

confidence:
  review_threshold: 0.75        # ez alatt megy review-ra
  tier1_repair_attempts: 2      # determinisztikus validálási hiba (hiányzó tag/placeholder)
                                 # ennyi ingyenes/olcsó újrapróbálkozást kap a bulk-fordító
                                 # híváson keresztül, mielőtt a drága review agent-hez kerülne
```

**Kategóriák:** minden bejegyzés az első illeszkedő szabályba esik, felülről lefelé. Ha van fejlesztői/belső szöveged (pl. AI-tuning tooltipek), érdemes külön kategóriát csinálni neki `match_key_regex`-szel — ez nem kér karakterhangot, nagyobb batch-mérettel mehet.

**Jelenetek együtt tartása dialógusnál (opcionális):** ha a formátumod hordoz valamilyen "melyik jelenethez/questhez tartozik" mezőt (pl. a projektednél `context_screen`), ezzel egy jelenet sorai egy batch-ben maradnak, és minden sor megkapja az előző néhány sort kontextusként:

```yaml
  - name: dialogue
    narrative_boundary_field: context_screen
    narrative_context_window: 4    # utolsó 4 sor kontextusként
```

Alapból ki van kapcsolva — ha nem állítod be, minden a régi módon megy.

**`batch_size` méretezése — miért 200/350, ne nagyobb:** egy batch összes fordítását EGY LLM-válaszban kell visszakapni, a `provider.max_output_tokens` (alapból 16384) korláton belül. Ökölszabály: `batch_size * ~25-35 token/bejegyzés` maradjon ez alatt, jó ráhagyással -- ha túllépi, a válasz csonkolva/hibás JSON-nal jön vissza, a batch újrapróbálkozik (`max_retries`-ig), és ha minden próbálkozás elfogy, az egész FÁJL befejezetlen marad ebben a futásban. Hosszabb szövegeknél (dialógus, questleírás) menj lejjebb, rövid UI-címkéknél mehetsz feljebb -- de ne vakon: ha bizonytalan vagy, inkább kisebb legyen, mint hogy csendben csonkoljon.

**Tartalom szerinti szűrés -- `match_source_regex`:** a `match_key_regex`/`match_notes_regex` mellett a tényleges forrásszövegre is lehet illeszteni. Hasznos pl. Unreal argumentum-módosító szintaxisnál (lásd 3b. pont) vagy bármilyen más, a szövegben felismerhető mintánál:

```yaml
  - name: format_sensitive
    match_source_regex: '\|(plural|gender|ordinal)\('
    batch_size: 80
```

---

## 3b. Unreal Engine 4/5: `format: ue4_5_po`

A Localization Dashboard `.po` exportja (mindkét nem-Crowdin collapse módban -- "Identical Text Identity" és "Identical Namespace") szabványos gettext szerkezet, csak a `msgctxt` hordozza az Unreal identitást/namespace-t -- ezt a `po_gettext` adapter (polib-bal) natívan helyesen kezeli, a `ue4_5_po` formátumnév csak ráköti a hozzá tartozó Unreal-specifikus **validátort** is:

```yaml
format: ue4_5_po
```

**Mit ellenőriz külön:** Unreal `{Arg}|plural(...)`/`|gender(...)`/`|ordinal(...)` argumentum-módosító szintaxisát, pl.:

```
{Count}|plural(one=You have {Count} item,other=You have {Count} items).
{Gender}|gender(He,She,They) greets you.
```

A `{Arg}` referencia eltűnését a sima placeholder-ellenőrzés is elkapná, de azt, hogy a `|plural(...)`/`|gender(...)` **szerkezet** (a modifier kulcsszó, a plural/ordinal ágak) sértetlen marad-e, csak ez a validátor nézi -- kritikus hibaként jelzi, ha egy plural-ág (pl. `few`) eltűnik, vagy ha a teljes modifier lekopik a fordításnál. Ezt a validátor **nem** próbálja saját maga kijavítani vagy "kitalálni" -- csak jelzi, a tier1-repair/review lépés dolga a javítás.

Ha sok ilyen soron van a projektben, érdemes külön kategóriába terelni őket kisebb batch-mérettel (lásd fent, `match_source_regex`), hogy egy elrontott válasz kevesebb sort vigyen magával.

**Fontos csapda -- `match_speaker_present` PO/UE-formátumnál sosem talál.** A `po_gettext`/`ue4_5_po` adapter nem tölti ki az `entry.speaker` mezőt (a PO formátumnak nincs natív "ki mondja" mezője) -- tehát egy ilyen kategória-szabály:

```yaml
categories:
  - name: dialogue
    match_speaker_present: true   # PO/UE-nél ez SOSEM igaz -- minden a default kategóriába esik
```

soha nem fog aktiválódni, és minden bejegyzés (a valódi párbeszéd-sorok is) a default/`ui` kategóriába esik -- karakterhang-injektálás, dialógusnak megfelelő batch-méret nélkül. Ezt a végén-végig futtatott valódi teszt fedte fel, nem a unit tesztek.

**A megoldás:** a `msgctxt` benne van az `entry.key`-ben (`{msgctxt}\x04{msgid}` formában), tehát `match_key_regex`-szel (vagy `match_notes_regex`/`match_source_regex`-szel, a projekted saját namespace-konvenciója szerint) lehet helyesen routolni:

```yaml
categories:
  - name: dialogue
    match_key_regex: '^Dialogue\.'   # a te msgctxt-konvenciódhoz igazítva
    needs_character_voice: true
    batch_size: 200
```

Ellenőrizd a saját `.po`-fájlod `msgctxt` mintázatát (`grep msgctxt fajl.po | head`), és ez alapján állítsd be a regex-et -- nincs univerzális alapérték, mert a namespace-elnevezés projektenként/csapatonként eltér.

---

## 3c. Unity: `format: unity` vagy `format: uabea_json`

Két külön útvonal, más-más export-típushoz:

- **`unity`** -- a hivatalos Unity Localization Package CSV-exportjához (Key/Id + nyelvi oszlopok). Az oszlopneveket heurisztikusan ismeri fel, de eltérő elnevezéshez expliciten is megadhatók (`format_options.source_column_names` / `target_column_names`). Ha van `Type`/`content_type` oszlopod, annak értéke automatikusan bekerül minden bejegyzés `notes`-ába `type:<érték>` formában -- ezt egy `match_notes_regex` kategória-szabállyal ki is tudod használni kategorizálásra, nem csak infóként megy ki az LLM-nek.
- **`uabea_json`** -- UABEA-val kibontott, nyers Unity asset-dump (pl. MonoBehaviour typetree exportok). Mivel ez sokkal zajosabb formátum (motor-belső GUID-ok, asset-útvonalak stb. keverednek a valódi szöveggel), van hozzá dedikált zajszűrő és audit-eszköz -- lásd az 5b. pontot.

Ha a projekted I2 Localization-t (egy elterjedt, nem hivatalos Unity-asset) használ, az egy harmadik, saját formátum -- ehhez jelenleg nincs kész adapter, szólj ha kell.

---

## 3d. Sorozat/több rész: korábbi játékok fordításának felhasználása

Ha 2+ egymáshoz kapcsolódó játékot (pl. egy sorozat részeit) fordítasz, van egy gyakorlatilag **kódmódosítás nélkül** elérhető, hatékony megoldás -- nem kell hozzá semmi különleges "sorozat-mód", mert a meglévő TM/glosszárium-mechanizmus már pont erre való.

**Egzakt TM-újrafelhasználás -- közös TM-fájl.** A `tm.db_path` bármelyik projekt gyökerén kívülre is mutathat:

```yaml
# projects/jatek1/project.yaml és projects/jatek2/project.yaml egyaránt:
tm:
  db_path: ../../shared/series-tm.sqlite3
```

Ha egy sztring szó szerint megegyezik két részben (ismétlődő UI-szöveg, menüelem, rendszerüzenet -- ezeknél tipikusan magas az átfedés, sztoriszövegnél/dialógusnál értelemszerűen alacsony), a második játék futtatásakor ez **nulla LLM-hívással** kerül elő a TM-ből. **Fontos feltétel:** a TM-kulcs `(content_hash, category, context_key)` -- ha az egyik projekt `ui`-nak, a másik `interface`-nek nevezi ugyanazt a kategóriát, az egyébként egyező sztringek nem fognak találkozni. Tartsd konzisztensnek a kategórianeveket a sorozat összes `project.yaml`-jában.

**Sorozat-szintű glosszárium -- közös fájl.** Ugyanez a minta:

```yaml
resources:
  glossary: ../../shared/series-glossary.md
```

Karakterek, helyszínek, tárgyak, skillek, frakciók, UI-terminológia -- mindegyik játék ugyanazt a fájlt bővíti/olvassa. **Ez a batch-onkénti glosszárium-pruning miatt nem drágul a projekt méretével** -- a `prune_for_batch()` (lásd `glossary.py`) minden batch-hez csak azokat a tagokat küldi ki, amik a batch szövegében ténylegesen előfordulnak, tehát egy 5 játéknyi közös glosszárium ugyanannyi tokent költ egy batch-nél, mint egy 1 játéknyi -- `antigravity_cli`-nél ez garantált (per-batch pruning mindig fut), `gemini`-nél a category-szintű cache-elt teljes glosszárium nő, de az a szerveroldali cache-elés miatt továbbra is olcsó batch-enként.

**Kontextus (korábbi részek szövegének "behúzása" retrievallel): NEM javasolt.** Egy teljes korábbi játék vagy nagy mennyiségű korábbi szöveg batch-enkénti bepakolása tiszta tokenpazarlás lenne, ahogy te magad is sejtetted -- és egy relevancia-alapú retrieval-rendszer (embedding, vektorkeresés) valódi, folyamatos karbantartási terhet adna egy bizonytalan, nehezen mérhető minőségi előnyért cserébe, ellentétben az egzakt TM-találattal (determinisztikus, ingyenes) vagy a glosszárium-kényszerítéssel (determinisztikus, a meglévő `flag_disputed_terms`/`glossary_terms.py` már biztosítja). Nem éri meg a komplexitást.

**Összefoglalva:** egzakt TM + közös glosszárium igen (gyakorlatilag ingyenes, nulla kódmódosítás, csak a `project.yaml`-ban közös elérési utak beállítása), kontextus-retrieval nem.

---

## 4. Melyik provider-t válaszd?

| | Mikor válaszd | Amit tudni kell |
|---|---|---|
| **`antigravity_cli`** | Ez az alapértelmezett -- ha már be vagy jelentkezve `agy auth login`-nal, semmi mást nem kell beállítani | Lásd kockázat-magyarázat lent -- ki van védve, de érdemes tudni róla. |
| **`gemini`** | Ha szeretnéd a szerver-oldali prompt cache-elés költségelőnyét (a teljes szószedet/karakter-bibliát csak egyszer fizeted meg kategóriánként, nem batch-enként), vagy batch-mode job-ot akarsz indítani | `GEMINI_API_KEY` szükséges (ingyenes: aistudio.google.com/apikey). Ugyanaz a Google-fiók, mint az `agy`-hoz. |
**Az `antigravity_cli`-ról érdemes tudni:** az `agy --print` (nem-interaktív mód) dokumentáltan képes lefutni és *semmit* ki nem írni, miközben 0-s exit code-dal tér vissza -- subprocess-ből hívva pont ez a helyzet áll fenn. `providers/antigravity_cli_provider.py` emiatt **soha nem bízik az exit code-ban önmagában** -- üres kimenetnél hangosan hibát dob ahelyett, hogy hamis sikert jelentene. Emellett nincs perzisztens cache a hívások között, ezért ez a provider batch-enként kapja a szószedetet/karakter-bibliát (kiszűrve a batch-ben ténylegesen szereplő kifejezésekre/szereplőkre), nem a teljeset -- ez pótolja a hiányzó cache-előnyt.

Ha inkább a szerver-oldali cache-elés költségelőnyét akarod (nagy projektnél, sok batch-csel ugyanabban a kategóriában, ez számottevő lehet), válaszd a `gemini`-t -- ekkor a teljes szószedet/karakter-bibliát egyszer küldöd kategóriánként, és a cache viszi tovább.

Akármelyik providert választod, nagy futás előtt érdemes egy `locpipe run --limit 1`-gyel kipróbálni -- ez csak az első batch fájlt dolgozza fel, így gyorsan látod, hogy a beállítások (glosszárium, stílus, provider) tényleg úgy működnek-e, ahogy vártad.

Környezeti változó beállítása:
```bash
export GEMINI_API_KEY="..."       # gemini providerhez (opcionális fallback)
# antigravity_cli-hez nem kell külön kulcs, csak `agy auth login`
```

**`review_model`/`escalation_model` -- miért nem automatikusan Pro:** a `gemini-3.1-pro` régen a magától értetődő "erősebb modell" választás volt a review-lépéshez. A `gemini-3.7-flash` megjelenésével (2026.08) ez már nem egyértelmű: az Artificial Analysis Intelligence Index szerint `gemini-3.7-flash` `high` effort-tal **magasabb** pontszámot ér el, mint a `gemini-3.1-pro` (56 vs 48), miközben tokenenként lényegesen olcsóbb is. Emiatt a sablon alapból `review_model: gemini-3.7-flash` + `review_effort: high`-ot ad, nem külön Pro-modellt. Ha nincs külön megadva `escalation_model`, az automatikusan a `review_model`-t örökli -- tehát ez a döntés a legkeményebb ~5%-os mintára (`escalation_effort: high` alapból) is vonatkozik, hacsak nem adsz meg neki explicit külön modellt.

---

## 5. Mielőtt bármit fordíttatnál: `locpipe plan`

```bash
locpipe plan --project projects/projektnev
```

**Ez nem hív LLM-et, nem ír semmit.** Tisztán kiszámolja a valós számokat:

```
53214 entries across the scanned batch files
  1847 already have a translation
  0 would be filled from translation memory (no LLM call)
  31402 unique strings actually need translating
  -> 18 LLM calls, by category:
       developer_text: 3 call(s)
       dialogue: 9 call(s)
       ui: 6 call(s)

Rough token estimate (chars/4 heuristic -- for sizing, not billing):
  ~142,000 input tokens at full price
  ~890,000 more input tokens, but as cache reads (automatic on Gemini 2.5+)
  ~410,000 output tokens
```

(A fenti számok kitaláltak, illusztrációnak — a te tényleges duplikáció-arányod eltérhet. Erre való a `plan`: a saját projekted valós arányát mutatja, nem egy általános becslést.)

Ha ez alapján túl soknak tűnik egy menetben, a `--limit N` kapcsolóval csak az első N batch-fájlt nézi/futtatja — így fokozatosan is haladhatsz.

---

## 5b. `uabea_json` projektnél: `locpipe audit` — mennyi szemét megy ki feleslegesen?

A `uabea_json` formátum két nagyon eltérő úton extraktál szöveget:

- **CSV `m_Script`-ben** (pl. Consumables, Subtitles) — validált oszlopfejlécből olvas, eleve tiszta, itt nincs teendő.
- **MonoBehaviour typetree** (pl. LocalizedTextBank) — rekurzívan bejár egy tetszőleges JSON-struktúrát, és *heurisztikával* dönti el, melyik string a valódi szöveg és melyik motor-belső adat (GUID, asset-útvonal, enum-konstans, indexelt azonosító stb.). Ez a heurisztika (`adapters/engine_noise.py`) tudatosan **konzervatív** — inkább küld ki pár felesleges tokent, mint hogy véletlenül kihagyjon valós szöveget —, de projektenként lehet olyan technikai mező, amit nem ismer fel.

Mielőtt éles fordítást futtatsz egy typetree-alapú fájlon, nézd meg mit extraktálna:

```bash
locpipe audit --project projects/projektnev
```

**Ez sem hív LLM-et, nem ír semmit** — csak jelentést készít (`<project>/audit_report.md`, vagy `--out <path>`), csoportosítva asset + útvonal-előtag szerint:

```
Scanned 3 file(s).
  kept (would be sent to the LLM):        412
  filtered as engine noise (built-in):    58
  filtered by uabea_json_path_exclude:    0
Full breakdown by asset/path: projects/projektnev/audit_report.md
```

A riportban minden csoportnál látod, mi maradt **kept** (ezek mennek ki fordításra) és mi lett **noise:***-ként kiszűrve, konkrét példákkal. Két dolgot érdemes átnézni:

1. **A `kept` sorok között van-e még szemét?** Ha igen, vedd fel a `project.yaml`-ba:
   ```yaml
   format_options:
     uabea_json_path_exclude:
       - "^entries\\.internal_metadata"   # regex a teljes elérési útra (json_path)
   ```
   Ez a mintázat a teljes egyező részfát kizárja (nem csak egy mezőt), és a jelentésben `excluded_by_config`-ként jelenik meg legközelebb — így ellenőrizni is tudod, hogy tényleg csak szemetet zártál-e ki.
2. **A `noise:*` sorok között van-e olyan, aminek fordítania kellene?** Ha a beépített heurisztika téved a te projekteden, kapcsold ki (`format_options.noise_filter: false`), és bízd az egészet a fenti explicit exclude-listára.

Ez projektenként **egyszeri** átnézés — utána minden jövőbeli extract ingyen kihagyja, amit egyszer már kiszűrtél.

---

## 6. `sync` vagy `batch` mód?

- **`sync`** — azonnal fordít, batch-enként egy hívás, párhuzamosan (`max_concurrency`). Akkor jó, ha próbálgatod a beállításokat, vagy kicsi a maradék munka.
- **`batch`** — az egész futást egy Gemini Batch job-ként küldi be (csak `gemini` providernél; `antigravity_cli` nem támogatja). **50% olcsóbb**, de akár 24 óráig is eltarthat, mire végez. Nagy, sok batch-es projektnél ajánlott mód, mert semmi nincs benne, aminek percek alatt kész kellene lennie.

Batch módban a folyamat **leállítható és később folytatható** — lásd 8. pont.

---

## 7. Éles futtatás

```bash
locpipe run --project projects/projektnev
```

Kimenet menet közben (sync módban batch-enként, batch módban egyben a job végén):

```
18 LLM call(s) needed (0 batch(es) completed so far, 0 entries committed already on record)
Submitted batch job batches/abc123 (18 requests) — can take up to 24h. Safe to stop this process now: re-running `locpipe run` will reattach instead of resubmitting.
```

Ha próba gyanánt előbb API-kulcs nélkül akarod látni, hogy fut-e a gépezet:

```bash
locpipe run --project projects/projektnev --dry-run
```

**Mit csinál pontosan, és mit nem:**

- **Nem hív valós modellt** -- a beépített `MockProvider` minden sztringet `[MOCK-HU] ...` előtaggal ad vissza, a placeholdereket (`{Count}`, `{PlayerName}` stb.) érintetlenül hagyva.
- **A teljes pipeline-t lefuttatja** -- extrakció, dedup, batch-építés, validálás, review-sor, merge -- valódi logikával, csak a "fordítás" hamis. Ez a lényeg: ellenőrizhető, hogy a batching/validálás/merge tényleg működik-e, LLM-token elköltése nélkül.
- **Beleírja a `[MOCK-HU] ...` szöveget a batch-fájlokba** -- ez szándékos (így ellenőrizhető a merge/output-lépés is), de azt jelenti, hogy a valós batch-fájljaid felülíródnak hamis tartalommal. Ha nem git alatt vannak vagy nincs biztonsági mentésed róluk, dolgozz egy másolaton, vagy használd inkább a `locpipe plan`-t (az **semmit** nem ír).
- **Nem szennyezi a Translation Memory-t** -- a `MockProvider` kimenete sosem kerül be a perzisztens TM SQLite-adatbázisba, hiába "sikeres" a futás. Enélkül egy `--dry-run` után futtatott valódi `locpipe run` visszakaphatta volna TM-találatként a `[MOCK-HU]` szemetet -- ez most explicit ki van zárva.
- **Nem ad token-becslést** -- arra a `locpipe plan` való (5. pont), ami még a `--dry-run`-nál is kevesebbet csinál (nem ír semmit, nem is "fordít" hamisan, csak számol).

---

## 8. Megszakadt egy nagy futás — mi van most?

**Mindkét módban:** semmi teendő, csak futtasd újra ugyanazt a parancsot:

```bash
locpipe run --project projects/projektnev
```

A checkpointing egysége egy batch *fájl* (nem egy string, nem is egy LLM-hívás): minden fájl a maga extract → fordítás → validálás → review → merge → TM-commit láncát önmagában, egyben végzi el, mielőtt a pipeline a következő fájlra lépne. A `projects/projektnev/checkpoint.json` pontosan tudja, mely fájlok végeztek teljesen (`completed_files`) -- ezeket egy újrafuttatás **át sem** olvassa be, nemhogy újrafordítaná. Csak a megszakadáskor épp folyamatban lévő fájl (és minden utána következő) próbálkozik újra.

Ha egy fájl feldolgozása közben bármi váratlan hiba történik (nem csak egy LLM-hívás hibázik, hanem pl. egy validátor összeomlik), az a pipeline futását **nem** állítja meg -- csak azt az egy fájlt hagyja befejezetlenül, és megy tovább a többivel ugyanabban a futásban. A futás végén kiírja, hány fájl maradt befejezetlen.

**`batch` módban** ezen felül: a `checkpoint.json` már tudja, melyik job fut — a pipeline visszacsatlakozik hozzá ahelyett, hogy újraküldené (ami dupla számlázást jelentene ugyanazokért a fordításokért). Ha a batch-fájlok és a TM nem változtak a beküldés óta, ez automatikusan működik.

**Ha valami tényleg elakadt** (pl. a checkpoint egy régi job-ra mutat, ami már lejárt): nézd meg a `projects/projektnev/checkpoint.json` `pending_job` mezőjét, ellenőrizd a job státuszát közvetlenül a szolgáltatónál, majd vagy várd meg, vagy manuálisan töröld ki a `pending_job` mezőt a fájlból, mielőtt újrafuttatod.

---

## 9. Mit jelentenek a futás végi számok

```
53214 entries total | 1847 already translated | 12300 filled from TM |
31402 unique strings sent to the LLM (in 18 calls, 12300 more saved by dedup+TM reuse) |
42 validation failures (30 auto-repaired without a review call) |
1180 routed to review, 1140 repaired | Fidelity sampling: 340 sampled, 12 repaired |
30250 new entries committed to TM for future runs | avg 4.2s/call | cache: {'cache_read_tokens': 890000, ...}
```

- **`filled from TM`** — ezeket *nem* fordította le újra, mert már megvolt egy korábbi futásból (vagy előzőleg jóváhagyott fordításból). Minél tovább dolgozol a projekten, ez a szám annál nagyobb lesz batch-ről batch-re.
- **`auto-repaired without a review call`** — determinisztikus validálási hiba (hiányzó tag, placeholder-eltérés stb.), amit a pipeline egy olcsó, automatikus újrapróbálkozással javított, mielőtt a drága review-lépéshez ért volna. Ez azt mutatja, mennyit spórolt ez a lépés ténylegesen.
- **`routed to review` / `repaired`** — ezek buktak el egy determinisztikus ellenőrzésen (miután az automatikus újrapróbálkozás már nem segített) vagy alacsony konfidenciát kaptak. A `repaired` azokat mutatja, amiket a review-lépés sikeresen javított *és* ami után újra lefutott a validálás, hogy tényleg jó-e; a különbség (`routed - repaired`) azok, amiket a review `flag_for_human: true`-val jelölt, VAGY amiknél a review saját javítása is elbukott a validáláson -- ezeket érdemes kézzel átnézni a `projects/projektnev/review/review_report.md`-ben.

---

## 10. Mit nézz át kézzel

```
projects/projektnev/review/needs_review.json     <- gépi olvasásra (kulcs, forrás, jelenlegi fordítás, hibák, konfidencia-jelzők, glosszárium-találatok)
projects/projektnev/review/review_report.md      <- emberi olvasásra
```

Ez tipikusan a bejegyzések kis százaléka (a régi rendszernél minden bejegyzés emberi/LLM QA-n ment át — itt csak az, ami tényleg gyanús, VAGY egy véletlenszerű minőség-ellenőrző minta kategóriánként).

Ezek a fájlok mindent tartalmaznak, amit a pipeline maga nem tudott automatikusan lezárni -- beleértve azokat is, ahol mind az automatikus újrapróbálkozás, mind a review-lépés saját javítása elbukott a validáláson. Ez utóbbi esetben a `needs_review.json`-ban a *jelenlegi*, még mindig fennálló hiba látszik, nem a régi.

---

## 11. Ha új formátumot vagy projektet kell hozzáadni

Új projekt (más nyelvpár, más játék): `locpipe init <név>`, töltsd ki a `project.yaml`-t, másold be a saját glosszáriumodat/stílusodat — a `locpipe/` kód egy sora sem változik.

Új fájlformátum (Ren'Py, Unity, UE3/4/5, Weblate XLIFF — ezekhez a validátor már kész, csak az olvasás/írás hiányzik): lásd `README.md` "Adding a new format adapter" pontját, illetve `locpipe/adapters/registry.py`-ban a pontos lista, mi van kész és mi nincs.

---

## 12. Gyors parancs-összefoglaló

```bash
locpipe init <név>                              # új projekt
locpipe plan --project projects/<név>           # számok, LLM-hívás nélkül
locpipe audit --project projects/<név>          # uabea_json: mit szűr ki extractáláskor, LLM-hívás nélkül
locpipe run --project projects/<név> --dry-run  # próba, API-kulcs nélkül
locpipe run --project projects/<név> --limit 1  # egy batch csak, éles API-val (agy-teszthez is jó)
locpipe run --project projects/<név>            # éles, teljes futás
python3 tests/test_pipeline.py                  # a pipeline-t magát teszteli, nem a te projektedet
```
