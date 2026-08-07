"""
Ren'Py Visual Novel Engine Adapter for GameStringer CLI.

Supports extraction of dialogue, narration, menu choices, and screen texts
from .rpy script files, and repatching via standard Ren'Py tl/ translation blocks
and say_menu_text_filter runtime hook.
"""

import os
import re
from typing import List, Optional, Tuple, Dict
from gamestringer.core.base_engine import BaseEngine, TransUnit, validate_smart_tokens
from gamestringer.core.xliff_exporter import export_xliff, parse_xliff
from gamestringer.core.backup import create_backup
from gamestringer.core.logger import logger


class RenpyEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "renpy"

    @property
    def description(self) -> str:
        return "Ren'Py Visual Novel Engine (.rpy / .rpa)"

    @property
    def supported_extensions(self) -> List[str]:
        return [".rpy", ".rpa"]

    def detect(self, input_path: str) -> bool:
        if not os.path.exists(input_path):
            return False

        if os.path.isfile(input_path):
            ext = os.path.splitext(input_path)[1].lower()
            return ext in self.supported_extensions

        if os.path.isdir(input_path):
            game_folder = os.path.join(input_path, "game")
            if os.path.exists(game_folder) and os.path.isdir(game_folder):
                return True

            for root, _, files in os.walk(input_path):
                for f in files:
                    if f.lower().endswith(".rpy"):
                        return True

        return False

    def extract(self, input_path: str, output_xliff_path: str, dry_run: bool = False) -> str:
        rpy_files = self._find_rpy_files(input_path)
        if not rpy_files:
            raise ValueError(f"No .rpy script files found in input path: {input_path}")

        units: List[TransUnit] = []
        unit_counter = 0
        processed_count = 0
        skipped_count = 0

        for full_path, rel_path in rpy_files:
            try:
                file_units, unit_counter = self._parse_rpy_file(full_path, rel_path, unit_counter)
                units.extend(file_units)
                processed_count += 1
            except Exception as err:
                logger.warning(f"Skipping corrupt or unreadable file '{rel_path}': {err}")
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

        translated_units = [u for u in units if u.target and u.target.strip()]
        if not translated_units:
            return "No target translations found in XLIFF to patch."

        # Validate Smart String tokens before patching
        for u in translated_units:
            missing_tokens = validate_smart_tokens(u.source, u.target)
            if missing_tokens:
                logger.warning(f"Smart token mismatch in unit [{u.id}]: missing tokens {missing_tokens}. Proceeding with patch.")

        # Resolve Ren'Py 'game/' directory
        game_folder = self._resolve_game_folder(input_path)
        target_lang = "it"  # Default target language tag

        # Create safety backup before patching
        backup_path = create_backup(game_folder)

        tl_folder = os.path.join(game_folder, "tl", target_lang)
        os.makedirs(tl_folder, exist_ok=True)

        # Categorize translations
        ui_strings: Dict[str, List[TransUnit]] = {}
        dialogue_units: List[TransUnit] = []

        for u in translated_units:
            context = u.context_note or ""
            if "type:screen" in context or "type:string" in context:
                rel_file = u.file_path or "script.rpy"
                ui_strings.setdefault(rel_file, []).append(u)
            else:
                dialogue_units.append(u)

        files_written = []

        # 1. Write `translate <lang> strings:` for UI strings
        for rel_file, str_units in ui_strings.items():
            base_filename = os.path.basename(rel_file)
            out_name = base_filename.replace(".rpy", f"_{target_lang}.rpy")
            out_file_path = os.path.join(tl_folder, out_name)

            lines = [
                f"# Translation file for {rel_file}",
                f"# Generated by GameStringer CLI",
                "",
                f"translate {target_lang} strings:",
                "",
            ]

            for u in str_units:
                clean_src = self._escape_renpy_string(self._unescape_renpy_string(u.source))
                clean_tgt = self._escape_renpy_string(u.target)
                line_info = f"line {u.line_number}" if u.line_number else ""
                lines.append(f"    # {u.file_path}:{line_info}")
                lines.append(f'    old "{clean_src}"')
                lines.append(f'    new "{clean_tgt}"')
                lines.append("")

            with open(out_file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            files_written.append(out_file_path)

        # 2. Write runtime say_menu_text_filter for dialogues and menus
        if dialogue_units:
            filter_file_path = os.path.join(tl_folder, "gamestringer_say_filter.rpy")
            filter_lines = [
                f"# GameStringer CLI — Runtime dialogue filter for language '{target_lang}'",
                "init 1900 python:",
                "    __gs_tl = {",
            ]

            seen_dialogue = {}
            for u in dialogue_units:
                src_key = self._unescape_renpy_string(u.source)
                seen_dialogue[src_key] = u.target

            for src_k, tgt_v in seen_dialogue.items():
                esc_k = self._escape_renpy_string(src_k)
                esc_v = self._escape_renpy_string(tgt_v)
                filter_lines.append(f'        u"{esc_k}": u"{esc_v}",')

            filter_lines.extend([
                "    }",
                f'    __gs_lang = "{target_lang}"',
                '    __gs_prev_filter = getattr(config, "say_menu_text_filter", None)',
                "    def __gs_say_filter(s):",
                "        try:",
                "            if renpy.game.preferences.language == __gs_lang:",
                "                t = __gs_tl.get(s)",
                "                if t is not None:",
                "                    return t",
                "        except Exception:",
                "            pass",
                "        if __gs_prev_filter is not None:",
                "            return __gs_prev_filter(s)",
                "        return s",
                "    config.say_menu_text_filter = __gs_say_filter",
                "",
            ])

            with open(filter_file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(filter_lines))
            files_written.append(filter_file_path)

        return (
            f"Successfully patched Ren'Py translations ({len(translated_units)} entries). "
            f"Backup created at: {backup_path}. "
            f"Generated {len(files_written)} file(s) in game/tl/{target_lang}/"
        )

    # ─────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────

    def _resolve_game_folder(self, input_path: str) -> str:
        """Resolve absolute path to Ren'Py 'game/' directory."""
        abs_path = os.path.abspath(input_path)
        if os.path.isfile(abs_path):
            abs_path = os.path.dirname(abs_path)

        if os.path.basename(abs_path.rstrip("/\\")) == "game":
            return abs_path

        direct_game = os.path.join(abs_path, "game")
        if os.path.exists(direct_game) and os.path.isdir(direct_game):
            return direct_game

        for root, dirs, _ in os.walk(abs_path):
            if "game" in dirs:
                return os.path.join(root, "game")

        return abs_path

    def _find_rpy_files(self, input_path: str) -> List[Tuple[str, str]]:
        """Return list of (full_path, rel_path) for all valid .rpy script files."""
        results = []
        if os.path.isfile(input_path):
            results.append((os.path.abspath(input_path), os.path.basename(input_path)))
            return results

        base_dir = os.path.abspath(input_path)
        game_folder = self._resolve_game_folder(input_path)

        for root, _, files in os.walk(game_folder):
            if os.path.sep + "tl" + os.path.sep in root or root.endswith(os.path.sep + "tl"):
                continue

            for file in files:
                if file.lower().endswith(".rpy"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base_dir)
                    results.append((full_path, rel_path))

        results.sort(key=lambda x: x[1])
        return results

    def _parse_rpy_file(self, full_path: str, rel_path: str, counter_start: int) -> Tuple[List[TransUnit], int]:
        """Parse a single .rpy file line by line into TransUnits."""
        units: List[TransUnit] = []
        counter = counter_start

        try:
            with open(full_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(full_path, "r", encoding="latin-1") as f:
                content = f.read()

        lines = content.splitlines()
        in_python_block = False
        in_screen_block = False

        skip_keywords = (
            "define ", "init ", "$", "if ", "elif ", "else:", "label ",
            "jump ", "call ", "return", "show ", "hide ", "scene ",
            "play ", "stop ", "with ", "transform ", "style ",
            "image ", "default ", "pause", "window ", "pass"
        )

        for i, line in enumerate(lines, start=1):
            trimmed = line.strip()

            if not trimmed or trimmed.startswith("#"):
                continue

            if trimmed.startswith("python:") or trimmed.startswith("init python:"):
                in_python_block = True
                continue

            if in_python_block:
                if len(line) - len(line.lstrip()) == 0 and not line.isspace():
                    in_python_block = False
                else:
                    continue

            if trimmed.startswith("screen "):
                in_screen_block = True
                continue

            if in_screen_block:
                if len(line) - len(line.lstrip()) == 0 and not line.isspace() and not trimmed.startswith("screen "):
                    in_screen_block = False

            if in_screen_block:
                if any(trimmed.startswith(kw) for kw in ("text ", "textbutton ", "label ")) or "Notify(" in trimmed:
                    matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', trimmed)
                    for match in matches:
                        if len(match) > 1:
                            counter += 1
                            units.append(TransUnit(
                                id=f"renpy_{counter:06d}",
                                source=match,
                                file_path=rel_path,
                                line_number=i,
                                context_note="type:screen",
                            ))
                continue

            if any(trimmed.startswith(kw) for kw in skip_keywords):
                continue

            dialogue_match = re.match(r'^(?:([a-zA-Z0-9_]+)\s+)?(?:u|r)?"([^"\\]*(?:\\.[^"\\]*)*)"$', trimmed)
            if dialogue_match:
                speaker, text = dialogue_match.groups()
                if text and len(text.strip()) > 1:
                    counter += 1
                    units.append(TransUnit(
                        id=f"renpy_{counter:06d}",
                        source=text,
                        file_path=rel_path,
                        line_number=i,
                        speaker=speaker,
                        context_note="type:dialogue" if speaker else "type:narration",
                    ))
                continue

            if '"' in trimmed:
                matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', trimmed)
                for match in matches:
                    if len(match.strip()) > 1:
                        counter += 1
                        units.append(TransUnit(
                            id=f"renpy_{counter:06d}",
                            source=match,
                            file_path=rel_path,
                            line_number=i,
                            context_note="type:generic",
                        ))

        return units, counter

    def _escape_renpy_string(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def _unescape_renpy_string(self, s: str) -> str:
        out = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                n = s[i + 1]
                if n == "\\":
                    out.append("\\")
                elif n == '"':
                    out.append('"')
                elif n == "n":
                    out.append("\n")
                elif n == "t":
                    out.append("\t")
                else:
                    out.append("\\" + n)
                i += 2
            else:
                out.append(s[i])
                i += 1
        return "".join(out)
