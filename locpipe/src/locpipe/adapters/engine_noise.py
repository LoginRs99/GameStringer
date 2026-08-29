"""Conservative "this is definitely not translatable text" detection for
engine/asset-export formats -- currently used by the uabea_json adapter's
typetree/array walk (Case 2/3), which -- unlike its CSV-in-m_Script path
(Case 1, which reads a known, validated column) -- has to guess which
string-valued fields in an arbitrary Unity object graph are actually
narrative/UI text versus internal engine plumbing (GUIDs, asset paths,
enum constants, indexed node names, ...).

Every rule here is deliberately one-sided: it only ever answers "this is
DEFINITELY engine noise", never "this is DEFINITELY real text". A false
positive (skipping something that should have been translated) is a much
worse outcome than a false negative (sending a stray GUID to the LLM for
a handful of wasted tokens) -- so any string this can't confidently place
in the first bucket is left alone. This will never catch everything; it's
meant to remove the cheap, common, unambiguous cases. What it misses is
what format_options.uabea_json_path_exclude (project-specific, path-based)
and the `locpipe audit` report (see cli.py) are for.
"""

from __future__ import annotations

import re
from typing import Optional

_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
_HEX_COLOR_RE = re.compile(r"^#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
_NUMBER_OR_VERSION_RE = re.compile(r"^-?\d+(\.\d+)*$")
_BOOLEAN_RE = re.compile(r"^(true|false)$", re.IGNORECASE)
_DOTTED_TYPE_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*){1,}$")
_ALL_CAPS_CONST_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FONT_ID_RE = re.compile(r"^font_[a-z0-9_]+$", re.IGNORECASE)
_ASSET_PATH_RE = re.compile(r"^(loc/|assets/|textures/|sprites/|fonts/|ui/)?(img_|tex_|sprite_|font_|atlas_|mat_|anim_|icon_)[a-z0-9_/-]+$", re.IGNORECASE)


# Common Unity/UABEA asset file extensions -- a bare filename or a path
# ending in one of these is an asset reference, not narrative/UI text.
_ASSET_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".tga", ".psd", ".exr", ".hdr",
    ".mat", ".prefab", ".anim", ".controller", ".fbx", ".obj",
    ".wav", ".mp3", ".ogg", ".shader", ".asset", ".unity",
    ".cs", ".dll", ".ttf", ".otf", ".ttc",
)

# Common single-word UI labels -- kept even though they have no whitespace
# and would otherwise trip the "looks like a bare identifier" rule below.
# Deliberately generous: missing one here just means a cheap extra string
# goes to the LLM, not that real content gets silently dropped.
_SHORT_UI_WORD_ALLOWLIST = {
    "ok", "yes", "no", "cancel", "back", "next", "menu", "settings",
    "start", "pause", "resume", "quit", "save", "load", "continue",
    "options", "exit", "play", "retry", "restart", "confirm", "close",
    "done", "skip", "new", "delete", "edit", "help", "credits", "score",
    "level", "time", "on", "off", "mute", "unmute", "accept", "decline",
    "submit", "apply", "reset", "default", "custom", "easy", "normal",
    "hard", "loading", "paused", "audio", "video", "controls",
    "inventory", "map", "quest", "quests", "shop", "buy", "sell", "equip",
    "unequip", "use", "drop", "select", "deselect", "enter", "leave",
}

# Length past which a spaceless PascalCase/identifier-shaped string is
# treated as a compound engine identifier rather than a plausible single
# UI word. Real single-word UI labels ("Inventory", "Settings") rarely
# run this long; component/node/class names routinely do.
_LONG_IDENTIFIER_THRESHOLD = 24


def noise_reason(value: str) -> Optional[str]:
    """None if `value` might plausibly be real text; otherwise a short
    tag naming which rule matched, for the audit report."""
    text = value.strip()
    if not text:
        return "empty"
    if len(text) <= 1 and not text.isalnum():
        return "lone-punctuation"
    if _GUID_RE.match(text):
        return "guid"
    if _HEX_COLOR_RE.match(text):
        return "hex-color"
    if _NUMBER_OR_VERSION_RE.match(text):
        return "number-or-version"
    if _BOOLEAN_RE.match(text):
        return "boolean-literal"
    if " " not in text and _DOTTED_TYPE_RE.match(text):
        return "dotted-type-name"  # e.g. "UnityEngine.UI.Button"

    lower = text.lower()
    if lower.endswith(_ASSET_EXTENSIONS):
        return "asset-reference"

    if " " not in text:
        if lower in _SHORT_UI_WORD_ALLOWLIST:
            return None
        if _FONT_ID_RE.match(text):
            return "font-identifier"
        if _ASSET_PATH_RE.match(text):
            return "asset-path"
        if _ALL_CAPS_CONST_RE.match(text):
            return "enum-constant"  # e.g. GAME_STATE_PAUSED
        if "_" in text and any(ch.isdigit() for ch in text):
            return "indexed-identifier"  # e.g. weight_001, node_42
        if (
            len(text) > _LONG_IDENTIFIER_THRESHOLD
            and _IDENTIFIER_RE.match(text)
            and text[0].isupper()
        ):
            return "long-identifier"  # long PascalCase compound, no spaces

    return None


def is_engine_noise(value: str) -> bool:
    return noise_reason(value) is not None
