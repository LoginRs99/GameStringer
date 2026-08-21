"""
Glyph Strip Signature Widget — Displays Hungarian glyph rendering state (ő ű Ő Ű).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from typing import Optional

from gamestringer.desktop_gui.theme import (
    BG_SURFACE, BG_INSET, FG_TEXT, FG_MUTED,
    ACCENT_INK, ACCENT_MOSS, ACCENT_PAPRIKA, ACCENT_AMBER,
    FONT_DISPLAY, FONT_FAMILY_DISPLAY, FONT_FAMILY_BODY
)
from gamestringer.desktop_gui.tooltip import create_tooltip


class GlyphStrip(tk.Frame):
    """Pinned sidebar widget displaying Hungarian glyph test status."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, bg=BG_SURFACE, highlightbackground=BG_INSET, highlightthickness=1, padx=8, pady=8)

        self.current_family = FONT_FAMILY_DISPLAY
        self.current_color = FG_MUTED

        lbl_header = tk.Label(
            self,
            text="GLYPH AUDIT",
            font=(FONT_FAMILY_BODY, 8, "bold"),
            bg=BG_SURFACE,
            fg=FG_MUTED,
            anchor="w"
        )
        lbl_header.pack(fill=tk.X)

        self.lbl_glyphs = tk.Label(
            self,
            text="ő  ű  Ő  Ű",
            font=(self.current_family, 14, "bold"),
            bg=BG_SURFACE,
            fg=self.current_color,
            pady=4
        )
        self.lbl_glyphs.pack(fill=tk.X)

        self.lbl_status = tk.Label(
            self,
            text="No font check run yet",
            font=(FONT_FAMILY_BODY, 8),
            bg=BG_SURFACE,
            fg=FG_MUTED,
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X)

        create_tooltip(
            self,
            "Hungarian Glyph Proofing Strip (ő ű Ő Ű):\n"
            "• Gray: Unchecked\n"
            "• Green (Moss): Verified supported in game font\n"
            "• Red (Paprika): Missing or unsupported font"
        )

    def update_result(self, status: str, font_name: Optional[str] = None):
        """Update glyph strip state based on preflight font check result."""
        status_clean = (status or "").lower()

        if status_clean in ("supported", "ok", "passed"):
            self.current_color = ACCENT_MOSS
            status_text = f"✓ Supported ({font_name or 'Font OK'})"
        elif status_clean in ("warning", "partial"):
            self.current_color = ACCENT_AMBER
            status_text = f"⚠ Fallback needed ({font_name or 'Warning'})"
        else:
            self.current_color = ACCENT_PAPRIKA
            status_text = f"✗ Missing glyphs ({font_name or 'Unsupported'})"

        # If font_name is an installed font family, try to use it
        if font_name:
            try:
                available = set(tkfont.families())
                if font_name in available:
                    self.current_family = font_name
            except Exception:
                pass

        self.lbl_glyphs.config(
            fg=self.current_color,
            font=(self.current_family, 14, "bold")
        )
        self.lbl_status.config(
            text=status_text,
            fg=self.current_color
        )
