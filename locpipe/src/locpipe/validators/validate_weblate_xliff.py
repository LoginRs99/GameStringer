#!/usr/bin/env python3
"""
validate_weblate_xliff.py -- mechanikus integritas-ellenorzo Weblate
altal exportalt XLIFF 1.1 fajlokhoz (format-weblate-xliff.md).

Altalanos, projekt-fuggetlen ellenorzeseket vegez -- NEM feltetelezi,
hogy egy adott jelolesi minta (pl. {...}) egy adott projektben
placeholder vagy tartalmi blokk. Alapertelmezesben ket, biztonsagosan
altalanositano mintat ellenoriz DARABSZAM szerint (nem tartalom
szerint):

  - '{' / '}' parositas -- barmilyen projektben hasznos strukturalis
    jelzes lehet, fuggetlenul attol, hogy placeholder-t vagy csak egy
    ismetlodo tartalmi blokkot (pl. cim/leiras-part) jelol a mogottes
    projektben -- ld. format-weblate-xliff.md "Kotelezo lepes" szakasza,
    ott irjuk le, hogyan derítsd ki EZEN a projekten, melyik eset all fenn.
  - %s / %d -- szeles korben elterjedt, altalaban valodi placeholder,
    tartalom szerint is ellenorizzuk (nem csak darabszam), mert ez a
    konvencio tobbnyire szigoruan vedett szokott lenni.

Ellenorzesek:
  1. XML jolformaltsag.
  2. Duplikalt trans-unit id -- EGY <file> elemen belul (XLIFF 1.1
     szerint az id csak fajlon belul garantaltan egyedi, nem a teljes
     dokumentumon; tobb <file>-t tartalmazo, osszefuzott exportnal ezt
     kulon-kulon nezzuk, nehogy ket fuggetlen file azonos id-je hamis
     duplikatumkent jelenjen meg).
  3. '{' / '}' darabszam-egyezes forras/cel kozott.
  4. %s / %d token-egyezes forras/cel kozott.
  5. Ures/hianyzo <target>, es 'needs-translation'/'new' allapotu
     bejegyzesek szamlalasa (informacios).

Opcionalis --glossary <glossary.md>: minden bejegyzest ellenoriz a
szoszedet high-bizalmu 'brand' bejegyzesei ellen (ld. _glossary_terms.py).

Hasznalat:
    python3 validate_weblate_xliff.py <fajl.xlf> [<masik.xlf> ...] [--glossary <glossary.md>]

Kilepesi kod: 1, ha talalt CRITICAL vagy MAJOR problemat, kulonben 0.
"""
import re
import sys
import xml.etree.ElementTree as ET

from .glossary_terms import check_protected_terms, extract_glossary_arg, load_glossary_for_check
from .html_tags import check_html_tags

NS = "{urn:oasis:names:tc:xliff:document:1.1}"
PCT_TOKEN_RE = re.compile(r"%\d*\$?[sd]")


def _clean_tag(elem) -> str:
    tag = elem.tag if hasattr(elem, "tag") else ""
    return tag.split("}", 1)[1] if "}" in tag else tag


def local_findall(root, tag_name: str):
    return [e for e in root.iter() if _clean_tag(e) == tag_name]


def local_find_files(root):
    """XLIFF-ben a <trans-unit id> egyedissege csak egy <file> elemen
    BELUL garantalt, nem a teljes dokumentumon -- ha egy exportban tobb
    <file> is van (pl. tobb komponens osszefuzve), a duplikalt-id
    ellenorzest <file>-onkent kell vegezni, kulonben hamis pozitiv
    'duplikatum' jelzes johetne ki ket, egymastol fuggetlen file
    azonos-id-jü bejegyzesebol."""
    files = [e for e in root.iter() if _clean_tag(e) == "file"]
    if not files:
        files = [root]
    return files


def elem_text(elem):
    """Az elem teljes szoveges tartalma (beleertve a kozvetlen szoveget,
    mert ebben az exportban nincsenek beagyazott inline elemek -- ha
    megis lennenek, ez a fuggveny akkor is osszegyujti az osszes
    szoveget, csak a tag-szerkezetet nem kulon kezeli)."""
    if elem is None:
        return ""
    return "".join(elem.itertext())


def validate_file(path, glossary_entries=None):
    critical, major, minor, info = [], [], [], []

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        critical.append(f"XML parse hiba: {e}")
        return critical, major, minor, info

    root = tree.getroot()
    file_elems = local_find_files(root)
    if not file_elems:
        file_elems = [root]  # nincs explicit <file> wrapper -- kezeljuk a gyokeret egy file-kent

    empty_target = 0
    needs_attention = 0
    pairs = []
    any_trans_unit_found = False

    for file_idx, file_el in enumerate(file_elems, start=1):
        trans_units = local_findall(file_el, "trans-unit")
        if not trans_units:
            trans_units = file_el.findall(".//trans-unit")
        if not trans_units:
            continue
        any_trans_unit_found = True
        original_attr = file_el.get("original") or f"#{file_idx}"

        seen_ids = {}
        for tu in trans_units:
            tu_id = tu.get("id", "")
            loc = f"[{original_attr}] id={tu_id!r}" if tu_id else f"[{original_attr}] (nincs id)"

            if tu_id:
                if tu_id in seen_ids:
                    critical.append(f"Duplikalt trans-unit id egy <file>-on ({original_attr!r}) belul: {tu_id!r}")
                else:
                    seen_ids[tu_id] = True
            else:
                major.append(f"{loc}: hianyzik az id attributum.")

            source_el = next((c for c in tu if _clean_tag(c) == "source"), None)
            target_el = next((c for c in tu if _clean_tag(c) == "target"), None)

            source_text = elem_text(source_el)
            target_text = elem_text(target_el)
            state = target_el.get("state") if target_el is not None else None

            if target_el is None or not target_text.strip():
                empty_target += 1
                continue

            if state in ("new", "needs-translation", "needs-review-translation", None):
                needs_attention += 1

            pairs.append((source_text, target_text, loc))

            src_open, src_close = source_text.count("{"), source_text.count("}")
            tgt_open, tgt_close = target_text.count("{"), target_text.count("}")
            if src_open != tgt_open or src_close != tgt_close:
                major.append(
                    f"{loc}: '{{'/'}}' darabszam eltere -- forras: {{{src_open} nyito, {src_close} zaro}}, "
                    f"cel: {{{tgt_open} nyito, {tgt_close} zaro}} "
                    f"(ellenorizd: ebben a projektben a {{}} placeholder-t vagy tartalmi blokkot jelol-e -- "
                    f"ld. format-weblate-xliff.md)"
                )

            src_pct = sorted(PCT_TOKEN_RE.findall(source_text))
            tgt_pct = sorted(PCT_TOKEN_RE.findall(target_text))
            if src_pct != tgt_pct:
                major.append(
                    f"{loc}: %s/%d placeholder eltere -- forras: {src_pct}, cel: {tgt_pct}"
                )

            html_issues = check_html_tags(source_text, target_text, loc)
            major.extend(html_issues)

    if not any_trans_unit_found:
        body = root.find(f".//{NS}body")
        if body is None:
            body = root.find(".//body")
        if body is not None and len(list(body)) == 0:
            info.append("A <body> ures -- ez a Weblate-komponens meg nem tartalmaz stringeket (legitim allapot, nem hiba).")
        else:
            major.append("Nem talalhato trans-unit elem -- ellenorizd a namespace-t/szerkezetet.")
        return critical, major, minor, info

    if empty_target:
        info.append(f"{empty_target} bejegyzesnek ures/hianyzo a target-je (fordítandó).")
    if needs_attention:
        info.append(
            f"{needs_attention} nem-ures bejegyzes van 'new'/'needs-translation'/"
            f"'needs-review-translation' allapotban vagy allapot-jelzo nelkul -- ellenorizendő."
        )

    if glossary_entries:
        major.extend(check_protected_terms(pairs, glossary_entries))

    return critical, major, minor, info


def main(argv):
    argv, glossary_path = extract_glossary_arg(argv)
    if not argv:
        print(__doc__)
        return 1

    glossary_entries = load_glossary_for_check(glossary_path) if glossary_path else None

    any_bad = False
    for path in argv:
        print(f"=== {path} ===")
        critical, major, info = validate_file(path, glossary_entries)
        for label, items in (("CRITICAL", critical), ("MAJOR", major), ("INFO", info)):
            if items:
                print(f"-- {label} ({len(items)}) --")
                for item in items:
                    print(f"  - {item}")
        if not (critical or major or info):
            print("  Nincs eszlelt problema.")
        if critical or major:
            any_bad = True
        print()

    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
