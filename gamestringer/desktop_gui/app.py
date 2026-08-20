"""
GameStringer Desktop GUI — Project Config & Preflight Wrapper for LocPipe.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

from gamestringer.desktop_gui.theme import (
    apply_theme, BG_CARD, ACCENT_CYAN, FG_TEXT, FG_MUTED, FONT_TITLE, FONT_HEADING
)
from gamestringer.desktop_gui.tabs.projects_tab import ProjectsTab
from gamestringer.desktop_gui.tabs.preflight_tab import PreflightTab
from gamestringer.desktop_gui.tabs.audit_tab import AuditTab
from gamestringer.desktop_gui.tabs.run_tab import RunTab


def create_app() -> tk.Tk:
    root = tk.Tk()
    root.title("GameStringer — LocPipe Desktop Preflight & Translation Manager")
    root.geometry("1100x800")
    root.minsize(950, 650)

    apply_theme(root)

    # Top Header Banner
    header_frame = tk.Frame(root, bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightthickness=1)
    header_frame.pack(fill="x", padx=10, pady=(10, 5))

    lbl_title = tk.Label(
        header_frame,
        text="⚡ GAMESTRINGER",
        font=("Segoe UI", 18, "bold"),
        bg=BG_CARD,
        fg=ACCENT_CYAN
    )
    lbl_title.pack(anchor="w", padx=15, pady=(10, 2))

    lbl_subtitle = tk.Label(
        header_frame,
        text="LocPipe Project Config & Preflight GUI • Sole LLM Provider: Antigravity CLI (Gemini Flash)",
        font=("Segoe UI", 9),
        bg=BG_CARD,
        fg=FG_MUTED
    )
    lbl_subtitle.pack(anchor="w", padx=15, pady=(0, 10))

    # Notebook Tabs (4 Tabs)
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    tab_projects = ProjectsTab(notebook, root)
    tab_preflight = PreflightTab(notebook, root)
    tab_audit = AuditTab(notebook, root)
    tab_run = RunTab(notebook, root)

    notebook.add(tab_projects, text=" 📁 Projects ")
    notebook.add(tab_preflight, text=" 🔍 Preflight & Fixes ")
    notebook.add(tab_audit, text=" 🔇 Audit Noise ")
    notebook.add(tab_run, text=" 🚀 Plan & Run ")

    # When tab changes, refresh project list in audit and run tabs
    def on_tab_changed(event):
        selected_tab = notebook.select()
        tab_widget = notebook.nametowidget(selected_tab)
        if hasattr(tab_widget, "refresh_projects"):
            tab_widget.refresh_projects()
        elif hasattr(tab_widget, "refresh_project_list"):
            tab_widget.refresh_project_list()

    notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

    return root


def main():
    root = create_app()
    root.mainloop()


if __name__ == "__main__":
    main()
