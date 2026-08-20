#!/usr/bin/env python3
"""
detect_format.py -- heurisztikus formátum-felismerő a loc-kit által
támogatott 7 batch-formátum egyikére.

Cél: ne kelljen 100%-ig "szemre" eldönteni, melyik format-*.md /
validate_*.py illik egy adott batch-fájlhoz -- ez a szkript ad egy
legjobb-tippet + indoklást. BIZONYTALAN esetben explicit jelzi, mit kell
manuálisan megerősíteni -- sosem dönt helyette csendben, mert két valós
eset (Unity két exportváltozata, UE4/5-po vs. sima gettext-po) a
kit saját format-*.md fájljai szerint is tartalmi ellenőrzést igényel,
amit ez a szkript csak heurisztikusan tud közelíteni.

Ez egy INFORMÁCIÓS eszköz, nem QA-kapu -- mindig 0-val lép ki, még ha
bizonytalan is a tipp (a bizonytalanságot a kimenet szövege jelzi, nem a
kilépési kód).

Használat:
    python3 detect_format.py <fájl1> [<fájl2> ...]
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

INI_SECTION_RE = re.compile(r"^\[\w+\]\s*$", re.MULTILINE)
INI_KV_RE = re.compile(r"^\w+\s*=", re.MULTILINE)
RENPY_TRANSLATE_RE = re.compile(r"^\s*translate\s+\w+\s+(strings|\w+)\s*:", re.MULTILINE)
UE_MSGCTXT_RE = re.compile(r'msgctxt\s+"([^"]*)"')


def sniff_encoding(raw_bytes):
    if raw_bytes[:2] == b"\xff\xfe":
        return "utf-16-le (BOM)"
    if raw_bytes[:2] == b"\xfe\xff":
        return "utf-16-be (BOM)"
    if raw_bytes[:3] == b"\xef\xbb\xbf":
        return "utf-8 (BOM)"
    sample = raw_bytes[:2000]
    if len(sample) > 20:
        odd_nulls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
        if odd_nulls > (len(sample) // 2) * 0.7:
            return "utf-16-le (BOM nélkül -- gyanús)"
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "ismeretlen/nem UTF-8"


def decode_best_effort(raw_bytes, enc_label):
    if "(BOM)" in enc_label and ("utf-16-le" in enc_label or "utf-16-be" in enc_label):
        # generikus "utf-16" kodek: FELISMERI a BOM-ot ES le is vágja --
        # explicit "utf-16-le"/"utf-16-be" NEM vágja le, egy \ufeff
        # karakter maradna a szöveg elején, ami elrontaná a sor-eleji (^)
        # regex-illesztést az első sorban.
        try:
            return raw_bytes.decode("utf-16")
        except UnicodeDecodeError:
            pass
    if "utf-16-le" in enc_label:
        # BOM nélküli gyanús eset -- itt nincs mit levágni
        try:
            return raw_bytes.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_bytes.decode("utf-8", errors="replace")


def detect_one(path):
    r = {"path": path, "guess": None, "confidence": "low", "reasons": [], "warnings": []}
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        r["guess"] = "HIBA"
        r["warnings"].append(f"Nem olvasható: {e}")
        return r

    lower = path.lower()
    enc = sniff_encoding(raw)
    text = decode_best_effort(raw, enc)

    # --- JSON -> generic-kv or uabea_json ---
    if lower.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            r["guess"] = "HIBA"
            r["warnings"].append(f".json kiterjesztés, de nem érvényes JSON: {e}")
            return r
        if isinstance(data, dict) and ("m_Script" in data or "m_Name" in data):
            r["guess"] = "uabea_json"
            r["confidence"] = "high"
            r["reasons"].append("Érvényes Unity UABEA JSON export ('m_Name'/'m_Script' mezőkkel).")
        elif isinstance(data, list) and data and isinstance(data[0], dict) and {"id", "source", "target"} <= data[0].keys():
            r["guess"] = "generic-kv"
            r["confidence"] = "high"
            r["reasons"].append("JSON tömb, elemek 'id'/'source'/'target' kulcsokkal -- format-generic-kv.md.")
        else:
            r["guess"] = "uabea_json"
            r["confidence"] = "medium"
            r["reasons"].append("Generikus JSON fájl UABEA/Unity struktúrához.")
        return r

    # --- .rpy -> Ren'Py ---
    if lower.endswith(".rpy"):
        if RENPY_TRANSLATE_RE.search(text):
            r["guess"] = "renpy"
            r["confidence"] = "high"
            r["reasons"].append("`.rpy` kiterjesztés és 'translate <nyelv> ...:' minta is megvan -- format-renpy.md.")
        else:
            r["guess"] = "renpy (bizonytalan)"
            r["warnings"].append("`.rpy` kiterjesztés, de nincs 'translate <nyelv> ...:' minta -- lehet, hogy ez forrás-script, nem legenerált fordítási batch.")
        return r

    # --- .csv -> Unity Localization csomag vs. egyéb ---
    if lower.endswith(".csv"):
        first_line = text.splitlines()[0] if text.splitlines() else ""
        header_cells = [c.strip().strip('"') for c in first_line.split(",")]
        if "Key" in header_cells and "Id" in header_cells:
            r["guess"] = "unity-csv"
            r["confidence"] = "high"
            r["reasons"].append(f"CSV fejléc tartalmazza a 'Key' és 'Id' oszlopot ({header_cells}) -- Unity Localization csomag export, format-unity.md.")
        else:
            r["guess"] = "ISMERETLEN (CSV, de nem Unity Localization csomag fejléc)"
            r["warnings"].append(
                f"CSV, de a fejléc ({header_cells}) nem a várt Unity Localization csomag mintát követi -- "
                f"lehet legacy/I2 export vagy más eszköz (ld. format-unity.md 'két variáns' figyelmeztetése), ellenőrizd manuálisan."
            )
        return r

    # --- .xlf / .xliff -> Weblate XLIFF ---
    if lower.endswith(".xlf") or lower.endswith(".xliff"):
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            r["guess"] = "HIBA"
            r["warnings"].append(f".xlf/.xliff kiterjesztés, de nem jólformált XML: {e}")
            return r
        tag = root.tag
        if "xliff" in tag.lower():
            r["guess"] = "weblate-xliff"
            version = root.get("version") or ""
            if "1.1" in tag or version == "1.1":
                r["confidence"] = "high"
                r["reasons"].append("XML gyökér <xliff>, XLIFF 1.1 névtér/verzió -- format-weblate-xliff.md illeszkedik.")
            else:
                r["confidence"] = "medium"
                r["warnings"].append(f"<xliff> gyökér, de a névtér/verzió ({tag!r}, version={version!r}) nem egyértelműen 1.1 -- format-weblate-xliff.md kifejezetten 1.1-re épül, ellenőrizd az export-verziót Weblate-ben.")
        else:
            r["guess"] = "ISMERETLEN (XML, de nem <xliff> gyökér)"
            r["warnings"].append(f"XML gyökérelem: {tag!r} -- nem xliff, ellenőrizd manuálisan.")
        return r

    # --- .po -> UE4/5 vs. sima gettext ---
    if lower.endswith(".po"):
        has_plural = "msgid_plural" in text
        plural_forms_m = re.search(r"Plural-Forms:\s*nplurals\s*=\s*(\d+)", text)
        ctxt_values = UE_MSGCTXT_RE.findall(text)
        ue_like = [v for v in ctxt_values if re.match(r"^[^\s,]+,\S+", v)]

        if has_plural or (plural_forms_m and int(plural_forms_m.group(1)) > 1 and not ue_like):
            r["guess"] = "po-gettext"
            r["confidence"] = "high" if has_plural else "medium"
            r["reasons"].append("Valódi 'msgid_plural' és/vagy többértékű Plural-Forms fejléc, UE-mintázatú msgctxt nélkül -- format-po-gettext.md.")
        elif ctxt_values and len(ue_like) / len(ctxt_values) > 0.7:
            r["guess"] = "ue4-ue5-po"
            r["confidence"] = "medium"
            r["reasons"].append(
                f"msgctxt bejegyzések többsége 'namespace,key' mintát követ ({len(ue_like)}/{len(ctxt_values)}), "
                f"nincs valódi msgid_plural -- valószínűleg format-ue4-ue5.md, de a minta nem 100%-ig egyértelmű, erősítsd meg."
            )
        else:
            r["guess"] = "ISMERETLEN (.po, de sem a gettext-, sem az UE-minta nem egyértelmű)"
            r["warnings"].append("`.po` fájl, de sem a gettext-plural, sem az UE msgctxt-minta nem egyértelmű -- nyisd meg és döntsd el format-po-gettext.md vagy format-ue4-ue5.md alapján.")
        return r

    # --- INI-szerű (UE3), kiterjesztéstől függetlenül -- a valódi kiterjesztés
    # projektenként változó (.int / 3-betűs nyelvkód), ld. format-ue3.md ---
    if INI_SECTION_RE.search(text) and INI_KV_RE.search(text):
        r["guess"] = "ue3-int"
        if "utf-16-le" in enc:
            r["confidence"] = "high"
            r["reasons"].append(f"INI-szerű [Szekció]/Kulcs=Érték szerkezet, kódolás: {enc} -- format-ue3.md.")
        else:
            r["confidence"] = "medium"
            r["warnings"].append(
                f"INI-szerű UE3-mintázat, de a kódolás ({enc}) NEM utf-16-le -- ez CRITICAL hiba "
                f"lenne UE3 fájlként (a validate_ue3_int.py úgyis elkapná), de előbb erősítsd meg, "
                f"hogy tényleg UE3 fájlról van szó és nem egy hasonló szerkezetű .ini."
            )
        return r

    ext = path.rsplit(".", 1)[-1] if "." in path else "(nincs kiterjesztés)"
    r["guess"] = "ISMERETLEN"
    r["warnings"].append(f"Egyik ismert minta sem illeszkedik egyértelműen (kiterjesztés: {ext}, kódolás: {enc}) -- nézd át kézzel, esetleg új adapter kell.")
    return r


def main(argv):
    if not argv:
        print(__doc__)
        return 0

    for path in argv:
        r = detect_one(path)
        print(f"=== {path} ===")
        print(f"  Tipp: {r['guess']}  (bizalom: {r['confidence']})")
        for reason in r["reasons"]:
            print(f"  + {reason}")
        for warning in r["warnings"]:
            print(f"  ! {warning}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
