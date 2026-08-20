"""
Projects Tab — View, create, and configure LocPipe translation projects.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Any, Dict, List, Optional
import yaml

from gamestringer.desktop_gui.theme import (
    BG_DARK, BG_CARD, BG_ENTRY, FG_TEXT, FG_MUTED,
    ACCENT_CYAN, ACCENT_EMERALD, ACCENT_MAGENTA,
    FONT_HEADING, FONT_BODY, FONT_MONO
)


def get_default_projects_dir() -> Path:
    # Try finding locpipe/projects under repo root
    cwd = Path.cwd()
    candidates = [
        cwd / "locpipe" / "projects",
        cwd / "projects",
        Path(__file__).resolve().parent.parent.parent.parent / "locpipe" / "projects",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Default to locpipe/projects in current working directory
    target = cwd / "locpipe" / "projects"
    target.mkdir(parents=True, exist_ok=True)
    return target


class ProjectsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, root: tk.Tk):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.projects_dir = get_default_projects_dir()
        self.current_project_path: Optional[Path] = None
        self.raw_config: Dict[str, Any] = {}

        self._build_ui()
        self.refresh_project_list()

    def _build_ui(self):
        # Main layout: Left sidebar (Project list + New button), Right pane (Config Form)
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Frame: Project Explorer
        left_frame = ttk.Labelframe(paned, text=" 📁 Projects ", style="TLabelframe", padding=10)
        paned.add(left_frame, weight=1)

        self.project_listbox = tk.Listbox(
            left_frame,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectbackground=ACCENT_CYAN,
            selectforeground="#000000",
            font=FONT_BODY,
            bd=1,
            highlightthickness=0,
        )
        self.project_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.project_listbox.bind("<<ListboxSelect>>", self._on_project_selected)

        btn_box = ttk.Frame(left_frame, style="TFrame")
        btn_box.pack(fill=tk.X)

        btn_new = ttk.Button(btn_box, text="+ New Project", command=self._create_new_project)
        btn_new.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        btn_refresh = ttk.Button(btn_box, text="🔄 Refresh", command=self.refresh_project_list)
        btn_refresh.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        # Right Frame: Config Editor Form
        right_frame = ttk.Labelframe(paned, text=" ⚙️ Project Configuration (project.yaml) ", style="TLabelframe", padding=15)
        paned.add(right_frame, weight=3)

        # Canvas + Scrollbar for form fields
        canvas = tk.Canvas(right_frame, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_form = ttk.Frame(canvas, style="Card.TFrame")

        self.scrollable_form.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        form = self.scrollable_form

        # Row 1: Project Name & Format
        r1 = ttk.Frame(form, style="Card.TFrame")
        r1.pack(fill=tk.X, pady=4)

        ttk.Label(r1, text="Project Name:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=15).pack(side=tk.LEFT)
        self.var_name = tk.StringVar()
        self.entry_name = ttk.Entry(r1, textvariable=self.var_name, state="readonly", width=25)
        self.entry_name.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(r1, text="Format Adapter:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=15).pack(side=tk.LEFT)
        self.var_format = tk.StringVar(value="uabea_json")
        self.combo_format = ttk.Combobox(
            r1,
            textvariable=self.var_format,
            values=["uabea_json", "unity", "po_gettext", "ue4_5_po", "generic_kv", "xliff", "weblate_xliff"],
            state="readonly",
            width=20,
        )
        self.combo_format.pack(side=tk.LEFT)

        # Row 2: Languages & Batch Glob
        r2 = ttk.Frame(form, style="Card.TFrame")
        r2.pack(fill=tk.X, pady=4)

        ttk.Label(r2, text="Source Lang:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=15).pack(side=tk.LEFT)
        self.var_source_lang = tk.StringVar(value="en")
        ttk.Entry(r2, textvariable=self.var_source_lang, width=8).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(r2, text="Target Lang:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=12).pack(side=tk.LEFT)
        self.var_target_lang = tk.StringVar(value="hu")
        ttk.Entry(r2, textvariable=self.var_target_lang, width=8).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(r2, text="Batch Glob:", font=FONT_HEADING, background=BG_CARD, foreground=ACCENT_CYAN, width=12).pack(side=tk.LEFT)
        self.var_batch_glob = tk.StringVar(value="batches/*.json")
        ttk.Entry(r2, textvariable=self.var_batch_glob, width=25).pack(side=tk.LEFT)

        # Section: Provider Lock Notice
        r_prov = ttk.Frame(form, style="Card.TFrame")
        r_prov.pack(fill=tk.X, pady=6)
        lbl_prov = tk.Label(
            r_prov,
            text="🔒 LLM Provider: antigravity_cli (model: gemini-3.7-flash) — Fixed across all projects",
            font=FONT_MONO,
            bg=BG_ENTRY,
            fg=ACCENT_EMERALD,
            padx=8,
            pady=4,
            relief="solid",
            bd=1
        )
        lbl_prov.pack(fill=tk.X)

        # Section: Format Options
        sec_opt = ttk.Labelframe(form, text=" Format Options ", style="TLabelframe", padding=10)
        sec_opt.pack(fill=tk.X, pady=8)

        # Noise Filter Toggle
        r_noise = ttk.Frame(sec_opt, style="Card.TFrame")
        r_noise.pack(fill=tk.X, pady=2)
        self.var_noise_filter = tk.BooleanVar(value=True)
        ttk.Checkbutton(r_noise, text="Enable built-in engine noise filtering (Case 2/3 typetree walk)", variable=self.var_noise_filter).pack(side=tk.LEFT)

        # Character replacements
        r_cr = ttk.Frame(sec_opt, style="Card.TFrame")
        r_cr.pack(fill=tk.X, pady=4)
        ttk.Label(r_cr, text="Character Replacements (JSON map, e.g. {\"ő\": \"ô\", \"ű\": \"û\"}):", font=FONT_BODY, background=BG_CARD, foreground=FG_TEXT).pack(anchor="w")
        self.var_char_replacements = tk.StringVar(value="{}")
        self.entry_char_replacements = ttk.Entry(r_cr, textvariable=self.var_char_replacements, font=FONT_MONO)
        self.entry_char_replacements.pack(fill=tk.X, pady=2)

        # UABEA JSON Path Exclude
        r_ex = ttk.Frame(sec_opt, style="Card.TFrame")
        r_ex.pack(fill=tk.X, pady=4)
        ttk.Label(r_ex, text="UABEA JSON Path Excludes (one regex pattern per line):", font=FONT_BODY, background=BG_CARD, foreground=FG_TEXT).pack(anchor="w")
        self.txt_path_exclude = tk.Text(r_ex, height=4, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=ACCENT_CYAN, font=FONT_MONO, bd=1)
        self.txt_path_exclude.pack(fill=tk.X, pady=2)

        # Section: Categories
        sec_cat = ttk.Labelframe(form, text=" Categories & Batch Rules ", style="TLabelframe", padding=10)
        sec_cat.pack(fill=tk.BOTH, expand=True, pady=8)

        cat_btn_box = ttk.Frame(sec_cat, style="Card.TFrame")
        cat_btn_box.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(cat_btn_box, text="+ Add Category", command=self._add_category).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(cat_btn_box, text="🗑 Remove Selected", command=self._remove_category).pack(side=tk.LEFT, padx=4)

        cat_cols = ("Name", "Batch Size", "Default", "Speaker Check", "Voice Bible", "Max Expansion")
        self.tree_categories = ttk.Treeview(sec_cat, columns=cat_cols, show="headings", height=5)
        for col in cat_cols:
            self.tree_categories.heading(col, text=col)
            self.tree_categories.column(col, width=90, anchor="center")
        self.tree_categories.column("Name", width=120, anchor="w")
        self.tree_categories.pack(fill=tk.BOTH, expand=True)

        # Action Buttons
        act_box = ttk.Frame(form, style="Card.TFrame")
        act_box.pack(fill=tk.X, pady=12)

        btn_save = ttk.Button(act_box, text="💾 Save project.yaml", style="Primary.TButton", command=self.save_project)
        btn_save.pack(side=tk.LEFT, padx=(0, 10))

        btn_reload = ttk.Button(act_box, text="↩ Reload from Disk", command=self.reload_current_project)
        btn_reload.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(act_box, text="", font=FONT_BODY, bg=BG_CARD, fg=ACCENT_EMERALD)
        self.lbl_status.pack(side=tk.LEFT, padx=15)

    def refresh_project_list(self):
        self.project_listbox.delete(0, tk.END)
        self.projects_dir = get_default_projects_dir()
        if not self.projects_dir.exists():
            return

        projects = []
        for p in sorted(self.projects_dir.iterdir()):
            if p.is_dir() and (p / "project.yaml").exists():
                projects.append(p.name)

        for proj in projects:
            self.project_listbox.insert(tk.END, proj)

        if projects:
            self.project_listbox.selection_set(0)
            self._load_project_by_name(projects[0])

    def _on_project_selected(self, event=None):
        sel = self.project_listbox.curselection()
        if not sel:
            return
        name = self.project_listbox.get(sel[0])
        self._load_project_by_name(name)

    def _load_project_by_name(self, name: str):
        proj_dir = self.projects_dir / name
        cfg_path = proj_dir / "project.yaml"
        if not cfg_path.exists():
            return

        self.current_project_path = proj_dir
        try:
            self.raw_config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse project.yaml: {e}")
            return

        self.var_name.set(self.raw_config.get("project", name))
        self.var_source_lang.set(self.raw_config.get("source_lang", "en"))
        self.var_target_lang.set(self.raw_config.get("target_lang", "hu"))
        self.var_format.set(self.raw_config.get("format", "uabea_json"))
        self.var_batch_glob.set((self.raw_config.get("batches") or {}).get("glob", "batches/*.json"))

        format_opts = self.raw_config.get("format_options", {})
        self.var_noise_filter.set(format_opts.get("noise_filter", True))

        char_rep = format_opts.get("character_replacements", {})
        self.var_char_replacements.set(json.dumps(char_rep, ensure_ascii=False) if char_rep else "{}")

        excludes = format_opts.get("uabea_json_path_exclude", [])
        self.txt_path_exclude.delete("1.0", tk.END)
        if isinstance(excludes, list):
            self.txt_path_exclude.insert(tk.END, "\n".join(str(x) for x in excludes))
        elif isinstance(excludes, str):
            self.txt_path_exclude.insert(tk.END, excludes)

        # Populate categories
        for row in self.tree_categories.get_children():
            self.tree_categories.delete(row)

        cats = self.raw_config.get("categories", [
            {"name": "dialogue", "match_speaker_present": True, "needs_character_voice": True, "batch_size": 200},
            {"name": "ui", "default": True, "batch_size": 350, "max_expansion_ratio": 1.3}
        ])

        for c in cats:
            self.tree_categories.insert("", tk.END, values=(
                c.get("name", "category"),
                c.get("batch_size", 350),
                "Yes" if c.get("default") else "No",
                "Yes" if c.get("match_speaker_present") else "No",
                "Yes" if c.get("needs_character_voice") else "No",
                c.get("max_expansion_ratio", "default")
            ))

        self.lbl_status.config(text=f"Loaded {name}", fg=ACCENT_EMERALD)

    def reload_current_project(self):
        if self.current_project_path:
            self._load_project_by_name(self.current_project_path.name)

    def _create_new_project(self):
        name = simpledialog.askstring("New Project", "Enter project name (e.g. MyGame):", parent=self.root)
        if not name:
            return
        name = name.strip()
        proj_dir = self.projects_dir / name
        if proj_dir.exists():
            messagebox.showwarning("Exists", f"Project '{name}' already exists.")
            return

        (proj_dir / "batches").mkdir(parents=True, exist_ok=True)
        (proj_dir / "resources").mkdir(parents=True, exist_ok=True)

        template_yaml = {
            "project": name,
            "source_lang": "en",
            "target_lang": "hu",
            "format": "uabea_json",
            "batches": {"glob": "batches/*.json"},
            "resources": {
                "glossary": "resources/glossary.md",
                "lang_style": "resources/lang-style.md",
                "character_voices": "resources/character-voices.md",
                "anti_fabrication_checklist": "resources/anti-fabrication-checklist.md",
            },
            "categories": [
                {"name": "dialogue", "match_speaker_present": True, "needs_character_voice": True, "batch_size": 200, "max_expansion_ratio": 1.8},
                {"name": "ui", "default": True, "needs_character_voice": False, "batch_size": 350, "max_expansion_ratio": 1.3}
            ],
            "provider": {
                "name": "antigravity_cli",
                "model": "gemini-3.7-flash",
                "effort": "low",
                "review_model": "gemini-3.7-flash",
                "review_effort": "high",
                "mode": "sync",
                "max_concurrency": 5,
            },
            "format_options": {
                "noise_filter": True,
                "character_replacements": {},
                "uabea_json_path_exclude": []
            },
            "tm": {"db_path": "tm/translation_memory.sqlite3"},
            "confidence": {
                "review_threshold": 0.75,
                "max_expansion_ratio": 1.6,
                "tier1_repair_attempts": 2
            }
        }

        (proj_dir / "project.yaml").write_text(yaml.dump(template_yaml, sort_keys=False, allow_unicode=True), encoding="utf-8")

        for fname, header in [
            ("glossary.md", "# Glossary\n\n| Source term | Target translation | Category | Confidence | Source/justification |\n|---|---|---|---|---|\n"),
            ("lang-style.md", "# Language style guide\n"),
            ("character-voices.md", "# Character voice bible\n\n| Character | Register | Traits | Avoid |\n|---|---|---|---|\n"),
            ("anti-fabrication-checklist.md", "# Anti-fabrication checklist\n"),
        ]:
            (proj_dir / "resources" / fname).write_text(header, encoding="utf-8")

        self.refresh_project_list()
        items = self.project_listbox.get(0, tk.END)
        if name in items:
            idx = items.index(name)
            self.project_listbox.selection_clear(0, tk.END)
            self.project_listbox.selection_set(idx)
            self._load_project_by_name(name)

    def _add_category(self):
        cat_name = simpledialog.askstring("Add Category", "Category Name (e.g. lore, items):", parent=self.root)
        if not cat_name:
            return
        self.tree_categories.insert("", tk.END, values=(cat_name.strip(), 300, "No", "No", "No", "default"))

    def _remove_category(self):
        sel = self.tree_categories.selection()
        if not sel:
            return
        for s in sel:
            self.tree_categories.delete(s)

    def save_project(self):
        if not self.current_project_path:
            messagebox.showwarning("No Project", "No active project selected.")
            return

        cfg = dict(self.raw_config) if self.raw_config else {}
        cfg["project"] = self.var_name.get()
        cfg["source_lang"] = self.var_source_lang.get()
        cfg["target_lang"] = self.var_target_lang.get()
        cfg["format"] = self.var_format.get()

        if "batches" not in cfg:
            cfg["batches"] = {}
        cfg["batches"]["glob"] = self.var_batch_glob.get()

        # Always lock provider to antigravity_cli
        if "provider" not in cfg:
            cfg["provider"] = {}
        cfg["provider"]["name"] = "antigravity_cli"
        if "model" not in cfg["provider"]:
            cfg["provider"]["model"] = "gemini-3.7-flash"

        # Format options
        if "format_options" not in cfg:
            cfg["format_options"] = {}
        cfg["format_options"]["noise_filter"] = self.var_noise_filter.get()

        raw_cr = self.var_char_replacements.get().strip()
        if raw_cr:
            try:
                cfg["format_options"]["character_replacements"] = json.loads(raw_cr)
            except Exception:
                cfg["format_options"]["character_replacements"] = {}

        raw_ex = self.txt_path_exclude.get("1.0", tk.END).strip()
        cfg["format_options"]["uabea_json_path_exclude"] = [line.strip() for line in raw_ex.splitlines() if line.strip()]

        # Reconstruct categories
        categories = []
        for item in self.tree_categories.get_children():
            vals = self.tree_categories.item(item, "values")
            c = {
                "name": str(vals[0]),
                "batch_size": int(vals[1]) if str(vals[1]).isdigit() else 350,
                "default": str(vals[2]).lower() == "yes",
            }
            if str(vals[3]).lower() == "yes":
                c["match_speaker_present"] = True
            if str(vals[4]).lower() == "yes":
                c["needs_character_voice"] = True
            if str(vals[5]) != "default" and str(vals[5]).replace(".", "").isdigit():
                c["max_expansion_ratio"] = float(vals[5])
            categories.append(c)

        if categories:
            cfg["categories"] = categories

        cfg_path = self.current_project_path / "project.yaml"
        try:
            cfg_path.write_text(yaml.dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
            self.lbl_status.config(text="✅ Saved successfully!", fg=ACCENT_EMERALD)
            self.root.after(3000, lambda: self.lbl_status.config(text=""))
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save project.yaml: {e}")
