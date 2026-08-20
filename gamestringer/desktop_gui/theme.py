import sys
import tkinter as tk
from tkinter import ttk

BG_DARK = "#070a11"
BG_CARD = "#121926"
BG_ENTRY = "#090d16"
FG_TEXT = "#f0f6fc"
FG_MUTED = "#8b9bb4"
ACCENT_CYAN = "#00f3ff"
ACCENT_MAGENTA = "#ff007f"
ACCENT_EMERALD = "#00ff88"
BORDER_CYAN = "#00f3ff"

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_HEADING = (FONT_FAMILY, 11, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_MONO = ("Consolas", 9) if sys.platform == "win32" else ("Courier", 9)


def apply_theme(root: tk.Tk):
    """Configure modern dark ttk style colors and elements."""
    root.configure(bg=BG_DARK)
    
    style = ttk.Style(root)
    style.theme_use("clam")

    # Global TTK Defaults
    style.configure(".",
                    background=BG_DARK,
                    foreground=FG_TEXT,
                    fieldbackground=BG_ENTRY,
                    troughcolor=BG_ENTRY,
                    font=FONT_BODY,
                    bordercolor=BG_CARD)

    # Frame & Labelframe
    style.configure("TFrame", background=BG_DARK)
    style.configure("Card.TFrame", background=BG_CARD, relief="flat")
    
    style.configure("TLabelframe", background=BG_CARD, foreground=ACCENT_CYAN, borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=BG_CARD, foreground=ACCENT_CYAN, font=FONT_HEADING)

    # Notebook Tabs
    style.configure("TNotebook", background=BG_DARK, borderwidth=0)
    style.configure("TNotebook.Tab",
                    background=BG_CARD,
                    foreground=FG_MUTED,
                    padding=[16, 8],
                    font=FONT_HEADING,
                    borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", "#1a2436")],
              foreground=[("selected", ACCENT_CYAN)])

    # Buttons
    style.configure("TButton",
                    background=BG_CARD,
                    foreground=ACCENT_CYAN,
                    bordercolor=ACCENT_CYAN,
                    borderwidth=1,
                    padding=[12, 6],
                    font=FONT_HEADING,
                    focuscolor="none")
    style.map("TButton",
              background=[("active", "#1e293b")],
              foreground=[("active", "#ffffff")])

    style.configure("Primary.TButton",
                    background="#0072ff",
                    foreground="#ffffff",
                    font=(FONT_FAMILY, 10, "bold"),
                    padding=[16, 8])
    style.map("Primary.TButton",
              background=[("active", ACCENT_CYAN)],
              foreground=[("active", "#000000")])

    style.configure("Stop.TButton",
                    background="#ff0055",
                    foreground="#ffffff",
                    font=(FONT_FAMILY, 10, "bold"),
                    padding=[12, 6])
    style.map("Stop.TButton",
              background=[("active", "#ff5500")])

    # Inputs & Dropdowns
    style.configure("TEntry", fieldbackground=BG_ENTRY, foreground=ACCENT_CYAN, insertcolor=ACCENT_CYAN)
    style.configure("TCombobox", fieldbackground=BG_ENTRY, foreground=ACCENT_CYAN, background=BG_CARD)
    style.map("TCombobox", fieldbackground=[("readonly", BG_ENTRY)], foreground=[("readonly", ACCENT_CYAN)])

    # Checkbuttons & Radios
    style.configure("TCheckbutton", background=BG_CARD, foreground=FG_TEXT, font=FONT_BODY)
    style.map("TCheckbutton", background=[("active", BG_CARD)], foreground=[("active", ACCENT_CYAN)])

    # Progressbar
    style.configure("Horizontal.TProgressbar",
                    troughcolor=BG_ENTRY,
                    background=ACCENT_CYAN,
                    bordercolor=BG_CARD,
                    lightcolor=ACCENT_CYAN,
                    darkcolor=ACCENT_CYAN)

    # Treeview (Tables)
    style.configure("Treeview",
                    background=BG_CARD,
                    foreground=FG_TEXT,
                    fieldbackground=BG_CARD,
                    rowheight=24,
                    font=FONT_MONO)
    style.configure("Treeview.Heading",
                    background="#1a2436",
                    foreground=ACCENT_CYAN,
                    font=FONT_HEADING,
                    relief="flat")
    style.map("Treeview",
              background=[("selected", "#25344d")],
              foreground=[("selected", "#ffffff")])
