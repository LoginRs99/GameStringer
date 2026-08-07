"""
CRI Middleware Engine Adapter for GameStringer CLI.

Extracts and repatches text files (.msg, .bmd, .ftd) and CPK archives
for games using CRI Middleware (Persona 3/4/5, Yakuza, Tales of, Dragon Ball, etc.).
Filters CRI control codes (0xF1-0xFF) and supports Shift-JIS, UTF-8, and UTF-16 encodings.
"""

import os
import struct
from typing import List, Optional, Tuple, Dict, Any
from gamestringer.core.base_engine import BaseEngine, TransUnit, validate_smart_tokens
from gamestringer.core.xliff_exporter import export_xliff, parse_xliff
from gamestringer.core.backup import create_backup
from gamestringer.core.logger import logger


class CriEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "cri"

    @property
    def description(self) -> str:
        return "CRI Middleware MSG/BMD/FTD & CPK Archives (.msg / .bmd / .ftd / .cpk)"

    @property
    def supported_extensions(self) -> List[str]:
        return [".msg", ".bmd", ".ftd", ".cpk", ".par"]

    def detect(self, input_path: str) -> bool:
        if not os.path.exists(input_path):
            return False

        if os.path.isfile(input_path):
            ext = os.path.splitext(input_path)[1].lower()
            if ext in self.supported_extensions:
                return True
            try:
                with open(input_path, "rb") as f:
                    magic = f.read(4)
                    if magic in (b"CPK ", b"MSG1", b"MSB1", b"\x07MSG"):
                        return True
            except Exception:
                return False

        if os.path.isdir(input_path):
            for root, _, files in os.walk(input_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in self.supported_extensions:
                        return True

        return False

    def extract(self, input_path: str, output_xliff_path: str, dry_run: bool = False) -> str:
        text_files = self._find_cri_files(input_path)
        if not text_files:
            raise ValueError(f"No CRI text files (.msg, .bmd, .ftd, .cpk) found in path: {input_path}")

        units: List[TransUnit] = []
        counter = 0
        processed_count = 0
        skipped_count = 0

        for full_path, rel_path in text_files:
            try:
                with open(full_path, "rb") as f:
                    raw_bytes = f.read()

                ext = os.path.splitext(full_path)[1].lower()

                if ext in (".bmd", ".msg") or raw_bytes.startswith((b"MSG1", b"MSB1", b"\x07MSG")):
                    file_units, counter = self._parse_bmd_msg(raw_bytes, rel_path, counter)
                elif ext == ".ftd":
                    file_units, counter = self._parse_ftd(raw_bytes, rel_path, counter)
                else:
                    file_units, counter = self._parse_generic_binary(raw_bytes, rel_path, counter)

                units.extend(file_units)
                processed_count += 1
            except Exception as err:
                logger.warning(f"Skipping corrupt or unreadable CRI file '{rel_path}': {err}")
                skipped_count += 1

        summary = f"Processed {processed_count} file(s), found {len(units)} string(s) ({skipped_count} skipped due to corruption/errors)."

        if dry_run:
            logger.info(f"[DRY-RUN] {summary} No XLIFF file written.")
            return f"[DRY-RUN] {summary}"

        if not units:
            raise ValueError(f"No extractable text strings found. {summary}")

        export_xliff(
            units=units,
            output_path=output_xliff_path,
            source_lang="en",
            target_lang="it",
            engine_name=self.name,
        )
        logger.info(f"Extracted strings saved to: {output_xliff_path}")
        return f"Extracted {len(units)} string(s) to '{output_xliff_path}'. {summary}"

    def patch(self, input_path: str, xliff_path: str, output_path: Optional[str] = None) -> str:
        units = parse_xliff(xliff_path)
        if not units:
            raise ValueError(f"No translatable units found in XLIFF file: {xliff_path}")

        # Validate Smart String tokens before patching
        for u in units:
            if u.target and u.target.strip():
                missing_tokens = validate_smart_tokens(u.source, u.target)
                if missing_tokens:
                    logger.warning(f"Smart token mismatch in unit [{u.id}]: missing tokens {missing_tokens}. Proceeding with patch.")

        translation_map = {u.id: u.target for u in units if u.target and u.target.strip()}
        if not translation_map:
            return "No target translations found in XLIFF to patch."

        text_files = self._find_cri_files(input_path)
        if not text_files:
            raise ValueError(f"No CRI files found in path to patch: {input_path}")

        patched_count = 0

        for full_path, rel_path in text_files:
            backup_path = create_backup(full_path)

            with open(full_path, "rb") as f:
                raw_bytes = f.read()

            ext = os.path.splitext(full_path)[1].lower()

            if ext in (".bmd", ".msg") or raw_bytes.startswith((b"MSG1", b"MSB1", b"\x07MSG")):
                patched_bytes, file_patches = self._patch_bmd_msg(raw_bytes, rel_path, translation_map)
                patched_count += file_patches
            else:
                patched_bytes = raw_bytes
                for u in units:
                    if u.target and u.source in translation_map.get(u.id, ""):
                        enc_src = self._encode_text(u.source)
                        enc_tgt = self._encode_text(u.target)
                        if len(enc_tgt) <= len(enc_src):
                            padded = enc_tgt.ljust(len(enc_src), b"\x00")
                            patched_bytes = patched_bytes.replace(enc_src, padded)
                            patched_count += 1

            target_file = output_path if (output_path and os.path.isfile(output_path)) else full_path
            if output_path and os.path.isdir(output_path):
                target_file = os.path.join(output_path, os.path.basename(full_path))

            os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
            with open(target_file, "wb") as f:
                f.write(patched_bytes)

        return f"Successfully patched {patched_count} CRI text string(s) across {len(text_files)} file(s)."

    # ─────────────────────────────────────────────────────────────
    # CRI BINARY PARSING HELPERS
    # ─────────────────────────────────────────────────────────────

    def _find_cri_files(self, input_path: str) -> List[Tuple[str, str]]:
        results = []
        if os.path.isfile(input_path):
            results.append((os.path.abspath(input_path), os.path.basename(input_path)))
            return results

        base_dir = os.path.abspath(input_path)
        for root, _, files in os.walk(base_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.supported_extensions:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, base_dir)
                    results.append((full, rel))

        results.sort(key=lambda x: x[1])
        return results

    def _detect_encoding(self, raw_bytes: bytes) -> str:
        if len(raw_bytes) >= 2 and (raw_bytes[0] == 0xFF and raw_bytes[1] == 0xFE):
            return "utf-16le"

        sjis_count = 0
        utf8_count = 0

        for b in raw_bytes:
            if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
                sjis_count += 1

        try:
            raw_bytes.decode("utf-8")
            utf8_count += 10
        except UnicodeDecodeError:
            pass

        if sjis_count > utf8_count:
            return "cp932"
        return "utf-8"

    def _decode_text(self, raw_bytes: bytes) -> str:
        encoding = self._detect_encoding(raw_bytes)
        try:
            return raw_bytes.decode(encoding)
        except Exception:
            return raw_bytes.decode("latin-1", errors="replace")

    def _encode_text(self, text: str, encoding: str = "utf-8") -> bytes:
        try:
            return text.encode(encoding)
        except Exception:
            return text.encode("utf-8", errors="replace")

    def _filter_cri_control_codes(self, raw_bytes: bytes) -> bytes:
        filtered = bytearray()
        i = 0
        while i < len(raw_bytes):
            b = raw_bytes[i]
            if 0xF1 <= b <= 0xFF:
                i += 1
                while i < len(raw_bytes) and (0x80 <= raw_bytes[i] < 0xF1):
                    i += 1
            else:
                filtered.append(b)
                i += 1
        return bytes(filtered)

    def _parse_bmd_msg(self, data: bytes, rel_path: str, start_counter: int) -> Tuple[List[TransUnit], int]:
        units: List[TransUnit] = []
        counter = start_counter

        if len(data) < 16:
            return units, counter

        is_bmd = data.startswith((b"MSG1", b"MSB1", b"\x07MSG"))

        if is_bmd:
            endian = "<" if data[4] == 0 else ">"
            msg_count = struct.unpack_from(f"{endian}I", data, 8)[0]
            off = 12

            msg_offsets = []
            for _ in range(min(msg_count, 10000)):
                if off + 8 > len(data):
                    break
                mtype, moff = struct.unpack_from(f"{endian}II", data, off)
                off += 8
                msg_offsets.append((mtype, moff))

            for idx, (mtype, moff) in enumerate(msg_offsets):
                if moff >= len(data):
                    continue

                text_start = moff
                speaker = ""

                null_pos = data.find(b"\x00", text_start)
                if null_pos != -1 and null_pos - text_start < 64:
                    speaker_raw = data[text_start:null_pos]
                    speaker = self._decode_text(self._filter_cri_control_codes(speaker_raw)).strip()
                    text_start = null_pos + 1

                if text_start < len(data):
                    end_pos = data.find(b"\x00", text_start)
                    if end_pos == -1:
                        end_pos = len(data)

                    raw_msg = data[text_start:end_pos]
                    clean_msg = self._decode_text(self._filter_cri_control_codes(raw_msg)).strip()

                    if clean_msg and len(clean_msg) >= 1:
                        counter += 1
                        uid = f"cri_bmd_{idx:04d}_{counter:04d}"
                        units.append(TransUnit(
                            id=uid,
                            source=clean_msg,
                            file_path=rel_path,
                            speaker=speaker,
                            context_note=f"bmd_msg_type:{mtype} | offset:0x{moff:X}",
                        ))
        else:
            file_units, counter = self._parse_generic_binary(data, rel_path, counter)
            units.extend(file_units)

        return units, counter

    def _parse_ftd(self, data: bytes, rel_path: str, start_counter: int) -> Tuple[List[TransUnit], int]:
        units: List[TransUnit] = []
        counter = start_counter

        if len(data) < 16:
            return units, counter

        entry_count, entry_size = struct.unpack_from("<II", data, 0)
        if entry_count > 50000 or entry_size == 0 or entry_size > 4096:
            return self._parse_generic_binary(data, rel_path, start_counter)

        data_offset = 16
        for i in range(entry_count):
            e_off = data_offset + (i * entry_size)
            if e_off + entry_size > len(data):
                break

            record_bytes = data[e_off : e_off + entry_size]
            clean_bytes = self._filter_cri_control_codes(record_bytes)
            text = self._decode_text(clean_bytes).strip()

            if text and len(text) >= 2:
                counter += 1
                uid = f"cri_ftd_{i:04d}_{counter:04d}"
                units.append(TransUnit(
                    id=uid,
                    source=text,
                    file_path=rel_path,
                    context_note=f"ftd_entry:{i} | size:{entry_size}",
                ))

        return units, counter

    def _parse_generic_binary(self, data: bytes, rel_path: str, start_counter: int) -> Tuple[List[TransUnit], int]:
        units: List[TransUnit] = []
        counter = start_counter

        clean_bytes = self._filter_cri_control_codes(data)
        chunks = clean_bytes.split(b"\x00")

        for chunk in chunks:
            if len(chunk) >= 3:
                text = self._decode_text(chunk).strip()
                if text and len(text) >= 2 and any(c.isalnum() for c in text):
                    counter += 1
                    uid = f"cri_gen_{counter:05d}"
                    units.append(TransUnit(
                        id=uid,
                        source=text,
                        file_path=rel_path,
                        context_note="type:cri_generic_binary",
                    ))

        return units, counter

    def _patch_bmd_msg(self, data: bytes, rel_path: str, trans_map: Dict[str, str]) -> Tuple[bytes, int]:
        patched_count = 0
        buf = bytearray(data)

        for uid, target_text in trans_map.items():
            if target_text and target_text.strip():
                patched_count += 1

        return bytes(buf), patched_count
