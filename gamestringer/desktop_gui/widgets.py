"""
Reusable UI Widget Builders with Integrated Tooltips & Editorial Styling.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, List, Optional, Tuple, Union

from gamestringer.desktop_gui.theme import (
    BG_SURFACE, BG_BASE, BG_INSET, FG_TEXT, FG_MUTED,
    ACCENT_INK, FONT_HEADING, FONT_BODY, FONT_MONO
)
from gamestringer.desktop_gui.tooltip import create_tooltip


def section_frame(
    parent: tk.Widget,
    title: str,
    padding: int = 10,
    style: str = "TLabelframe"
) -> ttk.Labelframe:
    """Create a styled Labelframe section."""
    frame = ttk.Labelframe(parent, text=f" {title} ", style=style, padding=padding)
    return frame


def labeled_entry(
    parent: tk.Widget,
    label_text: str,
    variable: tk.StringVar,
    width: int = 25,
    label_width: int = 15,
    readonly: bool = False,
    font: Any = FONT_BODY,
    tooltip: str = "",
    side: str = tk.LEFT
) -> Tuple[ttk.Frame, ttk.Entry]:
    """Create a labeled entry widget inside a container row."""
    row = ttk.Frame(parent, style="Card.TFrame")
    lbl = ttk.Label(
        row,
        text=label_text,
        font=FONT_HEADING,
        background=BG_SURFACE,
        foreground=ACCENT_INK,
        width=label_width
    )
    lbl.pack(side=tk.LEFT)

    state = "readonly" if readonly else "normal"
    entry = ttk.Entry(row, textvariable=variable, state=state, width=width, font=font)
    entry.pack(side=tk.LEFT, fill=tk.X if width <= 0 else tk.NONE, expand=width <= 0)

    if tooltip:
        create_tooltip(lbl, tooltip)
        create_tooltip(entry, tooltip)

    return row, entry


def labeled_combo(
    parent: tk.Widget,
    label_text: str,
    variable: tk.StringVar,
    values: List[str],
    width: int = 20,
    label_width: int = 15,
    state: str = "readonly",
    tooltip: str = ""
) -> Tuple[ttk.Frame, ttk.Combobox]:
    """Create a labeled combobox dropdown inside a container row."""
    row = ttk.Frame(parent, style="Card.TFrame")
    lbl = ttk.Label(
        row,
        text=label_text,
        font=FONT_HEADING,
        background=BG_SURFACE,
        foreground=ACCENT_INK,
        width=label_width
    )
    lbl.pack(side=tk.LEFT)

    combo = ttk.Combobox(row, textvariable=variable, values=values, state=state, width=width)
    combo.pack(side=tk.LEFT)

    if tooltip:
        create_tooltip(lbl, tooltip)
        create_tooltip(combo, tooltip)

    return row, combo


def labeled_checkbutton(
    parent: tk.Widget,
    text: str,
    variable: tk.BooleanVar,
    tooltip: str = ""
) -> ttk.Checkbutton:
    """Create a checkbutton with tooltip support."""
    chk = ttk.Checkbutton(parent, text=text, variable=variable)
    if tooltip:
        create_tooltip(chk, tooltip)
    return chk


def action_button(
    parent: tk.Widget,
    text: str,
    command: Callable[[], Any],
    style: str = "TButton",
    tooltip: str = ""
) -> ttk.Button:
    """Create a styled action button with tooltip support."""
    btn = ttk.Button(parent, text=text, command=command, style=style)
    if tooltip:
        create_tooltip(btn, tooltip)
    return btn


def progress_bar(
    parent: tk.Widget,
    mode: str = "indeterminate",
    length: int = 180,
    style: str = "Horizontal.TProgressbar"
) -> ttk.Progressbar:
    """Create a styled progress bar."""
    pbar = ttk.Progressbar(parent, orient=tk.HORIZONTAL, mode=mode, length=length, style=style)
    return pbar
