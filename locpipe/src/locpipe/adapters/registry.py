"""Format name (from project.yaml) -> FormatAdapter.

Status honestly reflects what's actually been ported as of this
scaffold, not what's aspirational:

  generic_kv    DONE — MindsEye's live format; ported and tested
                       against the real format-generic-kv.md spec.

  po_gettext    DONE — ported against format-po-gettext.md as proof
                       the pattern really is mechanical, not just
                       claimed. Uses polib rather than hand-parsing
                       .po syntax (see adapters/po_gettext.py for why,
                       and for the one known simplification it ships
                       with: plural forms are translated independently
                       per msgstr[N] rather than jointly).

  ue4_5_po      DONE — aliased to PoGettextAdapter; Unreal's Localization
                       Dashboard .po export (both of its non-Crowdin
                       collapse modes -- "Identical Text Identity and
                       Source Text" and "Identical Namespace and Source
                       Text", see Epic's localization docs) is standard
                       gettext with msgctxt carrying Unreal's identity/
                       namespace, not a different wire format -- polib
                       parses it correctly with zero UE-specific code.
                       What IS UE-specific and DOES need its own check:
                       the {Arg}|plural(...)/gender(...)/ordinal(...)
                       argument-modifier syntax -- see
                       validators/validate_ue4_5_po.py, registered only
                       for this format name, not for plain po_gettext.

  unity         DONE — ported from a working reference implementation
                       found while comparing locpipe against a
                       parallel pipeline (see README's "Bugs found and
                       fixed"). Wasn't needed for MindsEye itself
                       (generic_kv), built because the reusable-
                       platform story should mean something concrete
                       once in a while, not just be a claim.

  uabea_json    DONE — Unity/UABEA asset-dump export (see
                       adapters/uabea_json.py). Case 2/3 (typetree/array
                       walk, as opposed to Case 1's clean CSV-in-
                       m_Script) filters engine noise before it ever
                       becomes an Entry -- see adapters/engine_noise.py
                       and `locpipe audit`.

  weblate_xliff DONE — aliased to XLIFFAdapter; same wire format.

  renpy, ue3
                NOT PORTED — no adapter, no validator. Add both
                together (extract/merge + validate_file) if/when a
                project actually needs one of these formats; carrying
                half of a format (e.g. a validator with nothing to
                feed it) is dead weight, not a head start.
"""

from __future__ import annotations

from typing import Any

from .base import FormatAdapter
from .generic_kv import GenericKVAdapter
from .po_gettext import PoGettextAdapter
from .unity import UnityCSVAdapter
from .xliff import XLIFFAdapter
from .uabea_json import UABEAJsonAdapter

_NOT_YET_PORTED = {
    "renpy": "format-renpy.md",
    "ue3": "format-ue3.md",
}

# Adapters that take no construction-time config -- built once, reused.
_STATIC_REGISTRY: dict[str, FormatAdapter] = {
    "generic_kv": GenericKVAdapter(),
    "po_gettext": PoGettextAdapter(),
    "ue4_5_po": PoGettextAdapter(),
    "xliff": XLIFFAdapter(),
    "weblate_xliff": XLIFFAdapter(),
}

# Adapters that need project.yaml's format_options -- built fresh per
# call so a project's config actually reaches them (e.g. Unity's
# target column name).
_CONFIGURABLE_REGISTRY = {
    "unity": UnityCSVAdapter,
    "uabea_json": UABEAJsonAdapter,
    "bayonetta_json": UABEAJsonAdapter,
}


def get_adapter(format_name: str, format_options: dict[str, Any] | None = None) -> FormatAdapter:
    opts = format_options or {}
    if format_name == "uabea_json":
        return UABEAJsonAdapter(options=opts)
    if format_name in ("xliff", "weblate_xliff"):
        return XLIFFAdapter(options=opts)
    if format_name in _STATIC_REGISTRY:
        return _STATIC_REGISTRY[format_name]
    if format_name in _CONFIGURABLE_REGISTRY:
        if format_name == "unity":
            return UnityCSVAdapter(
                target_column_names=opts.get("target_column_names"),
                source_column_names=opts.get("source_column_names"),
                max_length_column_names=opts.get("max_length_column_names"),
            )
        return _CONFIGURABLE_REGISTRY[format_name]()
    if format_name in _NOT_YET_PORTED:
        spec_file = _NOT_YET_PORTED[format_name]
        raise NotImplementedError(
            f"'{format_name}' adapter isn't ported yet. The spec already exists "
            f"at .agents/context/{spec_file} in the old repo — port extract()/merge() "
            f"from it into locpipe/adapters/{format_name}.py and register it here."
        )
    known = sorted(list(_STATIC_REGISTRY) + list(_CONFIGURABLE_REGISTRY) + list(_NOT_YET_PORTED))
    raise ValueError(f"Unknown format '{format_name}'. Known: {known}")
