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
from typing import Any, Callable, Optional

from locpipe.config import load_project
from locpipe.pipeline import plan
from gamestringer.desktop_gui.tabs.projects_tab import get_default_projects_dir
from gamestringer.desktop_gui.theme import (
    BG_DARK, BG_CARD, BG_ENTRY, FG_TEXT, FG_MUTED,
    ACCENT_CYAN, ACCENT_EMERALD, ACCENT_MAGENTA,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_MONO
)
from gamestringer.desktop_gui.tooltip import create_tooltip
from gamestringer.desktop_gui.widgets import (
    section_frame, labeled_entry, labeled_combo, action_button, progress_bar
)


class RunTab(ttk.Frame):
    def __init__(
        self,
        parent: ttk.Notebook,
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
        self.active_process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.has_run_plan_in_session = False
        self.start_time: Optional[float] = None
        self.timer_id: Optional[str] = None

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
            width=22,
        )
        self.combo_project.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_project.bind("<<ComboboxSelected>>", self._on_project_changed)
        create_tooltip(self.combo_project, "Select target project to plan or translate")

        self.var_limit = tk.StringVar(value="")
        r_lim, _ = labeled_entry(
            top_bar, "Batch Limit:", self.var_limit, width=6, label_width=12,
            tooltip="For testing only: translates only the first N batches (e.g. 1 or 2). Leave blank to translate full project."
        )
        r_lim.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_plan = action_button(
            top_bar, "📋 Run Plan (Dry Estimate)", self._run_plan,
            tooltip="Dry run: calculates exact batch counts, deduplication, and input/output token estimates with ZERO API calls"
        )
        self.btn_plan.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_run = action_button(
            top_bar, "🚀 Run Translation (Antigravity CLI)", self._start_translation,
            style="Primary.TButton",
            tooltip="Live execution: translates batch files using Antigravity CLI (Gemini 3.7 Flash) and writes output"
        )
        self.btn_run.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = action_button(
            top_bar, "⏹ Stop", self._stop_execution,
            style="Stop.TButton",
            tooltip="Safely abort the running translation subprocess"
        )
        self.btn_stop.config(state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        self.pbar = progress_bar(top_bar, mode="indeterminate", length=130)

        # Stats Card
        self.stats_frame = section_frame(main_frame, "Execution Stats & Progress", padding=10)
        self.stats_frame.pack(fill=tk.X, pady=(0, 10))

        stat_row = ttk.Frame(self.stats_frame, style="Card.TFrame")
        stat_row.pack(fill=tk.X)

        self.lbl_stats = tk.Label(
            stat_row,
            text="Ready. Select a project and run Plan to estimate tokens, or Run to start translation.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=FG_TEXT,
            justify=tk.LEFT
        )
        self.lbl_stats.pack(side=tk.LEFT, anchor="w", expand=True)

        self.lbl_timer = tk.Label(
            stat_row,
            text="",
            font=FONT_MONO,
            bg=BG_CARD,
            fg=ACCENT_CYAN
        )
        self.lbl_timer.pack(side=tk.RIGHT, padx=(10, 0))

        self.btn_open_folder = action_button(
            self.stats_frame, "📂 Open Project Folder", self._open_project_folder,
            tooltip="Open the project's root folder in the system file manager"
        )

        # Log Output Box
        log_frame = section_frame(main_frame, "Live Output & Logging Console", padding=8)
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

    def _log(self, text: str, tag: str = "normal"):
        self.txt_log.insert(tk.END, text, tag)
        self.txt_log.see(tk.END)

    def _open_project_folder(self):
        if not self.current_project_dir or not self.current_project_dir.exists():
            return
        target = str(self.current_project_dir.resolve())
        try:
            if sys.platform == "win32":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}", parent=self.root)

    def _update_timer(self):
        if self.is_running and self.start_time:
            elapsed = int(time.time() - self.start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.lbl_timer.config(text=f"⏱ Elapsed: {mins:02d}:{secs:02d}")
            self.timer_id = self.root.after(1000, self._update_timer)

    def _run_plan(self):
        if not self.current_project_dir:
            messagebox.showwarning("No Project", "Please select a project first.", parent=self.root)
            return

        try:
            config = load_project(self.current_project_dir)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project: {e}", parent=self.root)
            return

        limit_val = int(self.var_limit.get().strip()) if self.var_limit.get().strip().isdigit() else None

        self.btn_plan.config(state="disabled")
        self.pbar.pack(side=tk.LEFT, padx=5)
        self.pbar.start(10)
        self.lbl_stats.config(text="Calculating plan and token estimates...", fg=ACCENT_CYAN)

        def worker():
            try:
                res = plan(config, limit_batches=limit_val)
                self.root.after(0, self._on_plan_complete, config, res, None)
            except Exception as e:
                self.root.after(0, self._on_plan_complete, config, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_plan_complete(self, config, res, error: Optional[str]):
        self.btn_plan.config(state="normal")
        self.pbar.stop()
        self.pbar.pack_forget()

        if error:
            self._log(f"\n[ERROR] Plan failed: {error}\n", "red")
            self.lbl_stats.config(text=f"Plan failed: {error}", fg=ACCENT_MAGENTA)
            return

        self.has_run_plan_in_session = True
        self._log(f"\n=== PRE-FLIGHT PLAN: {config.project} ===\n", "cyan")
        self._log(f"Provider: {config.provider.name} ({config.provider.model})\n", "muted")
        self._log(f"Raw translatable entries:  {res.raw_entries_count:,}\n")
        self._log(f"Unique strings:            {res.unique_entries_count:,} ({res.dedupe_ratio:.1f}% deduplication)\n")
        self._log(f"Total Batches:             {res.batch_count}\n")
        self._log(f"Estimated Input Tokens:    ~{res.estimated_input_tokens:,}\n")
        self._log(f"Estimated Output Tokens:   ~{res.estimated_output_tokens:,}\n", "green")

        stat_text = (
            f"Project: {config.project} | Batches: {res.batch_count} | Unique Entries: {res.unique_entries_count:,}\n"
            f"Estimated Tokens: ~{res.estimated_input_tokens:,} in / ~{res.estimated_output_tokens:,} out (0 API cost for plan)"
        )
        self.lbl_stats.config(text=stat_text, fg=ACCENT_CYAN)

    def _start_translation(self):
        if not self.current_project_dir:
            messagebox.showwarning("No Project", "Please select a project first.", parent=self.root)
            return

        if self.is_running:
            return

        proj_name = self.current_project_dir.name
        limit_val = self.var_limit.get().strip()
        limit_desc = f"{limit_val} batch(es) only" if limit_val.isdigit() else "NO LIMIT (Full Project)"

        # Data safety confirmation
        warning_msg = (
            f"Launch Live Translation Run?\n\n"
            f"• Project: {proj_name}\n"
            f"• Batch Scope: {limit_desc}\n"
            f"• Provider: Antigravity CLI (Gemini 3.7 Flash)\n\n"
        )
        if not self.has_run_plan_in_session:
            warning_msg += "⚠️ Note: You have not run 'Plan' yet in this session. Running Plan first is recommended to verify token estimates.\n\n"

        warning_msg += "Do you want to proceed with translation?"

        confirm = messagebox.askyesno(
            "Confirm Translation Run",
            warning_msg,
            icon="question",
            parent=self.root
        )
        if not confirm:
            return

        self.is_running = True
        self.btn_run.config(state="disabled")
        self.btn_plan.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_open_folder.pack_forget()

        self.pbar.pack(side=tk.LEFT, padx=5)
        self.pbar.start(10)

        self.start_time = time.time()
        self._update_timer()

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
        self.lbl_stats.config(text=f"Translation in progress for '{proj_name}' via Antigravity CLI...", fg=ACCENT_EMERALD)

        def worker():
            env = os.environ.copy()
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
                self.root.after(0, self._log, f"[ERROR] Subprocess execution error: {e}\n", "red")
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
        self.pbar.stop()
        self.pbar.pack_forget()

        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

        if exit_code == 0:
            self._log("\n✅ Pipeline completed successfully!\n", "green")
            self.lbl_stats.config(text="Pipeline execution completed successfully.", fg=ACCENT_EMERALD)
            self.btn_open_folder.pack(side=tk.LEFT, pady=(8, 0))
        else:
            self._log(f"\n❌ Pipeline exited with code {exit_code}\n", "red")
            self.lbl_stats.config(text=f"Pipeline finished with exit code {exit_code}.", fg=ACCENT_MAGENTA)
