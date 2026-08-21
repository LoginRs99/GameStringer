"""
Theme definition — Editorial Proofing Console token system & font fallback chains.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# 1. Semantic Color Token System
# ----------------------------------------------------------------------
BG_BASE = "#1C1B19"       # Application canvas background
BG_SURFACE = "#262420"    # Panels, cards, sidebar, labelframes
BG_INSET = "#14130F"      # Inputs, tables, text areas, log console
FG_TEXT = "#EDE7DD"       # Primary text
FG_MUTED = "#948C7E"      # Secondary / muted text
ACCENT_INK = "#3A6B7A"    # Brand, nav selection, focus rings, headers
ACCENT_MOSS = "#5C7A52"   # Success, "kept" audit state, supported font
ACCENT_PAPRIKA = "#B23A22"# Errors, destructive actions, missing glyphs
ACCENT_AMBER = "#D89B3C"  # Warnings, noise / excluded audit states

# ----------------------------------------------------------------------
# 2. Font Fallback Chains
# ----------------------------------------------------------------------
FONT_DISPLAY_CANDIDATES = ["Georgia", "Constantia", "Times New Roman", "DejaVu Serif"]
FONT_BODY_CANDIDATES = ["Segoe UI", "Helvetica Neue", "Helvetica", "DejaVu Sans", "Arial"]
FONT_MONO_CANDIDATES = ["Cascadia Mono", "Cascadia Code", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"]

_FONT_CACHE: Dict[Tuple[str, ...], str] = {}


def get_best_font_family(candidates: List[str]) -> str:
    """Find the first installed font from candidates list, cached after initial check."""
    key = tuple(candidates)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    try:
        available = set(tkfont.families())
    except Exception:
        available = set()

    for name in candidates:
        if name in available:
            _FONT_CACHE[key] = name
            return name

    fallback = candidates[0] if candidates else ""
    _FONT_CACHE[key] = fallback
    return fallback


FONT_FAMILY_DISPLAY = get_best_font_family(FONT_DISPLAY_CANDIDATES)
FONT_FAMILY_BODY = get_best_font_family(FONT_BODY_CANDIDATES)
FONT_FAMILY_MONO = get_best_font_family(FONT_MONO_CANDIDATES)

FONT_FAMILY = FONT_FAMILY_BODY
FONT_DISPLAY = (FONT_FAMILY_DISPLAY, 15, "bold")
FONT_TITLE = (FONT_FAMILY_DISPLAY, 15, "bold")
FONT_HEADING = (FONT_FAMILY_BODY, 10, "bold")
FONT_BODY = (FONT_FAMILY_BODY, 10)
FONT_MONO = (FONT_FAMILY_MONO, 9)


def apply_theme(root: tk.Tk):
    """Configure modern editorial dark ttk style colors and elements."""
    root.configure(bg=BG_BASE)

    style = ttk.Style(root)
    style.theme_use("clam")

    # Global TTK Defaults
    style.configure(
        ".",
        background=BG_BASE,
        foreground=FG_TEXT,
        fieldbackground=BG_INSET,
        troughcolor=BG_INSET,
        font=FONT_BODY,
        bordercolor=BG_SURFACE
    )

    # Frame & Labelframe
    style.configure("TFrame", background=BG_BASE)
    style.configure("Card.TFrame", background=BG_SURFACE, relief="flat")

    style.configure(
        "TLabelframe",
        background=BG_SURFACE,
        foreground=ACCENT_INK,
        borderwidth=1,
        relief="solid"
    )
    style.configure(
        "TLabelframe.Label",
        background=BG_SURFACE,
        foreground=ACCENT_INK,
        font=FONT_HEADING
    )

    # Buttons
    style.configure(
        "TButton",
        background=BG_SURFACE,
        foreground=FG_TEXT,
        bordercolor=ACCENT_INK,
        borderwidth=1,
        padding=[12, 5],
        font=FONT_HEADING,
        focuscolor="none"
    )
    style.map(
        "TButton",
        background=[("active", "#33302B")],
        foreground=[("active", "#ffffff")]
    )

    style.configure(
        "Primary.TButton",
        background=ACCENT_INK,
        foreground="#ffffff",
        font=FONT_HEADING,
        padding=[14, 6]
    )
    style.map(
        "Primary.TButton",
        background=[("active", "#4B8394")],
        foreground=[("active", "#ffffff")]
    )

    style.configure(
        "Stop.TButton",
        background=ACCENT_PAPRIKA,
        foreground="#ffffff",
        font=FONT_HEADING,
        padding=[12, 5]
    )
    style.map(
        "Stop.TButton",
        background=[("active", "#C8462C")]
    )

    # Inputs & Dropdowns
    style.configure(
        "TEntry",
        fieldbackground=BG_INSET,
        foreground=FG_TEXT,
        insertcolor=ACCENT_INK
    )
    style.configure(
        "TCombobox",
        fieldbackground=BG_INSET,
        foreground=FG_TEXT,
        background=BG_SURFACE
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_INSET)],
        foreground=[("readonly", FG_TEXT)]
    )

    # Checkbuttons & Radios
    style.configure(
        "TCheckbutton",
        background=BG_SURFACE,
        foreground=FG_TEXT,
        font=FONT_BODY
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG_SURFACE)],
        foreground=[("active", ACCENT_INK)]
    )

    # Progressbar
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=BG_INSET,
        background=ACCENT_INK,
        bordercolor=BG_SURFACE,
        lightcolor=ACCENT_INK,
        darkcolor=ACCENT_INK
    )

    # Treeview (Tables)
    style.configure(
        "Treeview",
        background=BG_INSET,
        foreground=FG_TEXT,
        fieldbackground=BG_INSET,
        rowheight=24,
        font=FONT_MONO
    )
    style.configure(
        "Treeview.Heading",
        background=BG_SURFACE,
        foreground=ACCENT_INK,
        font=FONT_HEADING,
        relief="flat"
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT_INK)],
        foreground=[("selected", "#ffffff")]
    )

    # Scrollbars
    style.configure(
        "TScrollbar",
        background=BG_SURFACE,
        troughcolor=BG_INSET,
        bordercolor=BG_BASE,
        arrowcolor=FG_MUTED
    )
