"""
GameStringer Desktop GUI — Project Config & Preflight Wrapper for LocPipe.
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

from gamestringer.desktop_gui.theme import (
    apply_theme, BG_CARD, BG_DARK, ACCENT_CYAN, FG_TEXT, FG_MUTED, FONT_TITLE, FONT_HEADING, FONT_BODY
)
from gamestringer.desktop_gui.tabs.projects_tab import ProjectsTab
from gamestringer.desktop_gui.tabs.preflight_tab import PreflightTab
from gamestringer.desktop_gui.tabs.audit_tab import AuditTab
from gamestringer.desktop_gui.tabs.run_tab import RunTab

SETTINGS_FILE = Path("gamestringer_gui_settings.json")


class GameStringerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GameStringer — LocPipe Desktop Preflight & Translation Manager")

        apply_theme(root)

        # Shared state
        self.shared_project_var = tk.StringVar(root, value="")

        self._build_header()
        self._build_tabs()
        self._build_menu()
        self._bind_shortcuts()
        self._load_settings()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_header(self):
        header_frame = tk.Frame(self.root, bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightthickness=1)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        lbl_title = tk.Label(
            header_frame,
            text="⚡ GAMESTRINGER",
            font=("Segoe UI", 18, "bold"),
            bg=BG_CARD,
            fg=ACCENT_CYAN
        )
        lbl_title.pack(anchor="w", padx=15, pady=(8, 2))

        lbl_subtitle = tk.Label(
            header_frame,
            text="LocPipe Project Config & Preflight GUI • Sole LLM Provider: Antigravity CLI (Gemini Flash)",
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=FG_MUTED
        )
        lbl_subtitle.pack(anchor="w", padx=15, pady=(0, 8))

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.tab_projects = ProjectsTab(
            self.notebook, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )
        self.tab_preflight = PreflightTab(self.notebook, self.root)
        self.tab_audit = AuditTab(
            self.notebook, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )
        self.tab_run = RunTab(
            self.notebook, self.root,
            shared_project_var=self.shared_project_var,
            on_project_changed_callback=self._on_project_changed
        )

        self.notebook.add(self.tab_projects, text=" 📁 Projects ")
        self.notebook.add(self.tab_preflight, text=" 🔍 Preflight & Fixes ")
        self.notebook.add(self.tab_audit, text=" 🔇 Audit Noise ")
        self.notebook.add(self.tab_run, text=" 🚀 Plan & Run ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_switched)

    def _on_tab_switched(self, event=None):
        selected_idx = self.notebook.index(self.notebook.select())
        # Refresh current tab if needed
        if selected_idx == 0:
            self.tab_projects.refresh_project_list()
        elif selected_idx == 2:
            self.tab_audit.refresh_projects()
        elif selected_idx == 3:
            self.tab_run.refresh_projects()

    def _on_project_changed(self, project_name: str):
        self.tab_projects.select_project(project_name)
        self.tab_audit.select_project(project_name)
        self.tab_run.select_project(project_name)

    def _build_menu(self):
        menubar = tk.Menu(self.root, bg=BG_CARD, fg=FG_TEXT, activebackground=ACCENT_CYAN, activeforeground="#000000")

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_CARD, fg=FG_TEXT, activebackground=ACCENT_CYAN, activeforeground="#000000")
        file_menu.add_command(label="New Project...", command=self.tab_projects._create_new_project, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=BG_CARD, fg=FG_TEXT, activebackground=ACCENT_CYAN, activeforeground="#000000")
        edit_menu.add_command(label="Save Current Project", command=self.tab_projects.save_project, accelerator="Ctrl+S")
        edit_menu.add_command(label="Reload from Disk", command=self.tab_projects.reload_current_project)
        edit_menu.add_separator()
        edit_menu.add_command(label="Refresh Tab", command=self._refresh_current_tab, accelerator="F5")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=BG_CARD, fg=FG_TEXT, activebackground=ACCENT_CYAN, activeforeground="#000000")
        help_menu.add_command(label="View README Documentation", command=self._open_docs)
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

    def _refresh_current_tab(self):
        selected_idx = self.notebook.index(self.notebook.select())
        if selected_idx == 0:
            self.tab_projects.refresh_project_list()
        elif selected_idx == 2:
            self.tab_audit.refresh_projects()
        elif selected_idx == 3:
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
            "⚡ GameStringer v2.0.0\n\n"
            "Unified LocPipe Desktop Preflight & Translation Manager\n"
            "Sole LLM Provider: Antigravity CLI (gemini-3.7-flash)\n\n"
            "• Manual game binary extraction (UABEA / Unreal PO)\n"
            "• Deterministic LocPipe translation pipeline\n"
            "• Preflight font checker & Addressables CRC repair\n"
            "• Built-in engine noise auditor\n\n"
            "MIT License",
            parent=self.root
        )

    def _load_settings(self):
        # Default geometry
        geometry = "1100x800"
        self.root.geometry(geometry)
        self.root.minsize(950, 650)

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

                last_tab = data.get("last_tab")
                if isinstance(last_tab, int) and 0 <= last_tab < self.notebook.index("end"):
                    self.notebook.select(last_tab)
            except Exception:
                pass

    def _save_settings(self):
        try:
            cur_tab = self.notebook.index(self.notebook.select())
        except Exception:
            cur_tab = 0

        data = {
            "geometry": self.root.geometry(),
            "last_project": self.shared_project_var.get(),
            "last_tab": cur_tab
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def on_close(self):
        # Guard against unsaved changes
        if not self.tab_projects.check_unsaved_changes():
            return

        # Stop any active background processes
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
