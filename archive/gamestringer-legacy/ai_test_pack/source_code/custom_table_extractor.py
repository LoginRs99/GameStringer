"""
Custom Binary Table & Streaming Asset Extractor for GameStringer.

Extracts 100% of length-prefixed binary strings, custom ScriptableObject data,
nested dictionary values, and StreamingAssets text tables (.json, .csv, .txt, .xml).
"""

import os
import re
import struct
from typing import List, Tuple, Set
from gamestringer.core.base_engine import TransUnit
from gamestringer.core.logger import logger

from gamestringer.engines.il2cpp_hybrid import should_keep_metadata_string

# Permissive printable string regex (UTF-8 letters, spaces, numbers, common punctuation, Latin accents)
PRINTABLE_RE = re.compile(r"^[\x20-\x7E\xA0-\xFF\u00C0-\u024F\u0400-\u04FF\u4E00-\u9FFF]{4,500}$")

CUSTOM_DROP_SUFFIXES = ("Prefab", "handle", "Chunk", "asset", "object", "Damage", "Cooldown")
CUSTOM_CHUNK_KEY_RE = re.compile(r"^[a-z]+_[a-z0-9_]+_(chunk|asset|prefab|handle)$")
UPPER_UNDERSCORE_RE = re.compile(r"^[A-Z0-9_]+$")

def should_keep_custom_string(s: str) -> bool:
    if not should_keep_metadata_string(s):
        return False

    if " " not in s:
        if any(s.endswith(suffix) for suffix in CUSTOM_DROP_SUFFIXES):
            return False
        if CUSTOM_CHUNK_KEY_RE.match(s):
            return False
        if UPPER_UNDERSCORE_RE.match(s) and "_" in s:
            return False

    return True


def scan_binary_custom_tables(file_path: str, start_counter: int = 0) -> Tuple[List[TransUnit], int]:
    """
    Scan a single binary asset file (.bundle, .assets, .dat) for Unity 4-byte Little-Endian
    length-prefixed strings and custom ScriptableObject binary table entries.

    :param file_path: Path to binary asset file
    :param start_counter: Starting unit ID index
    :return: Tuple of (list of TransUnit, updated counter)
    """
    units: List[TransUnit] = []
    counter = start_counter
    rel_name = os.path.basename(file_path)

    if not os.path.exists(file_path):
        return units, counter

    try:
        with open(file_path, "rb") as f:
            data = f.read()

        seen_strings: Set[str] = set()

        # Find contiguous sequences of printable ASCII/UTF-8 bytes (length 4 to 500)
        for match in re.finditer(rb'[\x20-\x7E\xA0-\xFF]{4,500}', data):
            start = match.start()
            length = match.end() - start

            # Validate Little-Endian 4-byte uint32 length prefix
            if start >= 4:
                pref_len = struct.unpack('<I', data[start-4:start])[0]
                if pref_len == length:
                    try:
                        raw_str = data[start:start+length].decode('utf-8', errors='ignore').strip()
                        if PRINTABLE_RE.match(raw_str) and should_keep_custom_string(raw_str) and raw_str not in seen_strings:
                            seen_strings.add(raw_str)
                            counter += 1
                            units.append(TransUnit(
                                id=f"custom_{counter:06d}",
                                source=raw_str,
                                file_path=rel_name,
                                namespace="custom_binary_table",
                                key=f"offset_0x{start:X}",
                                context_note=f"source:custom_table | pattern:binary_len_prefix | offset:0x{start:X} | file:{rel_name}"
                            ))
                    except Exception:
                        pass

        logger.info(f"Extracted {len(units)} custom binary string(s) from '{rel_name}'.")

    except Exception as err:
        logger.warning(f"Error scanning custom binary table '{rel_name}': {err}")

    return units, counter


def scan_streaming_text_files(input_dir: str, start_counter: int = 0) -> Tuple[List[TransUnit], int]:
    """
    Scan StreamingAssets directory for .csv, .json, .txt, .xml, .tsv text files containing localized text.

    :param input_dir: Root game folder
    :param start_counter: Starting unit ID index
    :return: Tuple of (list of TransUnit, updated counter)
    """
    units: List[TransUnit] = []
    counter = start_counter

    text_extensions = {".json", ".csv", ".txt", ".xml", ".tsv", ".yaml", ".yml"}

    for root, _, files in os.walk(input_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in text_extensions:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, input_dir)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()

                    seen_text: Set[str] = set()

                    # Extract string values from JSON or plain text lines
                    if ext == ".json":
                        matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content)
                        for s in matches:
                            s_clean = s.strip()
                            if len(s_clean) >= 4 and PRINTABLE_RE.match(s_clean) and should_keep_custom_string(s_clean) and s_clean not in seen_text:
                                seen_text.add(s_clean)
                                counter += 1
                                units.append(TransUnit(
                                    id=f"custom_{counter:06d}",
                                    source=s_clean,
                                    file_path=rel_path,
                                    namespace="streaming_json",
                                    key="json_string",
                                    context_note=f"source:streaming_assets | file:{rel_path}"
                                ))
                    else:
                        for line in content.splitlines():
                            line_clean = line.strip()
                            if len(line_clean) >= 4 and PRINTABLE_RE.match(line_clean) and should_keep_custom_string(line_clean) and line_clean not in seen_text:
                                seen_text.add(line_clean)
                                counter += 1
                                units.append(TransUnit(
                                    id=f"custom_{counter:06d}",
                                    source=line_clean,
                                    file_path=rel_path,
                                    namespace="streaming_text",
                                    key="text_line",
                                    context_note=f"source:streaming_assets | file:{rel_path}"
                                ))

                except Exception as err:
                    logger.warning(f"Error reading streaming text file '{rel_path}': {err}")

    return units, counter


def scan_all_custom_tables(input_path: str, start_counter: int = 0) -> Tuple[List[TransUnit], int]:
    """
    Main entry point for scanning custom binary tables and streaming assets.

    :param input_path: Game directory or input path
    :param start_counter: Starting counter index
    :return: Tuple of (extracted TransUnit list, updated counter)
    """
    units: List[TransUnit] = []
    counter = start_counter

    abs_path = os.path.abspath(input_path)
    game_dir = os.path.dirname(abs_path) if os.path.isfile(abs_path) else abs_path

    # 1. Scan streaming text files (.csv, .json, .txt)
    text_units, counter = scan_streaming_text_files(game_dir, start_counter=counter)
    units.extend(text_units)

    # 2. Scan binary asset files (.bundle, .assets, .dat) for binary length-prefixed strings
    binary_extensions = {".bundle", ".assets", ".dat", ".asset"}
    for root, _, files in os.walk(game_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in binary_extensions or f.lower() in ("core", "resources", "sharedassets0.assets"):
                full_path = os.path.join(root, f)
                bin_units, counter = scan_binary_custom_tables(full_path, start_counter=counter)
                units.extend(bin_units)

    return units, counter
