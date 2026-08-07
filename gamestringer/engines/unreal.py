"""
Unreal Engine Text Localization Resource (.locres) Adapter for GameStringer CLI.

Supports parsing and repatching Unreal Engine 4 and 5 binary .locres files
across Legacy (v0), Compact (v1), Optimized (v2), and CRC32 (v3) format specs.
Uses pure Python binary struct parsing without native C dependencies.
"""

import os
import struct
from typing import List, Optional, Tuple, Dict, Any
from gamestringer.core.base_engine import BaseEngine, TransUnit, validate_smart_tokens
from gamestringer.core.xliff_exporter import export_xliff, parse_xliff
from gamestringer.core.backup import create_backup
from gamestringer.core.logger import logger

# FGuid magic for LocRes v1+: FGuid(0x7574140E, 0xFC034A67, 0x9D90154A, 0x1B7F37C3)
LOCRES_MAGIC = bytes([
    0x0E, 0x14, 0x74, 0x75,
    0x67, 0x4A, 0x03, 0xFC,
    0x4A, 0x15, 0x90, 0x9D,
    0xC3, 0x37, 0x7F, 0x1B,
])


class UnrealEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "unreal"

    @property
    def description(self) -> str:
        return "Unreal Engine LocRes Binary Parser/Patcher (.locres)"

    @property
    def supported_extensions(self) -> List[str]:
        return [".locres"]

    def detect(self, input_path: str) -> bool:
        if not os.path.exists(input_path):
            return False

        if os.path.isfile(input_path):
            if input_path.lower().endswith(".locres"):
                return True
            try:
                with open(input_path, "rb") as f:
                    header = f.read(16)
                    return header == LOCRES_MAGIC
            except Exception:
                return False

        if os.path.isdir(input_path):
            for root, _, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith(".locres"):
                        return True

        return False

    def extract(self, input_path: str, output_xliff_path: str, dry_run: bool = False) -> str:
        locres_files = self._find_locres_files(input_path)
        if not locres_files:
            raise ValueError(f"No .locres files found in input path: {input_path}")

        all_units: List[TransUnit] = []
        processed_count = 0
        skipped_count = 0

        for full_path, rel_path in locres_files:
            try:
                with open(full_path, "rb") as f:
                    data = f.read()

                version, entries = self._parse_locres_binary(data)

                for ns, key, source_hash, val in entries:
                    if not val or not val.strip():
                        continue
                    unit_id = f"{ns}::{key}" if ns else key
                    all_units.append(TransUnit(
                        id=unit_id,
                        source=val,
                        file_path=rel_path,
                        namespace=ns,
                        key=key,
                        extra_metadata={"source_hash": source_hash, "version": version},
                    ))
                processed_count += 1
            except Exception as err:
                logger.warning(f"Skipping corrupt or unreadable file '{rel_path}': {err}")
                skipped_count += 1

        summary = f"Processed {processed_count} file(s), found {len(all_units)} string(s) ({skipped_count} skipped due to corruption/errors)."

        if dry_run:
            logger.info(f"[DRY-RUN] {summary} No XLIFF file written.")
            return f"[DRY-RUN] {summary}"

        if not all_units:
            raise ValueError(f"No extractable text entries found. {summary}")

        export_xliff(
            units=all_units,
            output_path=output_xliff_path,
            source_lang="en",
            target_lang="it",
            engine_name=self.name,
        )
        logger.info(f"Extracted strings saved to: {output_xliff_path}")
        return f"Extracted {len(all_units)} string(s) to '{output_xliff_path}'. {summary}"

    def patch(self, input_path: str, xliff_path: str, output_path: Optional[str] = None) -> str:
        units = parse_xliff(xliff_path)
        if not units:
            raise ValueError(f"No translatable units found in XLIFF file: {xliff_path}")

        locres_files = self._find_locres_files(input_path)
        if not locres_files:
            raise ValueError(f"No .locres files found in input path to patch: {input_path}")

        # Validate Smart String tokens before patching
        for u in units:
            if u.target and u.target.strip():
                missing_tokens = validate_smart_tokens(u.source, u.target)
                if missing_tokens:
                    logger.warning(f"Smart token mismatch in unit [{u.id}]: missing tokens {missing_tokens}. Proceeding with patch.")

        translation_map: Dict[Tuple[str, str], str] = {}
        for u in units:
            target_str = u.target if (u.target and u.target.strip()) else u.source
            ns = u.namespace or ""
            k = u.key or ""
            if not k and "::" in u.id:
                parts = u.id.split("::", 1)
                ns, k = parts[0], parts[1]
            elif not k:
                k = u.id

            translation_map[(ns, k)] = target_str

        patched_count = 0

        for full_path, rel_path in locres_files:
            backup_file = create_backup(full_path)

            with open(full_path, "rb") as f:
                data = f.read()

            version, entries = self._parse_locres_binary(data)

            patched_entries = []
            for ns, key, source_hash, orig_val in entries:
                new_val = translation_map.get((ns, key), orig_val)
                patched_entries.append((ns, key, source_hash, new_val))
                if new_val != orig_val:
                    patched_count += 1

            new_binary = self._write_locres_v0(patched_entries)

            target_out_path = output_path if (output_path and os.path.isfile(output_path)) else full_path
            if output_path and os.path.isdir(output_path):
                target_out_path = os.path.join(output_path, os.path.basename(full_path))

            os.makedirs(os.path.dirname(os.path.abspath(target_out_path)), exist_ok=True)
            with open(target_out_path, "wb") as f:
                f.write(new_binary)

        return f"Successfully patched {patched_count} strings across {len(locres_files)} .locres file(s)."

    # ─────────────────────────────────────────────────────────────
    # LOCRES BINARY PARSING & WRITING LOGIC
    # ─────────────────────────────────────────────────────────────

    def _find_locres_files(self, input_path: str) -> List[Tuple[str, str]]:
        results = []
        if os.path.isfile(input_path):
            results.append((os.path.abspath(input_path), os.path.basename(input_path)))
            return results

        base_dir = os.path.abspath(input_path)
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.lower().endswith(".locres"):
                    full = os.path.join(root, file)
                    rel = os.path.relpath(full, base_dir)
                    results.append((full, rel))

        results.sort(key=lambda x: x[1])
        return results

    def _read_i32(self, data: bytes, offset: int) -> Tuple[int, int]:
        val = struct.unpack_from("<i", data, offset)[0]
        return val, offset + 4

    def _read_u32(self, data: bytes, offset: int) -> Tuple[int, int]:
        val = struct.unpack_from("<I", data, offset)[0]
        return val, offset + 4

    def _read_i64(self, data: bytes, offset: int) -> Tuple[int, int]:
        val = struct.unpack_from("<q", data, offset)[0]
        return val, offset + 8

    def _read_fstring(self, data: bytes, offset: int) -> Tuple[str, int]:
        length, offset = self._read_i32(data, offset)
        if length == 0:
            return "", offset

        if length > 0:
            raw_bytes = data[offset : offset + length]
            offset += length
            if raw_bytes and raw_bytes[-1] == 0:
                raw_bytes = raw_bytes[:-1]
            return raw_bytes.decode("latin-1"), offset
        else:
            u16_units = -length
            byte_len = u16_units * 2
            raw_bytes = data[offset : offset + byte_len]
            offset += byte_len
            u16_str = raw_bytes.decode("utf-16le")
            if u16_str and u16_str[-1] == "\x00":
                u16_str = u16_str[:-1]
            return u16_str, offset

    def _write_fstring(self, buf: bytearray, s: str):
        if not s:
            buf.extend(struct.pack("<i", 0))
            return

        if s.isascii():
            encoded = s.encode("ascii") + b"\x00"
            buf.extend(struct.pack("<i", len(encoded)))
            buf.extend(encoded)
        else:
            encoded = s.encode("utf-16le") + b"\x00\x00"
            units_count = -(len(encoded) // 2)
            buf.extend(struct.pack("<i", units_count))
            buf.extend(encoded)

    def _parse_locres_binary(self, data: bytes) -> Tuple[int, List[Tuple[str, str, int, str]]]:
        offset = 0

        if len(data) >= 16 and data[0:16] == LOCRES_MAGIC:
            offset = 16
            version = data[offset]
            offset += 1
        else:
            version = 0

        if version > 3:
            raise ValueError(f"Unsupported LocRes version {version} (max supported version is 3)")

        string_array: List[str] = []

        if version >= 1:
            array_offset, offset = self._read_i64(data, offset)
            if array_offset >= 0 and array_offset < len(data):
                arr_off = array_offset
                str_count, arr_off = self._read_i32(data, arr_off)
                for _ in range(str_count):
                    s_val, arr_off = self._read_fstring(data, arr_off)
                    if version >= 2:
                        _ref_count, arr_off = self._read_i32(data, arr_off)
                    string_array.append(s_val)

        if version >= 3:
            _total_entries, offset = self._read_u32(data, offset)

        namespace_count, offset = self._read_i32(data, offset)
        entries: List[Tuple[str, str, int, str]] = []

        for _ in range(namespace_count):
            if version >= 2:
                _ns_hash, offset = self._read_u32(data, offset)

            namespace_key, offset = self._read_fstring(data, offset)
            entry_count, offset = self._read_i32(data, offset)

            for _ in range(entry_count):
                if version >= 2:
                    _key_hash, offset = self._read_u32(data, offset)

                entry_key, offset = self._read_fstring(data, offset)
                source_hash, offset = self._read_u32(data, offset)

                if version >= 1:
                    str_idx, offset = self._read_i32(data, offset)
                    if 0 <= str_idx < len(string_array):
                        val_str = string_array[str_idx]
                    else:
                        val_str = ""
                else:
                    val_str, offset = self._read_fstring(data, offset)

                entries.append((namespace_key, entry_key, source_hash, val_str))

        return version, entries

    def _write_locres_v0(self, entries: List[Tuple[str, str, int, str]]) -> bytes:
        buf = bytearray()

        ns_map: Dict[str, List[Tuple[str, int, str]]] = {}
        for ns, k, src_hash, val in entries:
            if ns not in ns_map:
                ns_map[ns] = []
            ns_map[ns].append((k, src_hash, val))

        buf.extend(struct.pack("<i", len(ns_map)))

        for ns_name, ns_entries in ns_map.items():
            self._write_fstring(buf, ns_name)
            buf.extend(struct.pack("<i", len(ns_entries)))

            for k_name, src_hash, val_str in ns_entries:
                self._write_fstring(buf, k_name)
                buf.extend(struct.pack("<I", src_hash))
                self._write_fstring(buf, val_str)

        return bytes(buf)
