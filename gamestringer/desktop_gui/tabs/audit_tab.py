"""
Audit Tab — Extraction Noise & Exclusion Auditor for LocPipe (no LLM calls).
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable, Dict, List, Optional
import yaml

from locpipe.config import load_project, ProjectConfig
from locpipe.adapters.registry import get_adapter
from gamestringer.desktop_gui.tabs.projects_tab import get_default_projects_dir
from gamestringer.desktop_gui.theme import (
    BG_BASE, BG_SURFACE, BG_INSET, FG_TEXT, FG_MUTED,
    ACCENT_INK, ACCENT_MOSS, ACCENT_PAPRIKA, ACCENT_AMBER,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO
)
from gamestringer.desktop_gui.tooltip import create_tooltip
from gamestringer.desktop_gui.widgets import (
    section_frame, labeled_entry, labeled_combo, action_button, progress_bar
)


class AuditTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        shared_project_var: Optional[tk.StringVar] = None,
        on_project_changed_callback: Optional[Callable[[str], None]] = None
    ):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.shared_project_var = shared_project_var
        self.on_project_changed_callback = on_project_changed_callback

        self.projects_dir = get_default_projects_dir()
        self.current_project_dir: Optional[Path] = None
        self.audit_records: List[Dict[str, str]] = []
        self.is_auditing = False

        self._build_ui()
        self.refresh_projects()

    def _build_ui(self):
        main_frame = ttk.Frame(self, style="TFrame", padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Workflow Guide Card (Always visible)
        explainer_frame = section_frame(main_frame, "📖 Extraction Audit Workflow", padding=8)
        explainer_frame.pack(fill=tk.X, pady=(0, 8))

        explainer_text = (
            "• Purpose: Scans project batch files with ZERO LLM calls/cost to classify extracted strings.\n"
            "• Classifications: [kept] translatable text sent to LLM | [noise:*] auto-filtered engine noise (GUIDs, types, colors) | [excluded_by_config] filtered by path rules.\n"
            "• Recommended Order: Run this audit BEFORE translating. Filter by 'kept', check for unwanted engine strings, click 'Exclude Selected Path' to filter them out, then proceed to the Run tab."
        )
        lbl_explainer = tk.Label(
            explainer_frame,
            text=explainer_text,
            font=FONT_BODY,
            bg=BG_SURFACE,
            fg=FG_TEXT,
            justify=tk.LEFT,
            anchor="w"
        )
        lbl_explainer.pack(fill=tk.X)

        # Top Control Bar
        top_bar = ttk.Frame(main_frame, style="Card.TFrame", padding=8)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(top_bar, text="Project:", font=FONT_HEADING, background=BG_SURFACE, foreground=ACCENT_INK).pack(side=tk.LEFT, padx=(5, 5))

        self.var_selected_project = tk.StringVar()
        self.combo_project = ttk.Combobox(
            top_bar,
            textvariable=self.var_selected_project,
            state="readonly",
            width=22,
        )
        self.combo_project.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_project.bind("<<ComboboxSelected>>", self._on_project_changed)
        create_tooltip(self.combo_project, "Select active project for non-LLM extraction noise auditing")

        action_button(top_bar, "🔄 Refresh", self.refresh_projects,
                      tooltip="Refresh list of projects from disk").pack(side=tk.LEFT, padx=(0, 10))

        self.btn_run = action_button(
            top_bar, "⚡ Run Extraction Audit", self._start_audit,
            style="Primary.TButton", tooltip="Extract batch files without LLM calls and classify translatable text vs. engine noise"
        )
        self.btn_run.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_exclude = action_button(
            top_bar, "🚫 Exclude Selected Path", self.exclude_selected_path,
            tooltip="Append the selected row's JSON path regex to format_options.uabea_json_path_exclude in project.yaml"
        )
        self.btn_exclude.pack(side=tk.LEFT, padx=(0, 10))

        self.pbar = progress_bar(top_bar, mode="indeterminate", length=140)

        self.lbl_status = tk.Label(top_bar, text="", font=FONT_BODY, bg=BG_SURFACE, fg=ACCENT_MOSS)
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Summary Metrics Frame
        self.summary_frame = section_frame(main_frame, "Audit Summary", padding=10)
        self.summary_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_metrics = tk.Label(
            self.summary_frame,
            text="Select a project and click 'Run Extraction Audit' to inspect translatable text vs. engine noise.",
            font=FONT_BODY,
            bg=BG_SURFACE,
            fg=FG_TEXT,
            justify=tk.LEFT
        )
        self.lbl_metrics.pack(anchor="w")

        # Table Filter Bar
        filter_bar = ttk.Frame(main_frame, style="TFrame")
        filter_bar.pack(fill=tk.X, pady=(0, 5))

        filter_tooltips = (
            "Filter rows by classification action:\n"
            "• ALL: Show all extracted strings\n"
            "• kept: Translatable strings that would be sent to the LLM\n"
            "• noise:*: Strings dropped by the built-in conservative heuristic (GUIDs, types, colors)\n"
            "• excluded_by_config: Strings dropped by project.yaml uabea_json_path_exclude patterns"
        )
        r_f_combo, self.combo_filter = labeled_combo(
            filter_bar, "Filter Action:", tk.StringVar(value="ALL"),
            values=["ALL", "kept", "noise:*", "excluded_by_config"],
            width=18, label_width=12, tooltip=filter_tooltips
        )
        self.var_filter_action = self.combo_filter.cget("textvariable") or tk.StringVar(value="ALL")
        self.combo_filter.configure(textvariable=self.var_filter_action)
        r_f_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        self.var_search = tk.StringVar()
        r_search, entry_search = labeled_entry(
            filter_bar, "Search Path/Text:", self.var_search, width=28, label_width=15,
            tooltip="Live text search filtering by JSON path, asset name, or string content"
        )
        r_search.pack(side=tk.LEFT, padx=(0, 8))
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
        create_tooltip(self.tree, "Click a row to select it, then click 'Exclude Selected Path' to add it to exclusion rules")

    def refresh_projects(self):
        self.projects_dir = get_default_projects_dir()
        projs = []
        if self.projects_dir.exists():
            for p in sorted(self.projects_dir.iterdir()):
                if p.is_dir() and (p / "project.yaml").exists():
                    projs.append(p.name)

        self.combo_project["values"] = projs
        target = self.shared_project_var.get() if self.shared_project_var else ""
        if target and target in projs:
            self.var_selected_project.set(target)
            self.current_project_dir = self.projects_dir / target
        elif projs:
            self.var_selected_project.set(projs[0])
            self.current_project_dir = self.projects_dir / projs[0]
        else:
            self.var_selected_project.set("")
            self.current_project_dir = None

    def select_project(self, name: str):
        projs = self.combo_project["values"]
        if name in projs:
            self.var_selected_project.set(name)
            self.current_project_dir = self.projects_dir / name

    def _on_project_changed(self, event=None):
        name = self.var_selected_project.get()
        if name:
            self.current_project_dir = self.projects_dir / name
            if self.shared_project_var and self.shared_project_var.get() != name:
                self.shared_project_var.set(name)
            if self.on_project_changed_callback:
                self.on_project_changed_callback(name)

    def _start_audit(self):
        if not self.current_project_dir or not (self.current_project_dir / "project.yaml").exists():
            messagebox.showwarning("No Project", "Please select a valid project first.", parent=self.root)
            return

        if self.is_auditing:
            return

        self.is_auditing = True
        self.btn_run.config(state="disabled")
        self.pbar.pack(side=tk.LEFT, padx=5)
        self.pbar.start(10)
        self.lbl_status.config(text="Scanning batch files...", fg=ACCENT_INK)

        def worker():
            records = []
            files_scanned = 0
            files_failed = []
            msg = ""

            try:
                config = load_project(self.current_project_dir)
                adapter = get_adapter(config.format, config.format_options)

                import inspect
                if "audit_sink" not in inspect.signature(adapter.extract).parameters:
                    msg = f"Format adapter '{config.format}' does not support typetree audit sink (only uabea_json Case 2/3 currently uses this)."
                else:
                    for path in config.batch_files:
                        sink: list[tuple[str, str, str]] = []
                        try:
                            adapter.extract(path, audit_sink=sink)
                            files_scanned += 1
                        except Exception as e:
                            files_failed.append(f"{path.name}: {e}")
                            continue

                        for json_path, value, action in sink:
                            records.append({
                                "file": path.stem,
                                "path": json_path,
                                "action": action,
                                "value": value
                            })

                self.root.after(0, self._on_audit_complete, records, files_scanned, files_failed, msg, None)
            except Exception as e:
                self.root.after(0, self._on_audit_complete, [], 0, [], "", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_audit_complete(self, records: list, files_scanned: int, files_failed: list, special_msg: str, error: Optional[str]):
        self.is_auditing = False
        self.pbar.stop()
        self.pbar.pack_forget()
        self.btn_run.config(state="normal")
        self.lbl_status.config(text="")

        if error:
            messagebox.showerror("Audit Error", f"Audit failed: {error}", parent=self.root)
            return

        self.audit_records = records

        if special_msg:
            self.lbl_metrics.config(text=special_msg, fg=ACCENT_INK)
            self._render_records([])
            return

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
        action_filter = self.var_filter_action.get() if hasattr(self.var_filter_action, "get") else "ALL"
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
        for r in to_show[:2000]:
            preview_val = r["value"].replace("\n", "\\n")
            if len(preview_val) > 80:
                preview_val = preview_val[:77] + "..."
            self.tree.insert("", tk.END, values=(r["file"], r["path"], r["action"], preview_val))

    def exclude_selected_path(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Row", "Please select a row in the table to exclude its path.", parent=self.root)
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

            pattern = f"^{json_path}$"
            if pattern not in excludes and json_path not in excludes:
                excludes.append(pattern)
                cfg_file.write_text(yaml.dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
                self.lbl_status.config(text=f"🚫 Excluded pattern '{pattern}' in project.yaml", fg=ACCENT_INK)
                messagebox.showinfo("Path Excluded", f"Added '{pattern}' to format_options.uabea_json_path_exclude in project.yaml.", parent=self.root)
                self._start_audit()
            else:
                messagebox.showinfo("Already Excluded", f"Pattern for '{json_path}' is already in excludes list.", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update project.yaml: {e}", parent=self.root)
