"""
Preflight Tab — Hungarian Font Glyph Compatibility Checker & Unity Addressables CRC Fixer.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from gamestringer.core.font_checker import check_game_fonts
from gamestringer.core.addressables_crc import fix_catalog_crc_command
from gamestringer.desktop_gui.theme import (
    BG_DARK, BG_CARD, BG_ENTRY, FG_TEXT, FG_MUTED,
    ACCENT_CYAN, ACCENT_EMERALD, ACCENT_MAGENTA,
    FONT_HEADING, FONT_BODY, FONT_MONO
)


class PreflightTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, root: tk.Tk):
        super().__init__(parent, style="TFrame")
        self.root = root

        self._build_ui()

    def _build_ui(self):
        # Two stacked Labelframes: 1. Font Checker, 2. Addressables CRC Fixer
        main_container = ttk.Frame(self, style="TFrame", padding=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Section 1: Font Glyph Checker
        # -------------------------------------------------------------
        sec_font = ttk.Labelframe(main_container, text=" 🔤 Hungarian Font Glyph Checker (Unity / IL2CPP) ", style="TLabelframe", padding=12)
        sec_font.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        lbl_desc = tk.Label(
            sec_font,
            text="Scans Unity assets for TextMeshPro (TMP_FontAsset) and standard Font objects to verify Hungarian glyph support (ő/ű/Ő/Ű).\nNote: Unity and IL2CPP only. Unreal Engine font checking is currently marked unsupported.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=FG_MUTED,
            justify=tk.LEFT
        )
        lbl_desc.pack(anchor="w", pady=(0, 8))

        r_path = ttk.Frame(sec_font, style="Card.TFrame")
        r_path.pack(fill=tk.X, pady=4)

        ttk.Label(r_path, text="Game Directory/Asset:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=20).pack(side=tk.LEFT)
        self.var_font_path = tk.StringVar()
        ttk.Entry(r_path, textvariable=self.var_font_path, font=FONT_BODY).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(r_path, text="📂 Browse...", command=self._browse_font_path).pack(side=tk.LEFT)

        r_eng = ttk.Frame(sec_font, style="Card.TFrame")
        r_eng.pack(fill=tk.X, pady=4)

        ttk.Label(r_eng, text="Target Engine:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=20).pack(side=tk.LEFT)
        self.var_font_engine = tk.StringVar(value="unity")
        combo_eng = ttk.Combobox(
            r_eng,
            textvariable=self.var_font_engine,
            values=["unity", "il2cpp", "unreal", "renpy", "cri"],
            state="readonly",
            width=15
        )
        combo_eng.pack(side=tk.LEFT, padx=(0, 15))

        btn_font_run = ttk.Button(r_eng, text="🔍 Check Font Assets", style="Primary.TButton", command=self._run_font_check)
        btn_font_run.pack(side=tk.LEFT)

        self.txt_font_result = tk.Text(sec_font, height=6, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_MONO, bd=1, wrap=tk.WORD)
        self.txt_font_result.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # -------------------------------------------------------------
        # Section 2: Unity Addressables CRC Fixer
        # -------------------------------------------------------------
        sec_crc = ttk.Labelframe(main_container, text=" 🔧 Unity Addressables catalog.json CRC Fixer ", style="TLabelframe", padding=12)
        sec_crc.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        lbl_crc_desc = tk.Label(
            sec_crc,
            text="Recalculates CRC32 checksums for modified AssetBundles (.bundle / .assets) and updates catalog.json and *.hash files.\nRun this after reimporting modified translation files into Unity games.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=FG_MUTED,
            justify=tk.LEFT
        )
        lbl_crc_desc.pack(anchor="w", pady=(0, 8))

        r_crc_path = ttk.Frame(sec_crc, style="Card.TFrame")
        r_crc_path.pack(fill=tk.X, pady=4)

        ttk.Label(r_crc_path, text="Unity Game Directory:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=20).pack(side=tk.LEFT)
        self.var_crc_path = tk.StringVar()
        ttk.Entry(r_crc_path, textvariable=self.var_crc_path, font=FONT_BODY).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(r_crc_path, text="📂 Browse...", command=self._browse_crc_path).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(r_crc_path, text="⚡ Fix CRC Hashes", style="Primary.TButton", command=self._run_crc_fix).pack(side=tk.LEFT)

        self.txt_crc_result = tk.Text(sec_crc, height=6, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_MONO, bd=1, wrap=tk.WORD)
        self.txt_crc_result.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _browse_font_path(self):
        d = filedialog.askdirectory(title="Select Game Directory", parent=self.root)
        if d:
            self.var_font_path.set(d)

    def _browse_crc_path(self):
        d = filedialog.askdirectory(title="Select Game Directory (containing catalog.json)", parent=self.root)
        if d:
            self.var_crc_path.set(d)

    def _run_font_check(self):
        path = self.var_font_path.get().strip()
        eng = self.var_font_engine.get().strip()

        if not path:
            messagebox.showwarning("Input Required", "Please select a game directory or file.")
            return

        if not os.path.exists(path):
            messagebox.showerror("Error", f"Path does not exist: {path}")
            return

        self.txt_font_result.delete("1.0", tk.END)
        self.txt_font_result.insert(tk.END, f"Scanning fonts in '{path}' with engine '{eng}'...\n\n")

        try:
            res = check_game_fonts(path, eng)
            status = res.get("status", "unknown")
            msg = res.get("message", "")

            self.txt_font_result.insert(tk.END, f"Status: [{status.upper()}]\n")
            self.txt_font_result.insert(tk.END, f"Engine: {res.get('engine', eng)}\n")
            self.txt_font_result.insert(tk.END, f"Result: {msg}\n")

            if res.get("font_assets"):
                self.txt_font_result.insert(tk.END, f"\nDetected Font Assets:\n")
                for fa in res["font_assets"]:
                    self.txt_font_result.insert(tk.END, f"  • {fa}\n")

        except Exception as e:
            self.txt_font_result.insert(tk.END, f"[ERROR] Font check failed: {e}\n")

    def _run_crc_fix(self):
        path = self.var_crc_path.get().strip()
        if not path:
            messagebox.showwarning("Input Required", "Please select a game directory.")
            return

        if not os.path.exists(path):
            messagebox.showerror("Error", f"Directory does not exist: {path}")
            return

        self.txt_crc_result.delete("1.0", tk.END)
        self.txt_crc_result.insert(tk.END, f"Recalculating CRC32 checksums in '{path}'...\n\n")

        try:
            res = fix_catalog_crc_command(path)
            if res.get("catalog_found"):
                self.txt_crc_result.insert(tk.END, f"✅ SUCCESS: {res.get('message')}\n\n")
                if res.get("updated_files"):
                    self.txt_crc_result.insert(tk.END, "Updated AssetBundles:\n")
                    for uf in res["updated_files"]:
                        self.txt_crc_result.insert(tk.END, f"  • {uf}\n")
                if res.get("catalogs"):
                    self.txt_crc_result.insert(tk.END, "\nModified Catalogs:\n")
                    for c in res["catalogs"]:
                        self.txt_crc_result.insert(tk.END, f"  • {c}\n")
            else:
                self.txt_crc_result.insert(tk.END, f"⚠️ WARNING: {res.get('message')}\n")
        except Exception as e:
            self.txt_crc_result.insert(tk.END, f"[ERROR] CRC fix failed: {e}\n")
