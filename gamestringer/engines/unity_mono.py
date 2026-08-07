"""
Unity (Mono) Engine Adapter for GameStringer CLI.

Extracts and repatches localization text from Unity AssetBundles (.bundle),
un-extended AssetBundle files (e.g. StreamingAssets/AssetBundles/*),
serialized assets (.assets), MonoBehaviour StringTables, SharedTableData,
and TextAsset CSV/JSON/Localization tables using UnityPy.
"""

import os
import re
import csv
import io
from typing import List, Optional, Tuple, Dict, Any
from gamestringer.core.base_engine import BaseEngine, TransUnit, validate_smart_tokens
from gamestringer.core.xliff_exporter import export_xliff, parse_xliff
from gamestringer.core.backup import create_backup
from gamestringer.core.logger import logger
from gamestringer.core.addressables_crc import auto_update_addressables_crc

from gamestringer.core.ui_whitelist import UI_WHITELIST

try:
    import UnityPy
except ImportError:
    UnityPy = None

SMART_STRING_PATTERN = re.compile(r"(\{[^{}]+\})")
UNITY_MAGIC_HEADERS = (b"UnityFS", b"UnityRaw", b"UnityWeb", b"UnityArchive")
MAX_SINGLE_FILE_SIZE_BYTES = 300 * 1024 * 1024  # 300 MB safeguard

_ASSEMBLY_QUALIFIED_RE = re.compile(
    r",\s*Version=[\d.]+,\s*Culture=\w+,\s*PublicKeyToken=(?:null|[0-9a-fA-F]+)", re.IGNORECASE
)
_DOTTED_SEGMENT_RE = re.compile(r"^[A-Z][A-Za-z0-9_\-]*$")
_VERSION_RE = re.compile(rb"(\d{1,4}\.\d{1,2}\.\d{1,3}[fpab]?\d{0,3})")

_TEXT_COMPONENT_KEYWORDS = (
    "text", "tmp", "textmesh", "textmeshpro", "textasset", "stringtable", "sharedtabledata",
    "localization", "localizedstring", "localizer", "uilabel", "ui_text",
    "dialogue", "conversation", "narrative", "story", "subtitle", "caption", "narration",
    "quest", "mission", "objective", "hint", "tutorial", "message", "mail", "letter", "notification",
    "menu", "button", "label", "title", "header", "description", "tooltip", "popup", "toast",
    "character", "npc", "enemy", "boss", "item", "weapon", "armor", "potion", "spell", "skill", "ability",
    "lore", "journal", "diary", "book", "scroll", "codex", "encyclopedia",
    "achievement", "trophy", "reward", "medal", "badge",
    "shop", "store", "merchant", "vendor", "buy", "sell", "trade",
    "save", "load", "slot", "profile", "settings", "options", "config",
    "chapter", "stage", "level", "area", "location", "dungeon", "world", "map",
    "health", "mana", "stamina", "energy", "xp", "attribute",
    "cutscene", "cinematic", "intro", "outro", "ending", "credits",
    "displayname", "heading"
)

_TEXT_PATH_KEYWORDS = (
    "localization", "stringtable", "text", "dialogue", "ui", "menu", "quest", "story",
    "subtitle", "lore", "journal", "notification", "tutorial", "message", "cutscene",
    "cinematic", "intro", "credits", "ending", "name", "title", "description", "label",
    "button", "popup", "toast", "run", "shared", "bundle", "asset"
)

_CODE_COMPONENT_EXACT = {
    "transform", "recttransform", "camera", "light", "audiosource", "audioalignment", "audiohost", "audiolistener", "animator", "animation",
    "rigidbody", "rigidbody2d", "collider", "collider2d", "meshrenderer", "skinnedmeshrenderer",
    "spriterenderer", "particlesystem", "trailrenderer", "linerenderer", "canvas", "canvasscaler",
    "graphicraycaster", "eventsystem", "standaloneinputmodule", "physics2draycaster", "physicsraycaster"
}

_CODE_COMPONENT_RE = re.compile(
    r"\b(transform|recttransform|camera|light|audiosource|audiolistener|animator|animation|rigidbody|rigidbody2d|collider|collider2d|meshrenderer|skinnedmeshrenderer|spriterenderer|particlesystem|trailrenderer|linerenderer|canvas|canvasscaler|graphicraycaster|eventsystem)\b",
    re.IGNORECASE
)

_HIGH_CONFIDENCE_FIELD_EXACT = {
    "text", "m_text", "text_", "displaytext", "display_text",
    "m_string", "stringvalue", "string_value",
    "value", "m_value", "entry", "m_entry", "content", "m_content",
    "title", "m_title", "header", "m_header", "heading", "m_heading",
    "description", "m_description", "desc", "m_desc", "body", "m_body",
    "name", "m_name", "displayname", "display_name", "message", "m_message", "msg", "m_msg",
    "dialogue", "m_dialogue", "dialog", "m_dialog", "line", "m_line", "speech", "m_speech",
    "subtitle", "m_subtitle", "caption", "m_caption",
    "notification", "m_notification", "notify", "m_notify", "alert", "m_alert",
    "tooltip", "m_tooltip", "hint", "m_hint", "tip", "m_tip",
    "label", "m_label", "buttontext", "button_text", "btntext", "btn_text",
    "questtext", "quest_text", "objectivetext", "objective_text", "missiontext", "mission_text",
    "itemname", "item_name", "itemdescription", "item_description",
    "charactername", "character_name", "npcname", "npc_name", "enemyname", "enemy_name",
    "locationname", "location_name", "areaname", "area_name", "levelname", "level_name",
    "loretext", "lore_text", "journaltext", "journal_text", "entrytext", "entry_text",
    "boss_name_", "win_session_end_message_"
}

_FIELD_BLACKLIST = {
    "localposition", "localrotation", "localscale", "position", "rotation", "eulerangles",
    "anchormin", "anchormax", "anchoredposition", "sizedelta", "pivot", "offsetmin", "offsetmax",
    "m_classname", "m_namespace", "m_assemblyname", "m_fullname", "m_typename",
    "guid", "m_guid", "guid_", "uniqueid", "m_uniqueid",
    "path_", "m_path", "assetpath", "asset_path", "filepath", "file_path",
    "last_push_call_stack_", "last_pop_call_stack_", "call_stack", "stack_trace", "m_stacktrace",
    "hash", "m_hash", "hash_", "crc", "m_crc", "checksum", "m_checksum",
    "prefabassetpath", "prefab_asset_path", "m_prefabassetpath",
    "assetbundlename", "asset_bundle_name", "m_assetbundlename",
    "fmod_event_", "fmodevent", "audioevent", "audio_event", "soundevent", "sound_event",
    "animatorstate", "animator_state", "statename", "state_name", "animationstate", "animation_state",
    "clipname", "clip_name", "animationclip", "animation_clip",
    "methodname", "method_name", "targetmethod", "target_method", "callbackmethod", "callback_method",
    "eventhandler", "event_handler", "eventcallback", "event_callback", "propertyname", "field_name_", "target_method_name_"
}

_GUID_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CAMEL_CASE_CODE_RE = re.compile(r"^[a-z]+[A-Z0-9][a-zA-Z0-9_]*$|^[A-Z][a-z0-9]+[A-Z0-9][a-zA-Z0-9_]*$")
_TITLE_OR_CAPS_RE = re.compile(r"^[A-Z][a-z]+$|^[A-Z]+$")
_ACCENTED_RE = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")
_PUNCTUATION_RE = re.compile(r'[.,!?;:\-"\']')


def classify_component(class_name: str, rel_path: str) -> str:
    """Classify MonoBehaviour into A (text_component), B (maybe_text), C (code_component), or D (unknown)."""
    c_lower = class_name.lower()
    p_lower = rel_path.lower()

    # Category A (Text Component)
    if any(k in c_lower for k in _TEXT_COMPONENT_KEYWORDS):
        return "text_component"

    # Category C (Code Component)
    if c_lower in _CODE_COMPONENT_EXACT or _CODE_COMPONENT_RE.search(class_name):
        return "code_component"

    # Category B (Maybe Text)
    if c_lower in ("monobehaviour", "gameobject", "scriptableobject", "component", "behaviour") or c_lower.startswith("monobehaviour_"):
        if any(k in p_lower for k in _TEXT_PATH_KEYWORDS):
            return "maybe_text"

    return "unknown"


def is_field_blacklisted(key_name: str, val_text: str) -> bool:
    """Layer 2: Field Name Blacklist."""
    k_lower = str(key_name).lower()
    if k_lower in _FIELD_BLACKLIST or any(b in k_lower for b in _FIELD_BLACKLIST):
        return True
    return False


def is_high_confidence_field(key_name: str) -> bool:
    """Layer 2: High confidence text field name check."""
    k_lower = str(key_name).lower()
    return k_lower in _HIGH_CONFIDENCE_FIELD_EXACT


def is_value_garbage(val_text: str, class_name: str) -> bool:
    """Layer 3: Value Heuristics (Code & System Noise Blacklist)."""
    s = val_text.strip()
    s_lower = s.lower()
    if not s or len(s) < 1 or len(s) > 10000:
        return True
    if s_lower in ("true", "false", "null", "none", "undefined", "nan", "infinity"):
        return True
    if _GUID_HEX_RE.match(s):
        return True
    if s_lower.startswith("   at ") or "get_stacktrace()" in s_lower:
        return True
    if s_lower.startswith("event:/") or s_lower.startswith("assets/") or s_lower.startswith("packages/"):
        return True
    if s_lower.endswith((".prefab", ".mat", ".asset", ".controller", ".anim", ".unity", ".png", ".jpg", ".tga", ".wav", ".mp3")):
        return True
    if any(ns in s for ns in ("System.Environment", "System.Action", "System.Collections", "UnityEngine.")):
        return True
    if s in ("Transform", "RectTransform", "Camera", "GameObject", "AudioSource", "Animator", "MonoBehaviour", "MonoScript"):
        return True
    if s.endswith(("_EventHandler", "_Callback", "_Coroutine", "_Listener")):
        return True
    if ".cs" in s_lower and ("\\" in s or "/" in s):
        return True
    if "," in s and "Version=" in s:
        return True
    if _looks_like_type_reference(s):
        return True
    return False


def should_keep_string(key_name: str, val_text: str, class_name: str, category: str = "unknown") -> bool:
    """Evaluate 4-layer smart filtering rules for a string value."""
    if is_field_blacklisted(key_name, val_text):
        return False
    if is_value_garbage(val_text, class_name):
        return False

    s = val_text.strip()

    # High-confidence field name priority
    if is_high_confidence_field(key_name):
        if not _CAMEL_CASE_CODE_RE.match(s) or " " in s:
            return True

    # Layer 3 Keep criteria (IS text if ANY match)
    if " " in s and len([c for c in s if c.isalpha()]) >= 3:
        return True
    if _ACCENTED_RE.search(s):
        return True
    if len(s) > 5 and _PUNCTUATION_RE.search(s):
        return True
    if s.lower() in UI_WHITELIST or s in ("OK", "Yes", "No", "Play", "Settings", "Quit", "Back", "Save", "Exit", "HP", "MP", "XP", "LV", "HUD"):
        return True

    # Safety Net: Single word Title Case or ALL CAPS (e.g. "Inventory", "Attack", "Quests", "Play")
    if 2 <= len(s) <= 20 and s.isalpha() and _TITLE_OR_CAPS_RE.match(s):
        return True

    # Check Layer 3 IS NOT text criteria
    if " " not in s and not _ACCENTED_RE.search(s) and not _PUNCTUATION_RE.search(s) and len(s) < 30:
        if _CAMEL_CASE_CODE_RE.match(s):
            return False

    if category == "text_component":
        return True

    if category in ("maybe_text", "unknown"):
        if " " in s or _ACCENTED_RE.search(s) or _PUNCTUATION_RE.search(s) or s.lower() in UI_WHITELIST or _TITLE_OR_CAPS_RE.match(s):
            return True
        return False

    return False
    if len(s) > 5 and _PUNCTUATION_RE.search(s):
        return True
    if s.lower() in UI_WHITELIST or s in ("OK", "Yes", "No", "Play", "Settings", "Quit", "Back", "Save", "Exit"):
        return True
    if _CAMEL_CASE_CODE_RE.match(s) and len(s) < 30 and " " not in s:
        return False
    if any(k in class_name.lower() for k in _TEXT_COMPONENT_KEYWORDS):
        return True
    return False


def _looks_like_type_reference(s: str) -> bool:
    """True if string is a serialized C# type or assembly reference (e.g. 'PlayerDefaultState, Assembly-CSharp')."""
    if _ASSEMBLY_QUALIFIED_RE.search(s):
        return True
    segments = [seg.strip() for seg in re.split(r"[.,]", s)]
    if len(segments) >= 2 and all(seg for seg in segments):
        return all(_DOTTED_SEGMENT_RE.match(seg) for seg in segments)
    return False


def detect_unity_version_from_header(file_path: str) -> Optional[Tuple[str, str]]:
    """Ultra-fast zero-dependency 64KB binary header scan for Unity version string & OS platform."""
    try:
        with open(file_path, "rb") as f:
            data = f.read(65536)
    except Exception:
        return None

    match = _VERSION_RE.search(data)
    if match:
        ver_str = match.group(1).decode("ascii", errors="ignore")
        if len(ver_str) >= 5 and "." in ver_str:
            platform = "Windows"
            data_lower = data.lower()
            if b"android" in data_lower:
                platform = "Android"
            elif b"switch" in data_lower:
                platform = "Nintendo Switch"
            elif b"ps5" in data_lower or b"ps4" in data_lower:
                platform = "PlayStation"
            elif b"linux" in data_lower:
                platform = "Linux"
            elif re.search(rb"\b(macos|osx|mac)\b", data_lower):
                platform = "macOS"
            return ver_str, platform
    return None


class UnityMonoEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "unity"

    @property
    def description(self) -> str:
        return "Unity Mono AssetBundle & Serialized Assets (.bundle / .assets / StringTable / TextAsset)"

    @property
    def supported_extensions(self) -> List[str]:
        return [".bundle", ".assets", ".asset"]

    def detect(self, input_path: str) -> bool:
        if not os.path.exists(input_path):
            return False

        if os.path.isfile(input_path):
            ext = os.path.splitext(input_path)[1].lower()
            if ext in self.supported_extensions:
                return True
            try:
                with open(input_path, "rb") as f:
                    return f.read(8).startswith(UNITY_MAGIC_HEADERS)
            except Exception:
                return False

        if os.path.isdir(input_path):
            for root, dirs, files in os.walk(input_path):
                if any(d.endswith("_Data") for d in dirs):
                    return True
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in self.supported_extensions or f.startswith("sharedassets") or f == "resources.assets":
                        return True

        return False

    def extract(self, input_path: str, output_xliff_path: str, dry_run: bool = False) -> str:
        if UnityPy is None:
            raise RuntimeError("UnityPy package is required for Unity Mono engine extraction. Install via 'pip install UnityPy'.")

        asset_files = self._find_unity_files(input_path)
        if not asset_files:
            raise ValueError(f"No Unity asset files (.bundle, .assets) found in path: {input_path}")

        units: List[TransUnit] = []
        counter = 0
        processed_count = 0
        skipped_count = 0

        for full_path, rel_path in asset_files:
            try:
                file_units, counter = self._extract_from_asset(full_path, rel_path, counter)
                units.extend(file_units)
                processed_count += 1
            except Exception as err:
                logger.warning(f"Skipping corrupt or unreadable asset file '{rel_path}': {err}")
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
        if UnityPy is None:
            raise RuntimeError("UnityPy package is required for Unity Mono engine patching. Install via 'pip install UnityPy'.")

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

        asset_files = self._find_unity_files(input_path)
        if not asset_files:
            raise ValueError(f"No Unity asset files found in path to patch: {input_path}")

        patched_count = 0
        backups_created = 0
        modified_target_files = []

        for full_path, rel_path in asset_files:
            # Create backup if patching in-place
            if not output_path:
                create_backup(full_path)
                backups_created += 1

            try:
                env = UnityPy.load(full_path)
            except Exception as err:
                logger.warning(f"Skipping unpatchable or corrupt asset file '{rel_path}': {err}")
                continue

            file_modified = False

            for obj in env.objects:
                if obj.type.name == "MonoBehaviour":
                    try:
                        data = obj.read_typetree()
                        if isinstance(data, dict):
                            modified = self._patch_monobehaviour_data(data, obj.path_id, rel_path, translation_map)
                            if modified:
                                obj.save_typetree(data)
                                file_modified = True
                                patched_count += 1
                    except Exception:
                        pass

                elif obj.type.name == "TextAsset":
                    try:
                        data = obj.read()
                        asset_name = getattr(data, "m_Name", getattr(data, "name", f"TextAsset_{obj.path_id}"))
                        script_bytes = getattr(data, "m_Script", getattr(data, "script", b""))

                        if isinstance(script_bytes, bytes):
                            text_content = script_bytes.decode("utf-8", errors="replace")
                        elif isinstance(script_bytes, str):
                            text_content = script_bytes
                        else:
                            text_content = ""

                        if text_content:
                            new_text, sub_count = self._patch_text_asset_content(text_content, asset_name, rel_path, obj.path_id, translation_map)
                            if sub_count > 0:
                                if hasattr(data, "m_Script"):
                                    data.m_Script = new_text
                                elif hasattr(data, "script"):
                                    data.script = new_text
                                data.save()
                                file_modified = True
                                patched_count += sub_count
                    except Exception as err:
                        logger.warning(f"Error patching TextAsset {obj.path_id} in '{rel_path}': {err}")

            if file_modified:
                if output_path:
                    if output_path.endswith((".assets", ".bundle")) or os.path.isfile(output_path):
                        target_file = output_path
                    else:
                        target_file = os.path.join(output_path, rel_path)
                else:
                    target_file = full_path

                os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
                with open(target_file, "wb") as f:
                    f.write(env.file.save())
                modified_target_files.append(target_file)

        crc_msgs = auto_update_addressables_crc(input_path, modified_target_files)
        crc_info = (" " + " | ".join(crc_msgs)) if crc_msgs else ""

        backup_msg = f"Backups created: {backups_created}" if backups_created > 0 else "Separate output folder target (original files untouched)"
        return f"Successfully patched {patched_count} Unity asset text element(s) across {len(asset_files)} file(s). {backup_msg}.{crc_info}"

    # ─────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────

    def _find_unity_files(self, input_path: str) -> List[Tuple[str, str]]:
        results = []
        if os.path.isfile(input_path):
            results.append((os.path.abspath(input_path), os.path.basename(input_path)))
            return results

        base_dir = os.path.abspath(input_path)
        for root, _, files in os.walk(base_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base_dir)

                ext = os.path.splitext(f)[1].lower()
                if ext in self.supported_extensions or f.startswith("sharedassets") or f == "resources.assets" or f == "globalgamemanagers":
                    try:
                        if os.path.getsize(full) > MAX_SINGLE_FILE_SIZE_BYTES:
                            logger.warning(f"Skipping large asset file '{rel}' (>300MB file size safeguard).")
                            continue
                    except Exception:
                        pass
                    results.append((full, rel))
                elif not ext or ext == ".manifest":
                    if f.endswith(".manifest"):
                        continue
                    try:
                        if os.path.getsize(full) > MAX_SINGLE_FILE_SIZE_BYTES:
                            continue
                        with open(full, "rb") as bf:
                            header = bf.read(8)
                            if header.startswith(UNITY_MAGIC_HEADERS):
                                results.append((full, rel))
                    except Exception:
                        pass

        results.sort(key=lambda x: x[1])
        return results

    def _extract_from_asset(self, full_path: str, rel_path: str, start_counter: int) -> Tuple[List[TransUnit], int]:
        units: List[TransUnit] = []
        counter = start_counter

        env = UnityPy.load(full_path)
        skipped_components = 0
        inspected_components = 0
        extracted_text_count = 0

        for obj in env.objects:
            if obj.type.name == "MonoBehaviour":
                try:
                    data = obj.read_typetree()
                    if isinstance(data, dict):
                        mb_name = data.get("m_Name", f"MonoBehaviour_{obj.path_id}")
                        cat = classify_component(mb_name, rel_path)
                        if cat == "code_component":
                            skipped_components += 1
                            continue

                        inspected_components += 1
                        entries = self._extract_strings_from_dict(data, mb_name, cat)

                        for key_name, val_text in entries:
                            if val_text and len(val_text.strip()) > 0:
                                counter += 1
                                extracted_text_count += 1
                                uid = f"unity_{obj.path_id}_{counter:05d}"

                                smart_tokens = SMART_STRING_PATTERN.findall(val_text)
                                context = f"mono_behaviour:{mb_name} | cat:{cat}"
                                if smart_tokens:
                                    context += f" | smart_tokens:{','.join(smart_tokens)}"

                                units.append(TransUnit(
                                    id=uid,
                                    source=val_text,
                                    file_path=rel_path,
                                    namespace=mb_name,
                                    key=str(key_name),
                                    context_note=context,
                                ))
                except Exception:
                    pass

            elif obj.type.name == "TextAsset":
                try:
                    data = obj.read()
                    asset_name = getattr(data, "m_Name", getattr(data, "name", f"TextAsset_{obj.path_id}"))
                    script_bytes = getattr(data, "m_Script", getattr(data, "script", b""))

                    if isinstance(script_bytes, bytes):
                        text_content = script_bytes.decode("utf-8", errors="replace")
                    elif isinstance(script_bytes, str):
                        text_content = script_bytes
                    else:
                        text_content = ""

                    if text_content and len(text_content) > 2:
                        extracted_units, counter = self._parse_text_asset_content(text_content, asset_name, rel_path, obj.path_id, counter)
                        units.extend(extracted_units)
                        extracted_text_count += len(extracted_units)
                except Exception as err:
                    logger.warning(f"Error parsing TextAsset {obj.path_id} in '{rel_path}': {err}")

        if skipped_components > 0:
            logger.debug(f"Skipped {skipped_components} code/system components in '{rel_path}'")
        if extracted_text_count > 0:
            logger.debug(f"Extracted {extracted_text_count} text strings from '{rel_path}'")

        return units, counter

    def _parse_text_asset_content(self, content: str, asset_name: str, rel_path: str, path_id: int, start_counter: int) -> Tuple[List[TransUnit], int]:
        units: List[TransUnit] = []
        counter = start_counter

        lines = content.splitlines()
        if lines and ("," in lines[0] or "\t" in lines[0]):
            delimiter = "\t" if "\t" in lines[0] else ","
            try:
                reader = csv.reader(io.StringIO(content), delimiter=delimiter)
                header = next(reader, None)
                if header:
                    text_col_indices = []
                    for idx, col in enumerate(header):
                        col_upper = col.strip().upper()
                        if col_upper in ("EN", "ENGLISH", "DESC", "DESCRIPTION", "TEXT", "DIALOGUE", "STRING"):
                            text_col_indices.append((idx, col_upper))

                    if text_col_indices:
                        for row_idx, row in enumerate(reader, start=2):
                            row_id = row[0] if row else f"row_{row_idx}"
                            for col_idx, col_name in text_col_indices:
                                if col_idx < len(row):
                                    val = row[col_idx].strip()
                                    if val and len(val) > 1 and not val.isdigit():
                                        counter += 1
                                        uid = f"csv_{asset_name}_{row_idx}_{col_name}_{counter}"
                                        units.append(TransUnit(
                                            id=uid,
                                            source=val,
                                            file_path=rel_path,
                                            namespace=asset_name,
                                            key=f"{row_id}:{col_name}",
                                            line_number=row_idx,
                                            context_note=f"text_asset_csv:{asset_name} | col:{col_name}",
                                        ))
                        if units:
                            return units, counter
            except Exception:
                pass

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed and len(trimmed) > 1 and not trimmed.startswith(("#", "//")):
                counter += 1
                uid = f"text_line_{asset_name}_{idx}_{counter}"
                units.append(TransUnit(
                    id=uid,
                    source=trimmed,
                    file_path=rel_path,
                    namespace=asset_name,
                    line_number=idx,
                    context_note=f"text_asset_line:{asset_name}",
                ))

        return units, counter

    def _patch_text_asset_content(self, content: str, asset_name: str, rel_path: str, path_id: int, trans_map: Dict[str, str]) -> Tuple[str, int]:
        sub_count = 0

        source_trans_map = {}
        for uid, target_text in trans_map.items():
            if asset_name in uid:
                source_trans_map[uid] = target_text

        lines = content.splitlines(keepends=True)
        patched_lines = []

        for idx, line in enumerate(lines, start=1):
            line_replaced = False
            for uid, target_text in source_trans_map.items():
                if f"_{idx}_" in uid or f"_{idx}" in uid:
                    patched_lines.append(line.replace(line.strip(), target_text))
                    sub_count += 1
                    line_replaced = True
                    break

            if not line_replaced:
                patched_lines.append(line)

        return "".join(patched_lines), sub_count

    def _extract_strings_from_dict(self, data: Any, class_name: str = "", category: str = "unknown") -> List[Tuple[str, str]]:
        results = []

        if isinstance(data, dict):
            table_data = data.get("m_TableData") or data.get("m_Entries") or data.get("m_StringTable")
            if isinstance(table_data, list):
                for item in table_data:
                    if isinstance(item, dict):
                        k = item.get("m_Key") or item.get("m_Id") or item.get("m_KeyId") or item.get("key")
                        v = item.get("m_Value") or item.get("m_Localized") or item.get("value")
                        if v and isinstance(v, str) and should_keep_string(str(k or "entry"), v, class_name, category):
                            results.append((str(k or "entry"), v))

            for k, v in data.items():
                if k in ("m_TableData", "m_Entries", "m_StringTable", "m_Script", "m_Name", "m_TypeName"):
                    continue
                if isinstance(v, str) and len(v.strip()) > 0:
                    if should_keep_string(k, v, class_name, category):
                        results.append((k, v))
                elif isinstance(v, (dict, list)):
                    results.extend(self._extract_strings_from_dict(v, class_name, category))

        elif isinstance(data, list):
            for item in data:
                results.extend(self._extract_strings_from_dict(item, class_name, category))

        return results

    def _patch_monobehaviour_data(self, data: Any, path_id: int, rel_path: str, trans_map: Dict[str, str]) -> bool:
        modified = False

        if isinstance(data, dict):
            table_data = data.get("m_TableData") or data.get("m_Entries") or data.get("m_StringTable")
            if isinstance(table_data, list):
                for item in table_data:
                    if isinstance(item, dict):
                        v = item.get("m_Value") or item.get("m_Localized") or item.get("value")
                        if v and isinstance(v, str):
                            for uid, target_text in trans_map.items():
                                if uid.startswith(f"unity_{path_id}_"):
                                    if "m_Value" in item:
                                        item["m_Value"] = target_text
                                    elif "value" in item:
                                        item["value"] = target_text
                                    elif "m_Localized" in item:
                                        item["m_Localized"] = target_text
                                    modified = True
                                    break

            for k, v in data.items():
                if k in ("m_TableData", "m_Entries", "m_StringTable"):
                    continue
                if isinstance(v, (dict, list)):
                    if self._patch_monobehaviour_data(v, path_id, rel_path, trans_map):
                        modified = True

        elif isinstance(data, list):
            for item in data:
                if self._patch_monobehaviour_data(item, path_id, rel_path, trans_map):
                    modified = True

        return modified
