"""
Run Tab — Execute LocPipe Plan (dry token estimate) and Run (Antigravity CLI translation).
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from locpipe.config import load_project
from locpipe.pipeline import plan
from gamestringer.desktop_gui.tabs.projects_tab import get_default_projects_dir
from gamestringer.desktop_gui.theme import (
    BG_DARK, BG_CARD, BG_ENTRY, FG_TEXT, FG_MUTED,
    ACCENT_CYAN, ACCENT_EMERALD, ACCENT_MAGENTA,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO
)


class RunTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, root: tk.Tk):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.projects_dir = get_default_projects_dir()
        self.current_project_dir: Optional[Path] = None
        self.active_process: Optional[subprocess.Popen] = None
        self.is_running = False

        self._build_ui()
        self.refresh_projects()

    def _build_ui(self):
        main_frame = ttk.Frame(self, style="TFrame", padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top Control Bar
        top_bar = ttk.Frame(main_frame, style="Card.TFrame", padding=10)
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

        ttk.Label(top_bar, text="Limit Batches:", font=FONT_BODY, background=BG_CARD, foreground=FG_TEXT).pack(side=tk.LEFT, padx=(5, 5))
        self.var_limit = tk.StringVar(value="")
        ttk.Entry(top_bar, textvariable=self.var_limit, width=6).pack(side=tk.LEFT, padx=(0, 15))

        self.btn_plan = ttk.Button(top_bar, text="📋 Run Plan (Dry Estimate)", command=self._run_plan)
        self.btn_plan.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_run = ttk.Button(top_bar, text="🚀 Run Translation (Antigravity CLI)", style="Primary.TButton", command=self._start_translation)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = ttk.Button(top_bar, text="⏹ Stop", style="Stop.TButton", state="disabled", command=self._stop_execution)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        # Stats Card
        self.stats_frame = ttk.Labelframe(main_frame, text=" Execution Stats ", style="TLabelframe", padding=10)
        self.stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_stats = tk.Label(
            self.stats_frame,
            text="Ready. Select a project and run Plan to estimate tokens or Run to start translation.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=FG_TEXT,
            justify=tk.LEFT
        )
        self.lbl_stats.pack(anchor="w")

        # Log Output Box
        log_frame = ttk.Labelframe(main_frame, text=" Live Output & Logging Console ", style="TLabelframe", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_log = tk.Text(log_frame, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_MONO, bd=1, wrap=tk.CHAR)
        scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)

        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Color tags for console
        self.txt_log.tag_config("cyan", foreground=ACCENT_CYAN)
        self.txt_log.tag_config("green", foreground=ACCENT_EMERALD)
        self.txt_log.tag_config("red", foreground=ACCENT_MAGENTA)
        self.txt_log.tag_config("yellow", foreground="#ffea00")
        self.txt_log.tag_config("muted", foreground=FG_MUTED)

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

    def _log(self, text: str, tag: str = "normal"):
        self.txt_log.insert(tk.END, text, tag)
        self.txt_log.see(tk.END)

    def _run_plan(self):
        if not self.current_project_dir:
            messagebox.showwarning("No Project", "Please select a project first.")
            return

        try:
            config = load_project(self.current_project_dir)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project: {e}")
            return

        limit_val = int(self.var_limit.get().strip()) if self.var_limit.get().strip().isdigit() else None

        self._log(f"\n=== PRE-FLIGHT PLAN: {config.project} ===\n", "cyan")
        self._log(f"Provider: {config.provider.name} ({config.provider.model})\n", "muted")

        try:
            res = plan(config, limit_batches=limit_val)
            self._log(f"Raw translatable entries:  {res.raw_entries_count}\n")
            self._log(f"Unique strings:            {res.unique_entries_count} ({res.dedupe_ratio:.1f}% deduplication)\n")
            self._log(f"Total Batches:             {res.batch_count}\n")
            self._log(f"Estimated Input Tokens:    ~{res.estimated_input_tokens:,}\n")
            self._log(f"Estimated Output Tokens:   ~{res.estimated_output_tokens:,}\n", "green")

            stat_text = (
                f"Project: {config.project} | Batches: {res.batch_count} | Unique Entries: {res.unique_entries_count:,}\n"
                f"Estimated Tokens: ~{res.estimated_input_tokens:,} in / ~{res.estimated_output_tokens:,} out (0 API cost for plan)"
            )
            self.lbl_stats.config(text=stat_text, fg=ACCENT_CYAN)

        except Exception as e:
            self._log(f"[ERROR] Plan failed: {e}\n", "red")

    def _start_translation(self):
        if not self.current_project_dir:
            messagebox.showwarning("No Project", "Please select a project first.")
            return

        if self.is_running:
            return

        self.is_running = True
        self.btn_run.config(state="disabled")
        self.btn_plan.config(state="disabled")
        self.btn_stop.config(state="normal")

        limit_val = self.var_limit.get().strip()

        # Build locpipe run command
        cmd = [
            sys.executable,
            "-m", "locpipe.cli",
            "run",
            "--project", str(self.current_project_dir)
        ]
        if limit_val.isdigit():
            cmd.extend(["--limit", limit_val])

        self._log(f"\n>>> Starting pipeline: {' '.join(cmd)}\n", "cyan")
        self.lbl_stats.config(text="Translation in progress with Antigravity CLI...", fg=ACCENT_EMERALD)

        def worker():
            env = os.environ.copy()
            # Ensure locpipe package is on PYTHONPATH
            locpipe_src = str(Path(__file__).resolve().parent.parent.parent.parent / "locpipe" / "src")
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = f"{locpipe_src}{os.pathsep}{env['PYTHONPATH']}"
            else:
                env["PYTHONPATH"] = locpipe_src

            try:
                self.active_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env
                )

                for line in iter(self.active_process.stdout.readline, ''):
                    if not line:
                        break
                    self.root.after(0, self._handle_log_line, line)

                self.active_process.wait()
                exit_code = self.active_process.returncode

                self.root.after(0, self._on_finished, exit_code)

            except Exception as e:
                self.root.after(0, self._log, f"[ERROR] Subprocess error: {e}\n", "red")
                self.root.after(0, self._on_finished, 1)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_log_line(self, line: str):
        tag = "normal"
        if "[ERROR]" in line or "Error" in line or "FAILED" in line:
            tag = "red"
        elif "[WARNING]" in line or "Warning" in line:
            tag = "yellow"
        elif "[SUCCESS]" in line or "Phase " in line or "SUCCESS" in line:
            tag = "green"
        elif "===" in line or "---" in line:
            tag = "cyan"
        self._log(line, tag)

    def _stop_execution(self):
        if self.active_process and self.active_process.poll() is None:
            self._log("\n⏹ Terminating process...\n", "yellow")
            try:
                self.active_process.terminate()
            except Exception:
                pass
        self._on_finished(1)

    def _on_finished(self, exit_code: int):
        self.is_running = False
        self.active_process = None
        self.btn_run.config(state="normal")
        self.btn_plan.config(state="normal")
        self.btn_stop.config(state="disabled")

        if exit_code == 0:
            self._log("\n✅ Pipeline completed successfully!\n", "green")
            self.lbl_stats.config(text="Pipeline execution completed successfully.", fg=ACCENT_EMERALD)
        else:
            self._log(f"\n❌ Pipeline exited with code {exit_code}\n", "red")
            self.lbl_stats.config(text=f"Pipeline finished with exit code {exit_code}.", fg=ACCENT_MAGENTA)
