"""
Unity Addressables CRC Hash Fixer for GameStringer CLI.

Recalculates CRC32 checksums for patched Unity AssetBundles (.bundle / .assets)
and updates catalog.json and *.hash files to ensure games load modified bundles cleanly.
"""

import os
import re
import json
import zlib
import time
from typing import List, Dict, Any, Tuple, Optional
from gamestringer.core.logger import logger
from gamestringer.core.backup import create_backup


def calculate_crc32(file_path: str) -> int:
    """Calculate unsigned 32-bit CRC32 checksum of a file."""
    crc = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def auto_update_addressables_crc(game_dir: str, modified_files: List[str]) -> List[str]:
    """
    Search for catalog.json or *.hash files in game_dir and update CRC32 entries for modified files.

    Returns list of updated log status messages.
    """
    updates_log = []
    if not game_dir or not os.path.exists(game_dir):
        return updates_log

    base_dir = os.path.abspath(game_dir)
    if os.path.isfile(base_dir):
        base_dir = os.path.dirname(base_dir)

    # Find catalog.json or *.hash files
    catalogs = []
    hash_files = []

    for root, _, files in os.walk(base_dir):
        for f in files:
            full = os.path.join(root, f)
            if f.lower() == "catalog.json" or f.lower().startswith("catalog_"):
                catalogs.append(full)
            elif f.lower().endswith(".hash"):
                hash_files.append(full)

    if not catalogs and not hash_files:
        return updates_log

    # 1. Process catalog.json files
    for cat_path in catalogs:
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)

            cat_updated = False
            for mod_file in modified_files:
                if not os.path.exists(mod_file):
                    continue
                filename = os.path.basename(mod_file)
                new_crc = calculate_crc32(mod_file)

                # Recursive search/update in JSON structure
                if _update_json_crc_entry(cat_data, filename, new_crc):
                    cat_updated = True
                    msg = f"Updated CRC32 ({new_crc}) for '{filename}' in '{os.path.basename(cat_path)}'"
                    logger.info(msg)
                    updates_log.append(msg)

            if cat_updated:
                create_backup(cat_path)
                with open(cat_path, "w", encoding="utf-8") as f:
                    json.dump(cat_data, f, indent=2)

        except Exception as err:
            logger.warning(f"[WARNING] Modified files detected but catalog.json CRC update failed: {err}. Run 'gamestringer fix-catalog --input \"{game_dir}\"' manually.")

    # 2. Process *.hash files
    for hash_path in hash_files:
        try:
            base_name = os.path.splitext(os.path.basename(hash_path))[0]
            for mod_file in modified_files:
                if not os.path.exists(mod_file):
                    continue
                if base_name.lower() in os.path.basename(mod_file).lower():
                    new_crc = calculate_crc32(mod_file)
                    create_backup(hash_path)
                    with open(hash_path, "w", encoding="utf-8") as f:
                        f.write(str(new_crc))
                    msg = f"Updated CRC32 hash file '{os.path.basename(hash_path)}' to {new_crc}"
                    logger.info(msg)
                    updates_log.append(msg)
        except Exception:
            pass

    return updates_log


def _update_json_crc_entry(data: Any, target_filename: str, new_crc: int) -> bool:
    """Recursively search and update CRC values matching target_filename in catalog.json data."""
    updated = False
    if isinstance(data, dict):
        # Check m_Crcs or Crc dictionary mappings
        for key, val in data.items():
            if key in ("m_Crcs", "m_ExtraData", "Crc", "crcs") and isinstance(val, (dict, list)):
                if isinstance(val, dict):
                    for sub_k in list(val.keys()):
                        if target_filename.lower() in str(sub_k).lower():
                            val[sub_k] = new_crc
                            updated = True
            elif target_filename.lower() in str(key).lower() and isinstance(val, int):
                data[key] = new_crc
                updated = True
            elif isinstance(val, (dict, list)):
                if _update_json_crc_entry(val, target_filename, new_crc):
                    updated = True

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            if isinstance(item, (dict, list)):
                if _update_json_crc_entry(item, target_filename, new_crc):
                    updated = True

    return updated


def fix_catalog_crc_command(input_path: str) -> Dict[str, Any]:
    """
    Standalone command for 'gamestringer fix-catalog --input <path>'.
    Scans for catalog.json and referenced asset files, recalculating and saving CRC32 hashes.
    """
    if not os.path.exists(input_path):
        raise ValueError(f"Input directory does not exist: {input_path}")

    base_dir = os.path.dirname(os.path.abspath(input_path)) if os.path.isfile(input_path) else os.path.abspath(input_path)

    # Find asset bundles and catalogs
    bundle_files = []
    catalogs = []

    for root, _, files in os.walk(base_dir):
        for f in files:
            full = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            if ext in (".bundle", ".assets", ".asset") or f.startswith("sharedassets"):
                bundle_files.append(full)
            elif f.lower() == "catalog.json" or f.lower().startswith("catalog_"):
                catalogs.append(full)

    if not catalogs:
        msg = f"No Addressables 'catalog.json' files found in '{input_path}'."
        logger.warning(msg)
        return {"catalog_found": False, "updated_files": [], "message": msg}

    updated_files = []
    for cat_path in catalogs:
        try:
            create_backup(cat_path)
            with open(cat_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)

            cat_updated = False
            for b_file in bundle_files:
                filename = os.path.basename(b_file)
                new_crc = calculate_crc32(b_file)
                if _update_json_crc_entry(cat_data, filename, new_crc):
                    cat_updated = True
                    updated_files.append(filename)
                    logger.info(f"Updated CRC32 ({new_crc}) for '{filename}' in '{cat_path}'")

            if cat_updated:
                with open(cat_path, "w", encoding="utf-8") as f:
                    json.dump(cat_data, f, indent=2)

        except Exception as err:
            logger.error(f"Error updating catalog '{cat_path}': {err}")

    summary_msg = f"Recalculated CRC32 for {len(updated_files)} asset file(s) across {len(catalogs)} Addressables catalog.json file(s)."
    logger.info(summary_msg)

    return {
        "catalog_found": True,
        "updated_files": updated_files,
        "catalogs": catalogs,
        "message": summary_msg
    }
