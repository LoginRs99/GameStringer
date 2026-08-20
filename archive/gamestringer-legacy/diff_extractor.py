"""
GameStringer CLI — Ground Truth Diff Extractor & Comparison Tool.

Performs a brute-force string extraction directly from Unity binary asset files
(.assets, .asset, .bundle, .resS) and compares it against an existing XLIFF output
to identify missing text, filter false negatives, and categorize why strings were missed.

Usage:
  python diff_extractor.py --game-dir "C:/Path/To/Game" --xliff "game.xliff"
"""

import os
import re
import sys
import argparse
import xml.etree.ElementTree as ET
from typing import Set, Dict, List, Tuple

# Printable UTF-8 / ASCII / Latin-1 / Extended Unicode pattern (4 to 500 characters)
ASCII_LATIN_PATTERN = re.compile(rb"[\x20-\x7E\xA0-\xFF\xC2-\xF4][\x20-\x7E\xA0-\xFF\x80-\xBF]{3,499}")

# Categorization Regexes
CAMEL_CASE_RE = re.compile(r"^[a-z]+[A-Z0-9][a-zA-Z0-9_]*$|^[A-Z][a-z0-9]+[A-Z0-9][a-zA-Z0-9_]*$")
ACCENT_RE = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ\u00C0-\u024F\u0400-\u04FF\u4E00-\u9FFF]")
PUNCT_RE = re.compile(r'[.,!?;:\-"\']')

# Known noise/code keywords for categorization
FIELD_BLACKLIST_KEYWORDS = {
    "position", "rotation", "scale", "guid", "uniqueid", "path", "hash", "crc",
    "fmod", "audio", "animator", "state", "clip", "method", "callback", "handler"
}

CODE_COMPONENT_KEYWORDS = {
    "system.", "unityengine.", "transform", "recttransform", "camera", "light",
    "rigidbody", "collider", "renderer", "monobehaviour", "gameobject", "scriptableobject"
}


def brute_force_extract_from_file(file_path: str) -> Set[str]:
    """Extract all printable text sequences of length 4-500 from a binary Unity asset file."""
    found_strings: Set[str] = set()

    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return found_strings

        # Process in 32MB chunks for memory safety with large bundle files
        chunk_size = 32 * 1024 * 1024
        with open(file_path, "rb") as f:
            overlap_bytes = b""
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                data = overlap_bytes + chunk
                # Keep last 500 bytes for cross-chunk string matches
                overlap_bytes = data[-500:] if len(data) > 500 else b""

                # 1. ASCII / UTF-8 extraction
                for match in ASCII_LATIN_PATTERN.finditer(data):
                    try:
                        raw_bytes = match.group(0)
                        text = raw_bytes.decode("utf-8", errors="ignore").strip()
                        if 4 <= len(text) <= 500 and not text.isdigit():
                            found_strings.add(text)
                    except Exception:
                        pass

                # 2. UTF-16LE extraction (common for Unity C# strings)
                try:
                    utf16_matches = re.findall(rb"(?:[\x20-\x7E\xA0-\xFF]\x00){4,500}", data)
                    for raw_u16 in utf16_matches:
                        text = raw_u16.decode("utf-16le", errors="ignore").strip()
                        if 4 <= len(text) <= 500 and not text.isdigit():
                            found_strings.add(text)
                except Exception:
                    pass

    except Exception as err:
        print(f"  [WARN] Failed to read '{os.path.basename(file_path)}': {err}")

    return found_strings


def scan_game_directory(game_dir: str) -> Set[str]:
    """Walk game folder and perform brute-force extraction on all Unity asset files."""
    all_brute_strings: Set[str] = set()

    valid_extensions = {".assets", ".asset", ".bundle", ".ress"}
    unity_header_magics = (b"UnityFS", b"UnityRaw", b"UnityWeb", b"UnityArchive")

    scanned_files = 0
    print(f"[1/3] Scanning game folder for Unity assets: {game_dir}...")

    for root, _, files in os.walk(game_dir):
        for f in files:
            full_path = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()

            is_unity_file = False
            if ext in valid_extensions or f.startswith("sharedassets") or f == "resources.assets" or f == "globalgamemanagers":
                is_unity_file = True
            elif not ext or ext == ".manifest":
                if f.endswith(".manifest"):
                    continue
                try:
                    with open(full_path, "rb") as check_f:
                        if check_f.read(8).startswith(unity_header_magics):
                            is_unity_file = True
                except Exception:
                    pass

            if is_unity_file:
                scanned_files += 1
                rel_path = os.path.relpath(full_path, game_dir)
                print(f"  • Extracted from: {rel_path}")
                extracted = brute_force_extract_from_file(full_path)
                all_brute_strings.update(extracted)

    print(f"[SUMMARY] Scanned {scanned_files} Unity asset file(s). Found {len(all_brute_strings)} unique brute-force string(s).\n")
    return all_brute_strings


def parse_xliff_sources(xliff_path: str) -> Set[str]:
    """Parse XLIFF 1.2 file and extract all <source> text strings."""
    print(f"[2/3] Parsing XLIFF file: {xliff_path}...")
    xliff_strings: Set[str] = set()

    if not os.path.exists(xliff_path):
        raise FileNotFoundError(f"XLIFF file not found: {xliff_path}")

    with open(xliff_path, "r", encoding="utf-8", errors="replace") as f:
        raw_xml = f.read()

    # Clean XML control chars
    cleaned_xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", raw_xml)
    root = ET.fromstring(cleaned_xml)

    for tu in root.iter():
        if tu.tag.endswith("trans-unit") or tu.tag == "trans-unit":
            for child in tu:
                tag_name = child.tag.split("}")[-1]
                if tag_name == "source" and child.text:
                    src_text = child.text.strip()
                    if src_text:
                        xliff_strings.add(src_text)

    print(f"[SUMMARY] Extracted {len(xliff_strings)} unique <source> string(s) from XLIFF.\n")
    return xliff_strings


def categorize_missing_string(s: str) -> str:
    """Categorize WHY a brute-force string was missed by the current pipeline filter."""
    s_lower = s.lower()

    if len(s) < 4:
        return "Too short"

    if CAMEL_CASE_RE.match(s) and " " not in s:
        return "CamelCase code"

    if any(k in s_lower for k in CODE_COMPONENT_KEYWORDS):
        return "Code component skipped"

    if any(k in s_lower for k in FIELD_BLACKLIST_KEYWORDS):
        return "Blacklisted field"

    if " " not in s and not PUNCT_RE.search(s) and not ACCENT_RE.search(s):
        return "No spaces/punctuation"

    return "Unknown / needs review"


def generate_comparison_report(
    brute_strings: Set[str],
    xliff_strings: Set[str],
    output_dir: str
) -> Tuple[str, str, str]:
    """Compare brute-force vs XLIFF strings and write outputs (txt files & markdown report)."""
    print("[3/3] Comparing extractions and generating report...")
    os.makedirs(output_dir, exist_ok=True)

    brute_file = os.path.join(output_dir, "brute_force_strings.txt")
    xliff_file = os.path.join(output_dir, "xliff_strings.txt")
    report_file = os.path.join(output_dir, "diff_report.md")

    # Write deduplicated text files
    with open(brute_file, "w", encoding="utf-8") as f:
        for s in sorted(brute_strings):
            f.write(s + "\n")

    with open(xliff_file, "w", encoding="utf-8") as f:
        for s in sorted(xliff_strings):
            f.write(s + "\n")

    # Sets comparison
    overlap = brute_strings & xliff_strings
    xliff_only = xliff_strings - brute_strings
    brute_only = brute_strings - xliff_strings

    # Categorize brute-only strings
    categories: Dict[str, List[str]] = {
        "Too short": [],
        "CamelCase code": [],
        "No spaces/punctuation": [],
        "Blacklisted field": [],
        "Code component skipped": [],
        "Unknown / needs review": [],
    }

    for s in brute_only:
        cat = categorize_missing_string(s)
        categories[cat].append(s)

    total_brute = len(brute_strings)
    total_xliff = len(xliff_strings)
    total_overlap = len(overlap)
    total_brute_only = len(brute_only)

    real_text_missed = len(categories["Unknown / needs review"])
    total_real_text = total_overlap + real_text_missed
    miss_rate = (real_text_missed / total_real_text * 100) if total_real_text > 0 else 0.0

    # Build Markdown Report
    report = []
    report.append("# GameStringer — Ground Truth String Extraction Diff Report\n")

    report.append("## C. Statistics Summary")
    report.append(f"- **Total Brute-Force Extracted Strings**: {total_brute:,}")
    report.append(f"- **Total XLIFF Extracted Strings**: {total_xliff:,}")
    report.append(f"- **Overlap (Extracted in Both)**: {total_overlap:,}")
    report.append(f"- **Brute-Force Only (Missed by XLIFF)**: {total_brute_only:,}")
    report.append(f"- **XLIFF Only (Non-asset / Metadata strings)**: {len(xliff_only):,}")
    report.append(f"- **Estimated Real Text Miss Rate**: **{miss_rate:.2f}%** ({real_text_missed:,} candidates need review out of {total_real_text:,})\n")

    report.append("### Categorization Breakdown of Missed Strings (`brute_force_only`)")
    report.append("| Reason Category | Count | Description |")
    report.append("|---|---|---|")
    for cat_name, items in categories.items():
        report.append(f"| **{cat_name}** | {len(items):,} | {get_cat_description(cat_name)} |")
    report.append("\n---\n")

    report.append("## B. Brute-Force-Only Strings (Missed by XLIFF)")
    report.append("> Review these strings to identify false negatives dropped by current filters.\n")

    for cat_name, items in categories.items():
        report.append(f"### Category: {cat_name} ({len(items):,} items)")
        if items:
            sample_items = sorted(items)[:30]
            report.append("```text")
            for item in sample_items:
                report.append(item)
            report.append("```")
            if len(items) > 30:
                report.append(f"_... and {len(items) - 30} more items._\n")
        else:
            report.append("_None_\n")

    report.append("\n---\n")

    report.append("## A. XLIFF-Only Strings (Top 50)")
    report.append("> Strings present in XLIFF but not matched in binary asset brute-force (likely metadata or formatted entries).\n")
    report.append("```text")
    for item in sorted(xliff_only)[:50]:
        report.append(item)
    report.append("```\n")

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print(f"Done! Created outputs in '{output_dir}':")
    print(f"  • {brute_file}")
    print(f"  • {xliff_file}")
    print(f"  • {report_file}\n")

    return brute_file, xliff_file, report_file


def get_cat_description(cat_name: str) -> str:
    descriptions = {
        "Too short": "Length < 4 characters",
        "CamelCase code": "Identifier matching camelCase code syntax with no spaces",
        "No spaces/punctuation": "Single word without spaces, punctuation, or accents",
        "Blacklisted field": "String matches blacklisted field keywords (position, guid, fmod, etc.)",
        "Code component skipped": "String matches engine/system namespace or class names",
        "Unknown / needs review": "Candidate for real game text (contains spaces, accents, or punctuation)",
    }
    return descriptions.get(cat_name, "")


def main():
    parser = argparse.ArgumentParser(
        description="GameStringer Diff Extractor — Compare Unity binary asset brute-force extractions against XLIFF output."
    )
    parser.add_argument("--game-dir", "-g", required=True, help="Path to Unity game directory containing asset files")
    parser.add_argument("--xliff", "-x", required=True, help="Path to XLIFF 1.2 file generated by GameStringer")
    parser.add_argument("--output-dir", "-o", default=".", help="Output directory for text files and diff_report.md (default: .)")

    args = parser.parse_args()

    game_dir = os.path.abspath(args.game_dir)
    xliff_path = os.path.abspath(args.xliff)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.exists(game_dir):
        print(f"[ERROR] Game directory does not exist: {game_dir}")
        sys.exit(1)

    if not os.path.exists(xliff_path):
        print(f"[ERROR] XLIFF file does not exist: {xliff_path}")
        sys.exit(1)

    brute_strings = scan_game_directory(game_dir)
    xliff_strings = parse_xliff_sources(xliff_path)

    generate_comparison_report(brute_strings, xliff_strings, output_dir)


if __name__ == "__main__":
    main()
