"""
Preflight Tab — Hungarian Font Glyph Compatibility Checker & Unity Addressables CRC Fixer.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional

from gamestringer.core.font_checker import check_game_fonts
from gamestringer.core.addressables_crc import fix_catalog_crc_command
from gamestringer.core.backup import create_backup
from gamestringer.desktop_gui.theme import (
    BG_BASE, BG_SURFACE, BG_INSET, FG_TEXT, FG_MUTED,
    ACCENT_INK, ACCENT_MOSS, ACCENT_PAPRIKA, ACCENT_AMBER,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO
)
from gamestringer.desktop_gui.tooltip import create_tooltip
from gamestringer.desktop_gui.widgets import (
    section_frame, labeled_entry, labeled_combo, labeled_checkbutton, action_button, progress_bar
)


class PreflightTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        on_font_check_result_callback: Optional[Callable[[str, Optional[str]], None]] = None
    ):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.on_font_check_result_callback = on_font_check_result_callback
        self.is_font_checking = False
        self.is_crc_fixing = False

        self._build_ui()

    def _build_ui(self):
        main_container = ttk.Frame(self, style="TFrame", padding=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Section 1: Font Glyph Checker
        # -------------------------------------------------------------
        sec_font = section_frame(main_container, "🔤 Hungarian Font Glyph Checker (Unity / IL2CPP)", padding=12)
        sec_font.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        lbl_desc = tk.Label(
            sec_font,
            text="Scans Unity assets for TextMeshPro (TMP_FontAsset) and standard Font objects to verify Hungarian glyph support (ő/ű/Ő/Ű).\nSupported engines: Unity Mono and Unity IL2CPP.",
            font=FONT_BODY,
            bg=BG_SURFACE,
            fg=FG_MUTED,
            justify=tk.LEFT
        )
        lbl_desc.pack(anchor="w", pady=(0, 8))

        r_path = ttk.Frame(sec_font, style="Card.TFrame")
        r_path.pack(fill=tk.X, pady=4)

        self.var_font_path = tk.StringVar()
        r_f_entry, _ = labeled_entry(
            r_path, "Game Asset Path:", self.var_font_path, width=0, label_width=18,
            tooltip="Path to Unity game directory or asset file containing fonts / TextAsset localization tables"
        )
        r_f_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        action_button(r_path, "📂 Browse...", self._browse_font_path,
                      tooltip="Browse for game folder or asset file").pack(side=tk.LEFT)

        r_eng = ttk.Frame(sec_font, style="Card.TFrame")
        r_eng.pack(fill=tk.X, pady=4)

        self.var_font_engine = tk.StringVar(value="unity")
        r_combo, _ = labeled_combo(
            r_eng, "Target Engine:", self.var_font_engine,
            values=["unity", "il2cpp"],
            width=12, label_width=18,
            tooltip="Unity engine variant to scan (Unity Mono or Unity IL2CPP)"
        )
        r_combo.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_font_run = action_button(
            r_eng, "🔍 Check Font Assets", self._start_font_check,
            style="Primary.TButton", tooltip="Scan fonts and configuration files for Hungarian character support"
        )
        self.btn_font_run.pack(side=tk.LEFT, padx=(0, 10))

        self.pbar_font = progress_bar(r_eng, mode="indeterminate", length=140)

        self.txt_font_result = tk.Text(sec_font, height=5, bg=BG_INSET, fg=FG_TEXT, font=FONT_MONO, bd=1, wrap=tk.WORD)
        self.txt_font_result.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # -------------------------------------------------------------
        # Section 2: Unity Addressables CRC Fixer
        # -------------------------------------------------------------
        sec_crc = section_frame(main_container, "🔧 Unity Addressables catalog.json CRC Fixer", padding=12)
        sec_crc.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        lbl_crc_desc = tk.Label(
            sec_crc,
            text="Recalculates CRC32 checksums for modified AssetBundles (.bundle / .assets) and updates catalog.json and *.hash files.\nRun this after reimporting modified translation files into Unity Addressables games.",
            font=FONT_BODY,
            bg=BG_SURFACE,
            fg=FG_MUTED,
            justify=tk.LEFT
        )
        lbl_crc_desc.pack(anchor="w", pady=(0, 8))

        r_crc_path = ttk.Frame(sec_crc, style="Card.TFrame")
        r_crc_path.pack(fill=tk.X, pady=4)

        self.var_crc_path = tk.StringVar()
        r_c_entry, _ = labeled_entry(
            r_crc_path, "Unity Game Directory:", self.var_crc_path, width=0, label_width=20,
            tooltip="Root directory of the Unity game containing Addressables catalog.json / *.hash files"
        )
        r_c_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        action_button(r_crc_path, "📂 Browse...", self._browse_crc_path,
                      tooltip="Browse for game folder containing Addressables data").pack(side=tk.LEFT, padx=(0, 8))

        r_crc_act = ttk.Frame(sec_crc, style="Card.TFrame")
        r_crc_act.pack(fill=tk.X, pady=4)

        self.var_crc_backup = tk.BooleanVar(value=True)
        chk_bak = labeled_checkbutton(
            r_crc_act, "Create timestamped backup before modifying files (.bak_<timestamp>)",
            self.var_crc_backup,
            tooltip="Automatically create a backup copy of catalog.json and hash files before overwriting with new CRCs"
        )
        chk_bak.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_crc_run = action_button(
            r_crc_act, "⚡ Fix CRC Hashes", self._start_crc_fix,
            style="Primary.TButton", tooltip="Recalculate bundle CRC32 hashes and update catalog.json entries"
        )
        self.btn_crc_run.pack(side=tk.LEFT, padx=(0, 10))

        self.pbar_crc = progress_bar(r_crc_act, mode="indeterminate", length=140)

        self.txt_crc_result = tk.Text(sec_crc, height=5, bg=BG_INSET, fg=FG_TEXT, font=FONT_MONO, bd=1, wrap=tk.WORD)
        self.txt_crc_result.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _browse_font_path(self):
        d = filedialog.askdirectory(title="Select Game Directory or Asset Folder", parent=self.root)
        if d:
            self.var_font_path.set(d)

    def _browse_crc_path(self):
        d = filedialog.askdirectory(title="Select Game Directory (containing catalog.json)", parent=self.root)
        if d:
            self.var_crc_path.set(d)

    def _start_font_check(self):
        path = self.var_font_path.get().strip()
        eng = self.var_font_engine.get().strip()

        if not path:
            messagebox.showwarning("Input Required", "Please select a game directory or file.", parent=self.root)
            return

        if not os.path.exists(path):
            messagebox.showerror("Error", f"Path does not exist: {path}", parent=self.root)
            return

        if self.is_font_checking:
            return

        self.is_font_checking = True
        self.btn_font_run.config(state="disabled")
        self.pbar_font.pack(side=tk.LEFT)
        self.pbar_font.start(10)

        self.txt_font_result.delete("1.0", tk.END)
        self.txt_font_result.insert(tk.END, f"Scanning fonts in '{path}' with engine '{eng}'...\n\n")

        def worker():
            try:
                res = check_game_fonts(path, eng)
                self.root.after(0, self._on_font_check_complete, res, None)
            except Exception as e:
                self.root.after(0, self._on_font_check_complete, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_font_check_complete(self, res: Optional[dict], error: Optional[str]):
        self.is_font_checking = False
        self.pbar_font.stop()
        self.pbar_font.pack_forget()
        self.btn_font_run.config(state="normal")

        if error:
            self.txt_font_result.insert(tk.END, f"[ERROR] Font check failed: {error}\n")
            if self.on_font_check_result_callback:
                self.on_font_check_result_callback("error", None)
            return

        status = res.get("status", "unknown")
        msg = res.get("message", "")
        font_assets = res.get("font_assets", [])
        font_name = font_assets[0] if font_assets else None

        self.txt_font_result.insert(tk.END, f"Status: [{status.upper()}]\n")
        self.txt_font_result.insert(tk.END, f"Engine: {res.get('engine', 'unity')}\n")
        self.txt_font_result.insert(tk.END, f"Result: {msg}\n")

        if font_assets:
            self.txt_font_result.insert(tk.END, "\nDetected Font Assets:\n")
            for fa in font_assets:
                self.txt_font_result.insert(tk.END, f"  • {fa}\n")

        if self.on_font_check_result_callback:
            self.on_font_check_result_callback(status, font_name)

    def _start_crc_fix(self):
        path = self.var_crc_path.get().strip()
        if not path:
            messagebox.showwarning("Input Required", "Please select a game directory.", parent=self.root)
            return

        if not os.path.exists(path):
            messagebox.showerror("Error", f"Directory does not exist: {path}", parent=self.root)
            return

        if self.is_crc_fixing:
            return

        do_backup = self.var_crc_backup.get()
        confirm = messagebox.askyesno(
            "Confirm CRC Fix",
            f"Recalculate Addressables CRC32 hashes and update catalog files in:\n\n{path}\n\n"
            f"Backup enabled: {'YES' if do_backup else 'NO'}\n\nProceed?",
            icon="question",
            parent=self.root
        )
        if not confirm:
            return

        self.is_crc_fixing = True
        self.btn_crc_run.config(state="disabled")
        self.pbar_crc.pack(side=tk.LEFT)
        self.pbar_crc.start(10)

        self.txt_crc_result.delete("1.0", tk.END)
        self.txt_crc_result.insert(tk.END, f"Scanning catalog.json and bundles in '{path}'...\n\n")

        def worker():
            try:
                backup_logs = []
                if do_backup:
                    base_dir = os.path.abspath(path)
                    for root, _, files in os.walk(base_dir):
                        for f in files:
                            if f.lower() == "catalog.json" or f.lower().startswith("catalog_") or f.lower().endswith(".hash"):
                                full_p = os.path.join(root, f)
                                bak = create_backup(full_p)
                                backup_logs.append(f"Backup created: {os.path.basename(bak)}")

                res = fix_catalog_crc_command(path)
                self.root.after(0, self._on_crc_fix_complete, res, backup_logs, None)
            except Exception as e:
                self.root.after(0, self._on_crc_fix_complete, None, [], str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_crc_fix_complete(self, res: Optional[dict], backup_logs: list, error: Optional[str]):
        self.is_crc_fixing = False
        self.pbar_crc.stop()
        self.pbar_crc.pack_forget()
        self.btn_crc_run.config(state="normal")

        if error:
            self.txt_crc_result.insert(tk.END, f"[ERROR] CRC fix failed: {error}\n")
            return

        if backup_logs:
            self.txt_crc_result.insert(tk.END, f"Safety Backups:\n")
            for b in backup_logs:
                self.txt_crc_result.insert(tk.END, f"  • {b}\n")
            self.txt_crc_result.insert(tk.END, "\n")

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
