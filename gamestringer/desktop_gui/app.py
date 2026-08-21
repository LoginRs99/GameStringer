"""
GameStringer Desktop GUI — Editorial Proofing Console & Sidebar Navigation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import List, Optional

from gamestringer.desktop_gui.theme import (
    apply_theme, BG_BASE, BG_SURFACE, BG_INSET, FG_TEXT, FG_MUTED,
    ACCENT_INK, ACCENT_MOSS, ACCENT_PAPRIKA, ACCENT_AMBER,
    FONT_DISPLAY, FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO, FONT_FAMILY_DISPLAY, FONT_FAMILY_BODY
)
from gamestringer.desktop_gui.glyph_strip import GlyphStrip
from gamestringer.desktop_gui.tabs.projects_tab import ProjectsTab
from gamestringer.desktop_gui.tabs.preflight_tab import PreflightTab
from gamestringer.desktop_gui.tabs.audit_tab import AuditTab
from gamestringer.desktop_gui.tabs.run_tab import RunTab
from gamestringer.desktop_gui.tooltip import create_tooltip

SETTINGS_FILE = Path("gamestringer_gui_settings.json")


class NavItem(tk.Frame):
    """Custom sidebar navigation item with active indicator and hover feedback."""

    def __init__(self, parent: tk.Widget, label: str, icon: str, index: int, on_select):
        super().__init__(parent, bg=BG_SURFACE, cursor="hand2")
        self.index = index
        self.on_select = on_select
        self.is_active = False

        self.indicator = tk.Frame(self, bg=BG_SURFACE, width=4)
        self.indicator.pack(side=tk.LEFT, fill=tk.Y)

        self.lbl = tk.Label(
            self,
            text=f"{icon}  {label}",
            font=FONT_HEADING,
            bg=BG_SURFACE,
            fg=FG_MUTED,
            padx=12,
            pady=11,
            anchor="w"
        )
        self.lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for w in (self, self.lbl, self.indicator):
            w.bind("<Button-1>", lambda e: self.on_select(self.index))
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def set_active(self, active: bool):
        self.is_active = active
        if active:
            self.configure(bg=BG_BASE)
            self.lbl.configure(bg=BG_BASE, fg=FG_TEXT)
            self.indicator.configure(bg=ACCENT_INK)
        else:
            self.configure(bg=BG_SURFACE)
            self.lbl.configure(bg=BG_SURFACE, fg=FG_MUTED)
            self.indicator.configure(bg=BG_SURFACE)

    def _on_enter(self, event=None):
        if not self.is_active:
            self.configure(bg="#2E2C27")
            self.lbl.configure(bg="#2E2C27", fg=FG_TEXT)

    def _on_leave(self, event=None):
        if not self.is_active:
            self.configure(bg=BG_SURFACE)
            self.lbl.configure(bg=BG_SURFACE, fg=FG_MUTED)


class GameStringerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GameStringer — Localization Preflight & Translation Console")

        apply_theme(root)

        # Shared state
        self.shared_project_var = tk.StringVar(root, value="")
        self.current_tab_index = 0
        self.nav_items: List[NavItem] = []

        self._build_layout()
        self._build_menu()
        self._bind_shortcuts()
        self._load_settings()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self):
        # Master container: Left Sidebar + Right Content Area
        self.paned_main = tk.Frame(self.root, bg=BG_BASE)
        self.paned_main.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Left Sidebar (~190px, BG_SURFACE)
        # -------------------------------------------------------------
        self.sidebar = tk.Frame(
            self.paned_main,
            bg=BG_SURFACE,
            width=190,
            highlightbackground=BG_INSET,
            highlightthickness=1
        )
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Wordmark
        wordmark_frame = tk.Frame(self.sidebar, bg=BG_SURFACE, padx=12, pady=16)
        wordmark_frame.pack(fill=tk.X)

        lbl_wordmark = tk.Label(
            wordmark_frame,
            text="⌁ GameStringer",
            font=(FONT_FAMILY_DISPLAY, 16, "bold"),
            bg=BG_SURFACE,
            fg=ACCENT_INK,
            anchor="w"
        )
        lbl_wordmark.pack(fill=tk.X)

        lbl_edition = tk.Label(
            wordmark_frame,
            text="PROOFING CONSOLE",
            font=(FONT_FAMILY_BODY, 7, "bold"),
            bg=BG_SURFACE,
            fg=FG_MUTED,
            anchor="w",
            pady=2
        )
        lbl_edition.pack(fill=tk.X)

        # Divider
        tk.Frame(self.sidebar, bg=BG_INSET, height=1).pack(fill=tk.X, padx=8, pady=(0, 8))

        # Nav Buttons Stack
        nav_container = tk.Frame(self.sidebar, bg=BG_SURFACE)
        nav_container.pack(fill=tk.X, expand=True, anchor="n")

        nav_defs = [
            ("Projects", "📁", 0),
            ("Preflight", "🔤", 1),
            ("Audit", "🔇", 2),
            ("Run", "🚀", 3),
        ]

        for label, icon, idx in nav_defs:
            item = NavItem(nav_container, label, icon, idx, self.switch_tab)
            item.pack(fill=tk.X, pady=1)
            self.nav_items.append(item)

        # Pinned Glyph Strip at Bottom of Sidebar
        self.glyph_strip = GlyphStrip(self.sidebar)
        self.glyph_strip.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        # -------------------------------------------------------------
        # Right Main Content Area
        # -------------------------------------------------------------
        self.content_area = tk.Frame(self.paned_main, bg=BG_BASE)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Top Header Bar
        self.header_bar = tk.Frame(
            self.content_area,
            bg=BG_SURFACE,
            highlightbackground=BG_INSET,
            highlightthickness=1,
            padx=14,
            pady=8
        )
        self.header_bar.pack(fill=tk.X)

        self.lbl_active_proj = tk.Label(
            self.header_bar,
            text="Project: (None selected)",
            font=FONT_HEADING,
            bg=BG_SURFACE,
            fg=FG_TEXT
        )
        self.lbl_active_proj.pack(side=tk.LEFT)

        lbl_badge = tk.Label(
            self.header_bar,
            text="🔒 antigravity_cli • gemini-3.7-flash",
            font=FONT_MONO,
            bg=BG_INSET,
            fg=ACCENT_MOSS,
            padx=8,
            pady=3,
            relief="solid",
            bd=1
        )
        lbl_badge.pack(side=tk.RIGHT)
        create_tooltip(lbl_badge, "Active Translation Engine: Antigravity CLI (Gemini 3.7 Flash)")

        # Mount Tabs
        self.tab_container = tk.Frame(self.content_area, bg=BG_BASE)
        self.tab_container.pack(fill=tk.BOTH, expand=True)

        self.tab_projects = ProjectsTab(
            self.tab_container, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )
        self.tab_preflight = PreflightTab(
            self.tab_container, self.root,
            on_font_check_result_callback=self.glyph_strip.update_result
        )
        self.tab_audit = AuditTab(
            self.tab_container, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )
        self.tab_run = RunTab(
            self.tab_container, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )

        self.tabs = [self.tab_projects, self.tab_preflight, self.tab_audit, self.tab_run]
        self.switch_tab(0)

    def switch_tab(self, index: int):
        if not (0 <= index < len(self.tabs)):
            return

        # Check unsaved changes if leaving Projects tab
        if self.current_tab_index == 0 and index != 0:
            if not self.tab_projects.check_unsaved_changes():
                return

        self.current_tab_index = index

        # Update nav highlights
        for i, item in enumerate(self.nav_items):
            item.set_active(i == index)

        # Show target tab
        for i, tab in enumerate(self.tabs):
            if i == index:
                tab.pack(fill=tk.BOTH, expand=True)
            else:
                tab.pack_forget()

        # Trigger refresh behavior
        if index == 0:
            self.tab_projects.refresh_project_list()
        elif index == 2:
            self.tab_audit.refresh_projects()
        elif index == 3:
            self.tab_run.refresh_projects()

    def _on_project_changed(self, project_name: str):
        self.lbl_active_proj.config(text=f"Project: {project_name}" if project_name else "Project: (None selected)")
        self.tab_projects.select_project(project_name)
        self.tab_audit.select_project(project_name)
        self.tab_run.select_project(project_name)

    def _build_menu(self):
        menubar = tk.Menu(self.root, bg=BG_SURFACE, fg=FG_TEXT, activebackground=ACCENT_INK, activeforeground="#ffffff")

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_SURFACE, fg=FG_TEXT, activebackground=ACCENT_INK, activeforeground="#ffffff")
        file_menu.add_command(label="New Project...", command=self.tab_projects._create_new_project, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=BG_SURFACE, fg=FG_TEXT, activebackground=ACCENT_INK, activeforeground="#ffffff")
        edit_menu.add_command(label="Save Current Project", command=self.tab_projects.save_project, accelerator="Ctrl+S")
        edit_menu.add_command(label="Reload from Disk", command=self.tab_projects.reload_current_project)
        edit_menu.add_separator()
        edit_menu.add_command(label="Refresh Tab", command=self._refresh_current_tab, accelerator="F5")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=BG_SURFACE, fg=FG_TEXT, activebackground=ACCENT_INK, activeforeground="#ffffff")
        view_menu.add_command(label="1. Projects", command=lambda: self.switch_tab(0))
        view_menu.add_command(label="2. Preflight & Fixes", command=lambda: self.switch_tab(1))
        view_menu.add_command(label="3. Audit Noise", command=lambda: self.switch_tab(2))
        view_menu.add_command(label="4. Plan & Run", command=lambda: self.switch_tab(3))
        menubar.add_cascade(label="View", menu=view_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=BG_SURFACE, fg=FG_TEXT, activebackground=ACCENT_INK, activeforeground="#ffffff")
        help_menu.add_command(label="View Documentation", command=self._open_docs)
        help_menu.add_separator()
        help_menu.add_command(label="About GameStringer", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda e: self.tab_projects.save_project())
        self.root.bind("<Control-S>", lambda e: self.tab_projects.save_project())
        self.root.bind("<Control-n>", lambda e: self.tab_projects._create_new_project())
        self.root.bind("<Control-N>", lambda e: self.tab_projects._create_new_project())
        self.root.bind("<Control-q>", lambda e: self.on_close())
        self.root.bind("<Control-Q>", lambda e: self.on_close())
        self.root.bind("<F5>", lambda e: self._refresh_current_tab())
        self.root.bind("<Control-1>", lambda e: self.switch_tab(0))
        self.root.bind("<Control-2>", lambda e: self.switch_tab(1))
        self.root.bind("<Control-3>", lambda e: self.switch_tab(2))
        self.root.bind("<Control-4>", lambda e: self.switch_tab(3))

    def _refresh_current_tab(self):
        if self.current_tab_index == 0:
            self.tab_projects.refresh_project_list()
        elif self.current_tab_index == 2:
            self.tab_audit.refresh_projects()
        elif self.current_tab_index == 3:
            self.tab_run.refresh_projects()

    def _open_docs(self):
        readme_path = Path("README.md").resolve()
        if readme_path.exists():
            try:
                if sys.platform == "win32":
                    os.startfile(str(readme_path))
                else:
                    webbrowser.open(readme_path.as_uri())
            except Exception:
                webbrowser.open("https://github.com/LoginRs99/GameStringer")
        else:
            webbrowser.open("https://github.com/LoginRs99/GameStringer")

    def _show_about(self):
        messagebox.showinfo(
            "About GameStringer",
            "⌁ GameStringer v2.0.0 (Editorial Proofing Console)\n\n"
            "Unified LocPipe Desktop Preflight & Translation Manager\n"
            "Sole LLM Provider: Antigravity CLI (gemini-3.7-flash)\n\n"
            "• Manual game binary extraction (UABEA / Unreal PO)\n"
            "• Deterministic LocPipe translation pipeline\n"
            "• Preflight font glyph verification & Addressables CRC repair\n"
            "• Built-in engine noise auditor\n\n"
            "MIT License",
            parent=self.root
        )

    def _load_settings(self):
        geometry = "1120x820"
        self.root.geometry(geometry)
        self.root.minsize(960, 660)

        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                saved_geom = data.get("geometry")
                if saved_geom:
                    self.root.geometry(saved_geom)

                last_proj = data.get("last_project")
                if last_proj:
                    self.shared_project_var.set(last_proj)
                    self._on_project_changed(last_proj)

                last_tab = data.get("last_tab", 0)
                if isinstance(last_tab, int) and 0 <= last_tab < len(self.tabs):
                    self.switch_tab(last_tab)
            except Exception:
                pass

    def _save_settings(self):
        data = {
            "geometry": self.root.geometry(),
            "last_project": self.shared_project_var.get(),
            "last_tab": self.current_tab_index
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def on_close(self):
        if not self.tab_projects.check_unsaved_changes():
            return

        if self.tab_run.active_process and self.tab_run.active_process.poll() is None:
            try:
                self.tab_run.active_process.terminate()
            except Exception:
                pass

        self._save_settings()
        self.root.destroy()


def create_app() -> tk.Tk:
    root = tk.Tk()
    app = GameStringerApp(root)
    return root


def main():
    root = create_app()
    root.mainloop()


if __name__ == "__main__":
    main()
