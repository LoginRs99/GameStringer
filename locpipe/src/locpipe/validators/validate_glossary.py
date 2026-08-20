#!/usr/bin/env python3
"""
validate_glossary.py -- strukturális integritás-ellenőrző a
.agents/context/glossary.md fájlhoz (glossary-schema.md).

A loc-glossary-researcher skill futtatja minden ÍRÁS UTÁN, hogy a saját
maga által bővített táblázat még mindig séma-konform maradjon -- a
glossary.md a többi skill (loc-translator, loc-qa-reviewer) számára a
"forrás igazság", ezért egy csendben becsúszott hibás sor (rossz oszlopszám,
érvénytelen kategória, véletlen duplikátum) minden további batch-re
kihatna.

Ellenőrzések:
  1. Minden adat-sor pontosan 5 oszlopot tartalmaz.
  2. Nincs üres 'Forrás kifejezés' vagy 'Célnyelvi fordítás' mező.
  3. Üres 'Forrás / indoklás' mező -- MAJOR (nincs papírnyom, honnan
     ered a kifejezés, ld. glossary-schema.md bizalmi szintek).
  4. Kategória érvényes (brand/lore/mechanic/ui/person), kivéve a
     ⚠️-jelölt kettős/kontextusfüggő bejegyzéseket (ott összetett érték
     is elfogadott, pl. "mechanic/ui").
  5. Bizalom érvényes (high/medium/low), ugyanezzel a kivétellel.
  6. Véletlen duplikált forrás-kifejezés: ha ugyanaz a forrás kifejezés
     két KÜLÖN (nem ⚠️-jelölt) sorban szerepel -- ez majdnem mindig azt
     jelenti, hogy egy kontextusfüggő kettős jelentést kellett volna egy
     sorba összevonni ⚠️ jelöléssel, nem két sorra szétválasztani.

Ez NEM ellenőrzi, hogy a fordítások maguk helyesek-e -- az a
loc-glossary-researcher/loc-qa-reviewer dolga. Csak a táblázat saját
strukturális konzisztenciáját nézi.

Használat:
    python3 validate_glossary.py <glossary.md>

Kilépési kód: 1, ha talált CRITICAL vagy MAJOR problémát, egyébként 0.
"""
import sys

from .glossary_terms import VALID_CATEGORIES, VALID_CONFIDENCE, parse_glossary


def main(argv):
    if not argv:
        print(__doc__)
        return 1

    path = argv[0]
    critical, major, info = [], [], []

    try:
        entries, issues = parse_glossary(path)
    except OSError as e:
        print(f"=== {path} ===")
        print(f"-- CRITICAL (1) --\n  - Nem olvasható fájl: {e}")
        return 1

    for lineno, msg in issues:
        critical.append(f"{lineno}. sor: {msg}")

    seen_sources = {}
    for idx, e in enumerate(entries):
        loc = f"{e['lineno']}. sor ('{e['source']}')"

        if not e["source"]:
            critical.append(f"{e['lineno']}. sor: üres 'Forrás kifejezés' mező.")
        if not e["target"]:
            critical.append(f"{loc}: üres 'Célnyelvi fordítás' mező.")
        if not e["justification"]:
            major.append(f"{loc}: üres 'Forrás / indoklás' mező -- nincs papírnyom, honnan ered a kifejezés.")

        if not e["is_dual"]:
            cats = {c.strip() for c in e["category"].split("/") if c.strip()}
            if not cats or not cats.issubset(VALID_CATEGORIES):
                major.append(
                    f"{loc}: érvénytelen kategória: {e['category']!r} "
                    f"(várt egyike: {sorted(VALID_CATEGORIES)}, vagy ⚠️-jelölt kettős bejegyzés)."
                )
            conf_base = e["confidence"].split("(")[0].strip()
            if conf_base not in VALID_CONFIDENCE:
                major.append(
                    f"{loc}: érvénytelen bizalmi szint: {e['confidence']!r} "
                    f"(várt egyike: {sorted(VALID_CONFIDENCE)}, vagy ⚠️-jelölt kettős bejegyzés)."
                )

        key = e["source"].lower().strip()
        if key and not e["is_dual"]:
            if key in seen_sources:
                prev = entries[seen_sources[key]]
                major.append(
                    f"{loc}: a(z) '{e['source']}' forrás kifejezés már szerepel a(z) "
                    f"{prev['lineno']}. sorban is, külön sorként -- ha ez szándékosan "
                    f"kontextusfüggő kettős jelentés, vond össze egy ⚠️-jelölt sorba "
                    f"(ld. glossary-schema.md 'Vitatott/kettős bejegyzés'), különben "
                    f"töröld a duplikátumot."
                )
            else:
                seen_sources[key] = idx

    dual_count = sum(1 for e in entries if e["is_dual"])
    info.append(f"Összesen {len(entries)} szószedet-bejegyzés.")
    if dual_count:
        info.append(f"Ebből {dual_count} kontextusfüggő (⚠️) kettős bejegyzés.")
    if not entries and not issues:
        info.append("A szószedet még üres (csak fejléc) -- ez önmagában nem hiba, ha a projekt épp csak most indul.")

    print(f"=== {path} ===")
    for label, items in (("CRITICAL", critical), ("MAJOR", major), ("INFO", info)):
        if items:
            print(f"-- {label} ({len(items)}) --")
            for item in items:
                print(f"  - {item}")
    if not (critical or major):
        print("  Nincs strukturális probléma.")

    return 1 if (critical or major) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
