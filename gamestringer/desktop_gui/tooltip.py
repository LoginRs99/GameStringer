"""
Modern Editorial Tooltip Component for Tkinter/TTK.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from gamestringer.desktop_gui.theme import (
    BG_INSET, FG_TEXT, ACCENT_INK, FONT_FAMILY
)


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 500):
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self.tip_window: Optional[tk.Toplevel] = None
        self.scheduled_id: Optional[str] = None

        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_click, add="+")
        self.widget.bind("<Unmap>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        if self.text:
            self.scheduled_id = self.widget.after(self.delay_ms, self._show_tip)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide_tip()

    def _on_click(self, event=None):
        self._cancel()
        self._hide_tip()

    def _cancel(self):
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None

    def _show_tip(self):
        if self.tip_window or not self.text:
            return

        try:
            x, y, cx, cy = self.widget.bbox("insert") or (0, 0, self.widget.winfo_width(), self.widget.winfo_height())
        except Exception:
            x = y = 0

        # Compute root screen coordinates
        root_x = self.widget.winfo_rootx() + 15
        root_y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Create floating borderless window
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{root_x}+{root_y}")
        tw.attributes("-topmost", True)

        frame = tk.Frame(
            tw,
            bg=BG_INSET,
            highlightbackground=ACCENT_INK,
            highlightthickness=1,
            padx=8,
            pady=5
        )
        frame.pack(fill=tk.BOTH, expand=True)

        label = tk.Label(
            frame,
            text=self.text,
            justify=tk.LEFT,
            bg=BG_INSET,
            fg=FG_TEXT,
            font=(FONT_FAMILY, 9),
            wraplength=380
        )
        label.pack()

    def _hide_tip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass

    def update_text(self, new_text: str):
        self.text = new_text.strip()


def create_tooltip(widget: tk.Widget, text: str, delay_ms: int = 500) -> ToolTip:
    """Attach a hover tooltip to a Tkinter widget."""
    return ToolTip(widget, text, delay_ms=delay_ms)
