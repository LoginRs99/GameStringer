#!/usr/bin/env python3
"""
validate_generic_kv.py — mechanikus integritas-ellenorzo a generikus
{id, source, target, notes} JSON batch formatumhoz (format-generic-kv.md).

Ez NEM helyettesiti a loc-qa-reviewer skill minosegi/jelentes-hu atnezeset --
csak a mechanikusan, biztosan eldontheto strukturalis hibakat fogja ki:
duplikalt id, hianyzo mezo, placeholder-keszlet eltere source/target kozott,
ICU plural kulcsszo elveszese.

Opcionalis --glossary <glossary.md>: minden bejegyzest ellenoriz a
szoszedet high-bizalmu, vedett kategoriaju (brand/mechanic/lore) 'nem
forditando' bejegyzesei ellen (ld. glossary_terms.py).

Hasznalat:
    python3 validate_generic_kv.py <batch.json> [<batch2.json> ...] [--glossary <glossary.md>]

Kilepesi kod: 1, ha talalt CRITICAL vagy MAJOR problemat, kulonben 0.
"""
import json
import re
import sys

from .glossary_terms import check_protected_terms, extract_glossary_arg, load_glossary_for_check
from .html_tags import check_html_tags

PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}|%[sd]|%\d+\$[sd]")
ICU_START_RE = re.compile(r"\{(\w+)\s*,\s*plural\s*,")
ICU_KEYWORD_RE = re.compile(r"\b(=\d+|zero|one|two|few|many|other)\s*\{")


def extract_icu_blocks_and_strip(text):
    """Kikeresi a balanszolt {var, plural, ...} blokkokat, es egy kanonikus
    {ICU:var} tokenre csereli oket a szovegben, hogy a plural-agakon beluli
    szoveg ne keveredjen ossze valodi placeholder-ekkel. Visszaadja a
    (cserelt_szoveg, [(var, kulcsszo_halmaz), ...]) part."""
    blocks = []
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = ICU_START_RE.match(text, i)
        if m:
            start = i
            depth = 0
            j = i
            while j < n:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            block_text = text[start:j]
            var_name = m.group(1)
            keywords = set(mm.group(1) for mm in ICU_KEYWORD_RE.finditer(block_text))
            blocks.append((var_name, keywords))
            out.append(f"{{ICU:{var_name}}}")
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out), blocks


def extract_placeholders(text):
    if not isinstance(text, str):
        return set()
    stripped, _ = extract_icu_blocks_and_strip(text)
    return set(PLACEHOLDER_RE.findall(stripped))


def extract_icu_info(text):
    if not isinstance(text, str):
        return []
    _, blocks = extract_icu_blocks_and_strip(text)
    return blocks


def validate_file(path, glossary_entries=None):
    critical, major, minor, info = [], [], [], []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        critical.append(f"Ervenytelen JSON: {e}")
        return critical, major, minor, info
    except UnicodeDecodeError as e:
        critical.append(f"Kodolasi hiba (nem UTF-8?): {e}")
        return critical, major, minor, info

    if not isinstance(data, list):
        critical.append("A gyoker elemnek tombnek (JSON array) kell lennie.")
        return critical, major, minor, info

    seen_ids = {}
    empty_targets = 0
    stub_targets = 0
    pairs = []

    for idx, entry in enumerate(data):
        loc = f"[{idx}]"
        if not isinstance(entry, dict):
            critical.append(f"{loc}: nem objektum.")
            continue

        eid = entry.get("id")
        loc = f"id={eid!r}" if eid is not None else loc

        for field in ("id", "source", "target"):
            if field not in entry:
                critical.append(f"{loc}: hianyzik a '{field}' mezo.")

        if "notes" in entry and not isinstance(entry["notes"], list):
            minor.append(f"{loc}: a 'notes' mezo nem lista (nem feltetlenul hiba, de ellenorizd).")

        if eid is not None:
            if eid in seen_ids:
                critical.append(f"{loc}: duplikalt id (elso elofordulas index {seen_ids[eid]}, ez: {idx}).")
            else:
                seen_ids[eid] = idx

        source = entry.get("source", "")
        target = entry.get("target", "")

        if target == "":
            empty_targets += 1
            continue
        if isinstance(source, str) and target == source and source.strip() != "":
            stub_targets += 1
            continue

        pairs.append((source, target, loc))

        src_ph = extract_placeholders(source)
        tgt_ph = extract_placeholders(target)
        if src_ph != tgt_ph:
            missing = src_ph - tgt_ph
            extra = tgt_ph - src_ph
            detail = []
            if missing:
                detail.append(f"hianyzik a targetbol: {sorted(missing)}")
            if extra:
                detail.append(f"target-ben tobblet (forrasban nincs): {sorted(extra)}")
            major.append(f"{loc}: placeholder-keszlet eltere -- {'; '.join(detail)}")

        html_issues = check_html_tags(source, target, str(eid) if eid is not None else "")
        major.extend(html_issues)

        src_icu = extract_icu_info(source)
        tgt_icu = dict((v, kw) for v, kw in extract_icu_info(target))
        for var_name, src_kw in src_icu:
            tgt_kw = tgt_icu.get(var_name)
            if tgt_kw is None:
                major.append(f"{loc}: hianyzik a(z) '{var_name}' ICU plural blokk a target-bol.")
            elif src_kw - tgt_kw:
                major.append(
                    f"{loc}: ICU plural kulcsszo hianyzik a target '{var_name}' blokkjabol: {sorted(src_kw - tgt_kw)}"
                )

    if glossary_entries:
        major.extend(check_protected_terms(pairs, glossary_entries))

    if empty_targets:
        info.append(f"{empty_targets} bejegyzesnek ures a target-je (fordítandó -- ld. loc-translator).")
    if stub_targets:
        info.append(f"{stub_targets} bejegyzesnel target == source (meg angolul van -- fordítandó).")

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
        critical, major, minor, info = validate_file(path, glossary_entries)
        for label, items in (
            ("CRITICAL", critical),
            ("MAJOR", major),
            ("MINOR", minor),
            ("INFO", info),
        ):
            if items:
                print(f"-- {label} ({len(items)}) --")
                for item in items:
                    print(f"  - {item}")
        if not any(critical + major + minor + info):
            print("  Nincs eszlelt problema.")
        if critical or major:
            any_bad = True
        print()

    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
