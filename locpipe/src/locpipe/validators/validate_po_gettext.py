#!/usr/bin/env python3
"""
validate_po_gettext.py -- mechanikus integritas-ellenorzo szabvany GNU
gettext .po fajlokhoz (format-po-gettext.md). Unreal-varianshoz (format:
ue4_5_po) ezt hasznalja alapnak, plusz ra van rakva egy Unreal-specifikus
plural/gender/ordinal argumentum-modositó-ellenorzes (ld.
validate_ue4_5_po.py) -- ez a fajl maga NEM ismeri az Unreal szintaxist.

Ellenorzesek:
  1. Duplikalt (msgctxt, msgid) par -- ket bejegyzes ne legyen azonos
     kontextussal es forrassal.
  2. msgid_plural eseten hianyzo msgstr[N] agak a fejlecben deklaralt
     nplurals ertekehez kepest.
  3. Placeholder-tokenek (%s, %d, %1$s, %(name)s, {name}, {0}) egyezese
     msgid/msgid_plural es a hozzatartozo msgstr(ok) kozott -- pozicionalis
     %s/%d tokeneknel csak a DARABSZAM egyezeset nezi (ezek atrendezhetok),
     nevesitett/szamozott tokeneknel a PONTOS HALMAZT.
  4. `fuzzy` jelzovel ellatott, de nem-ures msgstr-ek jelzese -- ezek meg
     emberi/QA megerositesre varnak, nem tekintendok kesznek.
  5. Ures msgstr(ok) szamlalasa (informacios).

Opcionalis --glossary <glossary.md>: minden msgstr/msgstr[N] erteket
ellenoriz a szoszedet high-bizalmu 'brand' bejegyzesei ellen (ld.
_glossary_terms.py) -- plural bejegyzeseknel a msgid+msgid_plural
egyuttes szoveget hasznalja forrasnak minden aghoz.

Hasznalat:
    python3 validate_po_gettext.py <fajl.po> [<masik.po> ...] [--glossary <glossary.md>]

Kilepesi kod: 1, ha talalt CRITICAL vagy MAJOR problemat, kulonben 0.
"""
import re
import sys

from .glossary_terms import check_protected_terms, extract_glossary_arg, load_glossary_for_check
from .html_tags import check_html_tags

ENTRY_SPLIT_RE = re.compile(r"\n\s*\n")
FLAGS_RE = re.compile(r'^#,\s*(.+)$', re.MULTILINE)
MSGCTXT_RE = re.compile(r'(?<!_)msgctxt\s+((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
MSGID_RE = re.compile(r'(?<!_)msgid\s+((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
MSGID_PLURAL_RE = re.compile(r'msgid_plural\s+((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
MSGSTR_SIMPLE_RE = re.compile(r'(?<!\[)msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
MSGSTR_N_RE = re.compile(r'msgstr\[(\d+)\]\s+((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
QUOTED_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
NPLURALS_RE = re.compile(r"nplurals\s*=\s*(\d+)")

NAMED_TOKEN_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}|\{\d+\}|%\(\w+\)[sd]|%\d+\$[sd]")
POSITIONAL_TOKEN_RE = re.compile(r"(?<!\$)%[sd]")


def join_quoted(raw):
    if raw is None:
        return None
    parts = QUOTED_STR_RE.findall(raw)
    joined = "".join(parts)
    joined = joined.replace('\\"', '"').replace("\\t", "\t").replace("\\n", "\n")
    return joined


def parse_po(text):
    entries = []
    header_nplurals = None
    for block in ENTRY_SPLIT_RE.split(text):
        if "msgid" not in block:
            continue
        id_m = MSGID_RE.search(block)
        if not id_m:
            continue
        msgid = join_quoted(id_m.group(1))

        ctxt_m = MSGCTXT_RE.search(block)
        plural_m = MSGID_PLURAL_RE.search(block)
        flags_m = FLAGS_RE.search(block)
        flags = [f.strip() for f in flags_m.group(1).split(",")] if flags_m else []

        if msgid == "" and ctxt_m is None:
            # fejlec blokk
            header_str_m = MSGSTR_SIMPLE_RE.search(block)
            header_text = join_quoted(header_str_m.group(1)) if header_str_m else ""
            np_m = NPLURALS_RE.search(header_text)
            if np_m:
                header_nplurals = int(np_m.group(1))
            continue

        entry = {
            "msgctxt": join_quoted(ctxt_m.group(1)) if ctxt_m else None,
            "msgid": msgid,
            "flags": flags,
            "is_plural": plural_m is not None,
        }

        if plural_m:
            entry["msgid_plural"] = join_quoted(plural_m.group(1))
            entry["msgstr_n"] = {int(n): join_quoted(v) for n, v in MSGSTR_N_RE.findall(block)}
        else:
            str_m = MSGSTR_SIMPLE_RE.search(block)
            entry["msgstr"] = join_quoted(str_m.group(1)) if str_m else ""

        entries.append(entry)

    return entries, header_nplurals


def token_sets(text):
    if not text:
        return set(), 0
    named = set(NAMED_TOKEN_RE.findall(text))
    positional_count = len(POSITIONAL_TOKEN_RE.findall(text))
    return named, positional_count


def validate_file(path, glossary_entries=None):
    critical, major, minor, info = [], [], [], []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    entries, header_nplurals = parse_po(text)
    if not entries:
        major.append("Nem talalhato ervenyes msgid/msgstr bejegyzes (a fejlecen kivul).")
        return critical, major, minor, info

    seen = {}
    empty_count = 0
    fuzzy_count = 0
    pairs = []

    for entry in entries:
        key = (entry["msgctxt"], entry["msgid"])
        loc = f"msgctxt={entry['msgctxt']!r} " if entry["msgctxt"] else ""
        loc += f"msgid={entry['msgid'][:50]!r}"

        if key in seen:
            critical.append(f"Duplikalt (msgctxt, msgid) par: {loc} (elozo: {seen[key]})")
        else:
            seen[key] = loc

        is_fuzzy = "fuzzy" in entry["flags"]

        if entry["is_plural"]:
            msgstr_n = entry.get("msgstr_n", {})
            if header_nplurals is not None:
                expected = set(range(header_nplurals))
                got = set(msgstr_n.keys())
                if got != expected:
                    missing = expected - got
                    extra = got - expected
                    detail = []
                    if missing:
                        detail.append(f"hianyzo index(ek): {sorted(missing)}")
                    if extra:
                        detail.append(f"varatlan index(ek): {sorted(extra)}")
                    major.append(
                        f"{loc}: msgstr[N] agak szama nem egyezik a fejlec nplurals={header_nplurals} "
                        f"ertekevel -- {'; '.join(detail)}"
                    )

            src_named, src_pos = token_sets(entry["msgid"])
            plural_named, plural_pos = token_sets(entry.get("msgid_plural", ""))
            combined_src = entry["msgid"] + "\n" + entry.get("msgid_plural", "")
            for idx, val in sorted(msgstr_n.items()):
                if not val.strip():
                    empty_count += 1
                    continue
                pairs.append((combined_src, val, f"{loc} msgstr[{idx}]"))
                tgt_named, tgt_pos = token_sets(val)
                exp_named = src_named | plural_named
                if tgt_named != exp_named and exp_named:
                    if not (tgt_named <= exp_named or exp_named <= tgt_named) or tgt_named != exp_named:
                        missing = exp_named - tgt_named
                        extra = tgt_named - exp_named
                        if missing or extra:
                            major.append(
                                f"{loc} msgstr[{idx}]: nevesitett/szamozott placeholder eltere -- "
                                f"hianyzik: {sorted(missing)}, tobblet: {sorted(extra)}"
                            )
                exp_pos = max(src_pos, plural_pos)
                if exp_pos and tgt_pos != exp_pos:
                    major.append(
                        f"{loc} msgstr[{idx}]: pozicionalis (%s/%d) placeholder darabszam eltere "
                        f"(vart: {exp_pos}, talalt: {tgt_pos})"
                    )
                if is_fuzzy:
                    info.append(f"{loc} msgstr[{idx}]: 'fuzzy' jelzovel -- emberi/QA megerosites szukseges.")
                
                html_issues = check_html_tags(combined_src, val, f"{entry['msgctxt']}:{entry['msgid']}" if entry["msgctxt"] else entry["msgid"])
                major.extend(html_issues)
        else:
            msgstr = entry.get("msgstr", "")
            if not msgstr.strip():
                empty_count += 1
            else:
                pairs.append((entry["msgid"], msgstr, loc))
                src_named, src_pos = token_sets(entry["msgid"])
                tgt_named, tgt_pos = token_sets(msgstr)
                if src_named != tgt_named:
                    missing = src_named - tgt_named
                    extra = tgt_named - src_named
                    if missing or extra:
                        major.append(
                            f"{loc}: nevesitett/szamozott placeholder eltere -- "
                            f"hianyzik: {sorted(missing)}, tobblet: {sorted(extra)}"
                        )
                if src_pos and tgt_pos != src_pos:
                    major.append(
                        f"{loc}: pozicionalis (%s/%d) placeholder darabszam eltere "
                        f"(vart: {src_pos}, talalt: {tgt_pos})"
                    )
                if is_fuzzy:
                    fuzzy_count += 1
                
                html_issues = check_html_tags(entry["msgid"], msgstr, f"{entry['msgctxt']}:{entry['msgid']}" if entry["msgctxt"] else entry["msgid"])
                major.extend(html_issues)

    if glossary_entries:
        major.extend(check_protected_terms(pairs, glossary_entries))

    if empty_count:
        info.append(f"{empty_count} msgstr ures (fordítandó).")
    if fuzzy_count:
        info.append(f"{fuzzy_count} nem-ures bejegyzes 'fuzzy' jelzovel -- QA megerositesre var.")
    if header_nplurals is None:
        info.append("Nem talalhato 'Plural-Forms' / nplurals a fejlecben -- ha van plural bejegyzes, ezt potolni kell (ne talald ki magad).")

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
