"""
Audit Tab — Extraction Noise & Exclusion Auditor for LocPipe (no LLM calls).
"""

from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional
import yaml

from locpipe.config import load_project, ProjectConfig
from locpipe.adapters.registry import get_adapter
from locpipe.audit import build_audit_report, render_report_markdown
from gamestringer.desktop_gui.tabs.projects_tab import get_default_projects_dir
from gamestringer.desktop_gui.theme import (
    BG_DARK, BG_CARD, BG_ENTRY, FG_TEXT, FG_MUTED,
    ACCENT_CYAN, ACCENT_EMERALD, ACCENT_MAGENTA,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO
)


class AuditTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, root: tk.Tk):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.projects_dir = get_default_projects_dir()
        self.current_project_dir: Optional[Path] = None
        self.audit_records: List[Dict[str, str]] = []

        self._build_ui()
        self.refresh_projects()

    def _build_ui(self):
        main_frame = ttk.Frame(self, style="TFrame", padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top Control Bar
        top_bar = ttk.Frame(main_frame, style="Card.TFrame", padding=8)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(top_bar, text="Project:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN).pack(side=tk.LEFT, padx=(5, 5))

        self.var_selected_project = tk.StringVar()
        self.combo_project = ttk.Combobox(
            top_bar,
            textvariable=self.var_selected_project,
            state="readonly",
            width=25,
        )
        self.combo_project.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_project.bind("<<ComboboxSelected>>", self._on_project_changed)

        ttk.Button(top_bar, text="🔄 Refresh", command=self.refresh_projects).pack(side=tk.LEFT, padx=(0, 10))

        btn_run = ttk.Button(top_bar, text="⚡ Run Extraction Audit", style="Primary.TButton", command=self.run_audit)
        btn_run.pack(side=tk.LEFT, padx=(0, 10))

        btn_exclude = ttk.Button(top_bar, text="🚫 Exclude Selected Path", command=self.exclude_selected_path)
        btn_exclude.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_status = tk.Label(top_bar, text="", font=FONT_BODY, bg=BG_CARD, fg=ACCENT_EMERALD)
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Summary Metrics Frame
        self.summary_frame = ttk.Labelframe(main_frame, text=" Audit Summary ", style="TLabelframe", padding=10)
        self.summary_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_metrics = tk.Label(
            self.summary_frame,
            text="Select a project and click 'Run Extraction Audit' to inspect translatable text vs. engine noise.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=FG_TEXT,
            justify=tk.LEFT
        )
        self.lbl_metrics.pack(anchor="w")

        # Table Filter Bar
        filter_bar = ttk.Frame(main_frame, style="TFrame")
        filter_bar.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(filter_bar, text="Filter Action:", font=FONT_BODY, background=BG_DARK, foreground=FG_TEXT).pack(side=tk.LEFT, padx=(0, 5))
        self.var_filter_action = tk.StringVar(value="ALL")
        self.combo_filter = ttk.Combobox(
            filter_bar,
            textvariable=self.var_filter_action,
            values=["ALL", "kept", "noise:*", "excluded_by_config"],
            state="readonly",
            width=18
        )
        self.combo_filter.pack(side=tk.LEFT, padx=(0, 15))
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        ttk.Label(filter_bar, text="Search Path / Text:", font=FONT_BODY, background=BG_DARK, foreground=FG_TEXT).pack(side=tk.LEFT, padx=(0, 5))
        self.var_search = tk.StringVar()
        entry_search = ttk.Entry(filter_bar, textvariable=self.var_search, width=30)
        entry_search.pack(side=tk.LEFT, padx=(0, 8))
        entry_search.bind("<KeyRelease>", lambda e: self._apply_filter())

        # Table (Treeview)
        table_frame = ttk.Frame(main_frame, style="TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("file", "path", "action", "value")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("file", text="Asset / File")
        self.tree.heading("path", text="JSON Path")
        self.tree.heading("action", text="Action / Reason")
        self.tree.heading("value", text="Extracted String Value")

        self.tree.column("file", width=140, anchor="w")
        self.tree.column("path", width=260, anchor="w")
        self.tree.column("action", width=150, anchor="center")
        self.tree.column("value", width=420, anchor="w")

        v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

    def refresh_projects(self):
        self.projects_dir = get_default_projects_dir()
        projs = []
        if self.projects_dir.exists():
            for p in sorted(self.projects_dir.iterdir()):
                if p.is_dir() and (p / "project.yaml").exists():
                    projs.append(p.name)

        self.combo_project["values"] = projs
        if projs:
            if not self.var_selected_project.get() or self.var_selected_project.get() not in projs:
                self.var_selected_project.set(projs[0])
                self.current_project_dir = self.projects_dir / projs[0]
        else:
            self.var_selected_project.set("")
            self.current_project_dir = None

    def _on_project_changed(self, event=None):
        name = self.var_selected_project.get()
        if name:
            self.current_project_dir = self.projects_dir / name

    def run_audit(self):
        if not self.current_project_dir or not (self.current_project_dir / "project.yaml").exists():
            messagebox.showwarning("No Project", "Please select a valid project first.")
            return

        try:
            config = load_project(self.current_project_dir)
            adapter = get_adapter(config.format, config.format_options)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project: {e}")
            return

        self.audit_records.clear()
        files_scanned = 0
        files_failed = []

        import inspect
        supports_sink = "audit_sink" in inspect.signature(adapter.extract).parameters

        if not supports_sink:
            self.lbl_metrics.config(
                text=f"Format adapter '{config.format}' does not support typetree audit sink (only uabea_json Case 2/3 currently uses this).",
                fg=ACCENT_CYAN
            )
            self._render_records()
            return

        for path in config.batch_files:
            sink: list[tuple[str, str, str]] = []
            try:
                adapter.extract(path, audit_sink=sink)
                files_scanned += 1
            except Exception as e:
                files_failed.append(f"{path.name}: {e}")
                continue

            for json_path, value, action in sink:
                self.audit_records.append({
                    "file": path.stem,
                    "path": json_path,
                    "action": action,
                    "value": value
                })

        # Calculate metrics
        kept_count = sum(1 for r in self.audit_records if r["action"] == "kept")
        ex_count = sum(1 for r in self.audit_records if r["action"] == "excluded_by_config")
        noise_count = sum(1 for r in self.audit_records if r["action"].startswith("noise:"))
        total_scanned = len(self.audit_records)
        skipped_pct = (100.0 * (ex_count + noise_count) / total_scanned) if total_scanned > 0 else 0.0

        summary_text = (
            f"Files Scanned: {files_scanned} | Total Strings: {total_scanned}\n"
            f"✅ Kept (Sent to LLM): {kept_count} | 🚫 Config Excluded: {ex_count} | "
            f"🔇 Engine Noise Filtered: {noise_count} ({skipped_pct:.1f}% filtered out of LLM calls)"
        )
        self.lbl_metrics.config(text=summary_text, fg=FG_TEXT)
        self._apply_filter()

    def _apply_filter(self):
        action_filter = self.var_filter_action.get()
        search_query = self.var_search.get().lower().strip()

        filtered = []
        for r in self.audit_records:
            act = r["action"]
            if action_filter == "kept" and act != "kept":
                continue
            elif action_filter == "noise:*" and not act.startswith("noise:"):
                continue
            elif action_filter == "excluded_by_config" and act != "excluded_by_config":
                continue

            if search_query:
                if search_query not in r["path"].lower() and search_query not in r["value"].lower() and search_query not in r["file"].lower():
                    continue

            filtered.append(r)

        self._render_records(filtered)

    def _render_records(self, records: Optional[List[Dict[str, str]]] = None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        to_show = records if records is not None else self.audit_records
        # Cap display at 2000 rows for smooth UI performance
        for r in to_show[:2000]:
            preview_val = r["value"].replace("\n", "\\n")
            if len(preview_val) > 80:
                preview_val = preview_val[:77] + "..."
            self.tree.insert("", tk.END, values=(r["file"], r["path"], r["action"], preview_val))

    def exclude_selected_path(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Row", "Please select a row in the table to exclude its path.")
            return

        item = self.tree.item(sel[0], "values")
        json_path = item[1]

        if not self.current_project_dir:
            return

        cfg_file = self.current_project_dir / "project.yaml"
        if not cfg_file.exists():
            return

        try:
            cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
            format_opts = cfg.setdefault("format_options", {})
            excludes = format_opts.setdefault("uabea_json_path_exclude", [])
            if not isinstance(excludes, list):
                excludes = [str(excludes)]
                format_opts["uabea_json_path_exclude"] = excludes

            # Add exact path regex pattern if not already present
            pattern = f"^{json_path}$"
            if pattern not in excludes and json_path not in excludes:
                excludes.append(pattern)
                cfg_file.write_text(yaml.dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
                self.lbl_status.config(text=f"🚫 Excluded pattern '{pattern}' in project.yaml", fg=ACCENT_CYAN)
                messagebox.showinfo("Path Excluded", f"Added '{pattern}' to format_options.uabea_json_path_exclude in project.yaml.")
                self.run_audit()
            else:
                messagebox.showinfo("Already Excluded", f"Pattern for '{json_path}' is already in excludes list.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update project.yaml: {e}")
