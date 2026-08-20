"""
Managed C# Assembly & IL2CPP DLL Scanner for GameStringer.

Extracts hardcoded C# string literals, field values, and metadata strings
from Managed assembly DLLs (Assembly-CSharp.dll) and IL2CPP runtimes.
"""

import os
import re
import struct
from typing import List, Tuple, Set, Optional
from gamestringer.core.base_engine import TransUnit
from gamestringer.core.logger import logger
from gamestringer.engines.il2cpp_hybrid import should_keep_metadata_string, clean_control_chars

# Standard Unity/System DLLs to skip during Mono scanning to avoid engine internal noise
ENGINE_DLL_EXCLUSIONS = {
    "unityengine.dll", "mscorlib.dll", "system.dll", "system.core.dll", "system.xml.dll",
    "mono.posix.dll", "mono.security.dll", "rewired_core.dll", "rewired_windows.dll",
    "dotween.dll", "pathfinding.ionic.zip.reduced.dll", "pathfinding.jsonfx.dll",
    "rotorz.dotnet-exception-utils.dll", "rotorz.dotnet-type-utils.dll",
    "rotorz.unity3d-reorderable-list.dll", "rotorz.unity3d-utils.dll", "amplifycolor.dll"
}


def detect_runtime_type(input_path: str) -> Tuple[str, List[str]]:
    """
    Detect whether target game uses Mono runtime (Assembly-CSharp.dll) or IL2CPP runtime (GameAssembly.dll).

    :param input_path: Root game directory or file path
    :return: Tuple of (runtime_type, list_of_target_files)
    """
    abs_path = os.path.abspath(input_path)
    game_dir = os.path.dirname(abs_path) if os.path.isfile(abs_path) else abs_path

    mono_dlls = []
    il2cpp_files = []

    # Search for Managed directory or Assembly-CSharp.dll
    for root, _, files in os.walk(game_dir):
        for f in files:
            f_lower = f.lower()
            full = os.path.join(root, f)

            if f_lower == "assembly-csharp.dll":
                mono_dlls.append(full)
            elif f_lower.endswith(".dll") and "managed" in root.lower():
                if not f_lower.startswith("unityengine.") and not f_lower.startswith("system.") and f_lower not in ENGINE_DLL_EXCLUSIONS:
                    mono_dlls.append(full)
            elif f_lower in ("gameassembly.dll", "libil2cpp.so", "global-metadata.dat"):
                il2cpp_files.append(full)

    if mono_dlls:
        logger.info(f"[RUNTIME DETECTED] Mono C# Runtime — found {len(mono_dlls)} managed assembly DLL(s).")
        return "mono", mono_dlls
    elif il2cpp_files:
        logger.info(f"[RUNTIME DETECTED] Unity IL2CPP Runtime — found IL2CPP metadata binary files.")
        return "il2cpp", il2cpp_files

    logger.info("[RUNTIME DETECTED] Unknown / standard asset runtime.")
    return "unknown", []


def scan_mono_dll_strings(dll_path: str, start_counter: int = 0) -> Tuple[List[TransUnit], int]:
    """
    Scan a managed .NET C# assembly DLL (Assembly-CSharp.dll) for UTF-16LE and UTF-8 string literals.

    :param dll_path: Path to .dll binary file
    :param start_counter: Starting unit ID index
    :return: Tuple of (list of TransUnit, updated counter)
    """
    units: List[TransUnit] = []
    counter = start_counter
    dll_name = os.path.basename(dll_path)

    if not os.path.exists(dll_path):
        return units, counter

    try:
        with open(dll_path, "rb") as f:
            data = f.read()

        seen_strings: Set[str] = set()

        # 1. UTF-16LE String Literal extraction (C# ldstr opcode literals)
        utf16_matches = re.findall(rb"(?:[\x20-\x7E\xA0-\xFF]\x00){2,500}", data)
        for raw_bytes in utf16_matches:
            try:
                s = raw_bytes.decode("utf-16le", errors="ignore").strip()
                s_clean = clean_control_chars(s)

                if s_clean and s_clean not in seen_strings:
                    if should_keep_metadata_string(s_clean):
                        seen_strings.add(s_clean)
                        counter += 1
                        units.append(TransUnit(
                            id=f"dll_{counter:06d}",
                            source=s_clean,
                            file_path=dll_name,
                            namespace=dll_name.replace(".dll", ""),
                            key="ldstr_utf16",
                            context_note=f"source:managed_dll | file:{dll_name} | encoding:utf16",
                        ))
            except Exception:
                pass

        # 2. UTF-8 String Literal extraction fallback
        utf8_matches = re.findall(rb"[\x20-\x7E\xC2-\xF4][\x20-\x7E\xA0-\xFF\x80-\xBF]{3,499}", data)
        for raw_bytes in utf8_matches:
            try:
                s = raw_bytes.decode("utf-8", errors="ignore").strip()
                s_clean = clean_control_chars(s)

                if s_clean and s_clean not in seen_strings:
                    if should_keep_metadata_string(s_clean):
                        seen_strings.add(s_clean)
                        counter += 1
                        units.append(TransUnit(
                            id=f"dll_{counter:06d}",
                            source=s_clean,
                            file_path=dll_name,
                            namespace=dll_name.replace(".dll", ""),
                            key="ldstr_utf8",
                            context_note=f"source:managed_dll | file:{dll_name} | encoding:utf8",
                        ))
            except Exception:
                pass

        logger.info(f"Extracted {len(units)} managed string literal(s) from '{dll_name}'.")

    except Exception as err:
        logger.warning(f"Error scanning DLL '{dll_name}': {err}")

    return units, counter


def scan_game_dlls(input_path: str, start_counter: int = 0) -> Tuple[List[TransUnit], int]:
    """
    Main entry point for scanning game managed assemblies and runtime DLLs.

    :param input_path: Root game folder or directory
    :param start_counter: Starting unit ID index
    :return: Tuple of (extracted TransUnits, updated counter)
    """
    units: List[TransUnit] = []
    counter = start_counter

    runtime_type, target_files = detect_runtime_type(input_path)

    if runtime_type == "mono":
        for dll_file in target_files:
            dll_units, counter = scan_mono_dll_strings(dll_file, counter)
            units.extend(dll_units)

    return units, counter
