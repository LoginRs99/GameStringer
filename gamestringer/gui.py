"""
GameStringer GUI — Tkinter Graphical Interface Wrapper for GameStringer CLI.

Provides a modern, responsive GUI for extracting and repatching game text without modifying core engine logic.
Supports background process execution, real-time logging, persistent settings, and auto-detection.
"""

import sys
import os
import json
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Dict, Any

# Ensure root directory is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gamestringer.engines.il2cpp_hybrid import find_il2cppdumper_path, IL2CPPDUMPER_URL
from gamestringer.core.batch import auto_detect_engine
from gamestringer.cli import ENGINE_REGISTRY

# Settings persistence path
if sys.platform == "win32":
    SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "GameStringer")
else:
    SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".config", "GameStringer")

SETTINGS_FILE = os.path.join(SETTINGS_DIR, "gui_settings.json")


def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file if available."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data: Dict[str, Any]) -> None:
    """Save settings dict to JSON file."""
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def open_system_path(path: str) -> None:
    """Open a file or folder in the operating system file explorer or default application."""
    if not path or not os.path.exists(path):
        messagebox.showerror("Error", f"Target path does not exist: {path}")
        return

    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as err:
        messagebox.showerror("Error", f"Failed to open path: {err}")


class GameStringerGUI:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GameStringer — Game Text Extractor")
        self.root.geometry("740x640")
        self.root.minsize(700, 580)

        self.msg_queue: queue.Queue = queue.Queue()

        # State Variables
        self.game_folder_var = tk.StringVar()
        self.engine_var = tk.StringVar(value="Auto-detect")
        self.dry_run_var = tk.BooleanVar(value=False)
        self.verbose_var = tk.BooleanVar(value=True)
        self.skip_garbage_var = tk.BooleanVar(value=True)

        self.xliff_path_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()
        self.il2cppdumper_path_var = tk.StringVar()

        self.status_var = tk.StringVar(value="Result: Ready | Strings: 0 | Size: 0 MB")
        self.progress_percent_var = tk.StringVar(value="0%")

        self.last_generated_xliff: Optional[str] = None
        self.last_generated_output_folder: Optional[str] = None

        self._apply_styles()
        self._build_widgets()
        self._load_saved_settings()
        self._check_il2cppdumper_on_startup()

        # Start queue listener
        self.root.after(100, self._poll_queue)

    def _apply_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Header.TLabel", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10, "bold"))

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ─────────────────────────────────────────────────────────────
        # 1. TOP SECTION — Extraction
        # ─────────────────────────────────────────────────────────────
        extract_frame = ttk.LabelFrame(main_frame, text=" Text Extraction ", padding=10)
        extract_frame.pack(fill=tk.X, pady=(0, 8))

        # Game Folder row
        f_row = ttk.Frame(extract_frame)
        f_row.pack(fill=tk.X, pady=2)
        ttk.Label(f_row, text="Game Folder:", width=14).pack(side=tk.LEFT)
        ttk.Entry(f_row, textvariable=self.game_folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(f_row, text="Browse", width=10, command=self._browse_game_folder).pack(side=tk.LEFT)

        # Engine selection row
        e_row = ttk.Frame(extract_frame)
        e_row.pack(fill=tk.X, pady=4)
        ttk.Label(e_row, text="Engine:", width=14).pack(side=tk.LEFT)
        engine_combo = ttk.Combobox(
            e_row,
            textvariable=self.engine_var,
            state="readonly",
            values=["Auto-detect", "unity", "unreal", "renpy", "cri", "il2cpp"],
        )
        engine_combo.pack(side=tk.LEFT, padx=5)

        # Options Checkboxes
        c_row = ttk.Frame(extract_frame)
        c_row.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(c_row, text="Dry-run", variable=self.dry_run_var).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(c_row, text="Verbose", variable=self.verbose_var).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(c_row, text="Skip metadata garbage (IL2CPP)", variable=self.skip_garbage_var).pack(side=tk.LEFT)

        # Extract Button & Progress bar
        self.btn_extract = ttk.Button(extract_frame, text="EXTRACT TO XLIFF", style="Accent.TButton", command=self._start_extraction)
        self.btn_extract.pack(fill=tk.X, pady=(6, 4))

        p_row = ttk.Frame(extract_frame)
        p_row.pack(fill=tk.X, pady=2)
        self.progress_bar = ttk.Progressbar(p_row, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.lbl_progress = ttk.Label(p_row, textvariable=self.progress_percent_var, width=6)
        self.lbl_progress.pack(side=tk.RIGHT)

        # ─────────────────────────────────────────────────────────────
        # 2. MIDDLE SECTION — Log & Results
        # ─────────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(main_frame, text=" Log & Status ", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=9,
            font=("Consolas" if sys.platform == "win32" else "Courier", 9),
            wrap="word",
            state="disabled",
            bg="#1e1e1e" if sys.platform == "win32" else "#2b2b2b",
            fg="#d4d4d4",
            insertbackground="#ffffff",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        res_row = ttk.Frame(log_frame)
        res_row.pack(fill=tk.X)

        self.lbl_result = ttk.Label(res_row, textvariable=self.status_var, style="Status.TLabel", foreground="#2e7d32")
        self.lbl_result.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_open_xliff = ttk.Button(res_row, text="Open XLIFF", state="disabled", command=self._open_xliff_file)
        self.btn_open_xliff.pack(side=tk.LEFT, padx=4)

        self.btn_open_out_folder = ttk.Button(res_row, text="Open Output Folder", state="disabled", command=self._open_output_folder)
        self.btn_open_out_folder.pack(side=tk.LEFT)

        # ─────────────────────────────────────────────────────────────
        # 3. BOTTOM SECTION — Patching
        # ─────────────────────────────────────────────────────────────
        patch_frame = ttk.LabelFrame(main_frame, text=" Repatch Translated Text ", padding=10)
        patch_frame.pack(fill=tk.X, pady=4)

        # XLIFF File row
        x_row = ttk.Frame(patch_frame)
        x_row.pack(fill=tk.X, pady=2)
        ttk.Label(x_row, text="XLIFF File:", width=14).pack(side=tk.LEFT)
        ttk.Entry(x_row, textvariable=self.xliff_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(x_row, text="Browse", width=10, command=self._browse_xliff_file).pack(side=tk.LEFT)

        # Output Folder row
        out_row = ttk.Frame(patch_frame)
        out_row.pack(fill=tk.X, pady=2)
        ttk.Label(out_row, text="Output Folder:", width=14).pack(side=tk.LEFT)
        ttk.Entry(out_row, textvariable=self.output_folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(out_row, text="Browse", width=10, command=self._browse_output_folder).pack(side=tk.LEFT)

        # Patch Button
        self.btn_patch = ttk.Button(patch_frame, text="PATCH BACK TO GAME", style="Accent.TButton", command=self._start_patching)
        self.btn_patch.pack(fill=tk.X, pady=(6, 2))

        # ─────────────────────────────────────────────────────────────
        # 4. IL2CPPDUMPER SETTINGS SECTION
        # ─────────────────────────────────────────────────────────────
        dumper_frame = ttk.LabelFrame(main_frame, text=" IL2CppDumper Settings ", padding=8)
        dumper_frame.pack(fill=tk.X, pady=(4, 0))

        d_row = ttk.Frame(dumper_frame)
        d_row.pack(fill=tk.X)
        ttk.Label(d_row, text="IL2CppDumper:", width=14).pack(side=tk.LEFT)
        ttk.Entry(d_row, textvariable=self.il2cppdumper_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(d_row, text="Browse", width=10, command=self._browse_il2cppdumper_path).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(d_row, text="Auto-detect", command=self._auto_detect_il2cppdumper).pack(side=tk.LEFT)

    # ─────────────────────────────────────────────────────────────
    # BROWSE ACTIONS & DEFAULTS
    # ─────────────────────────────────────────────────────────────

    def _browse_game_folder(self):
        folder = filedialog.askdirectory(title="Select Game Directory")
        if folder:
            self.game_folder_var.set(folder)
            # Update default XLIFF and output folder paths if empty
            if not self.xliff_path_var.get():
                self.xliff_path_var.set(folder.rstrip("/\\") + ".xliff")
            if not self.output_folder_var.get():
                self.output_folder_var.set(folder.rstrip("/\\") + "_patched")
            self._save_current_settings()

    def _browse_xliff_file(self):
        fpath = filedialog.askopenfilename(title="Select Translated XLIFF File", filetypes=[("XLIFF files", "*.xliff"), ("All files", "*.*")])
        if fpath:
            self.xliff_path_var.set(fpath)
            self._save_current_settings()

    def _browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder for Patched Files")
        if folder:
            self.output_folder_var.set(folder)
            self._save_current_settings()

    def _browse_il2cppdumper_path(self):
        fpath = filedialog.askopenfilename(
            title="Select IL2CppDumper Executable",
            filetypes=[("Executables", "*.exe" if sys.platform == "win32" else "*"), ("All files", "*.*")],
        )
        if fpath:
            self.il2cppdumper_path_var.set(fpath)
            self._save_current_settings()

    def _auto_detect_il2cppdumper(self):
        detected = find_il2cppdumper_path()
        if detected:
            self.il2cppdumper_path_var.set(detected)
            self._append_log(f"[SUCCESS] Auto-detected IL2CppDumper at: {detected}\n")
            messagebox.showinfo("IL2CppDumper Found", f"IL2CppDumper executable found:\n{detected}")
        else:
            self.il2cppdumper_path_var.set("")
            self._append_log(f"[WARNING] IL2CppDumper not found. Download from: {IL2CPPDUMPER_URL}\n")
            messagebox.showwarning(
                "IL2CppDumper Not Found",
                f"IL2CppDumper was not found in standard system paths.\n\nDownload release from:\n{IL2CPPDUMPER_URL}",
            )
        self._save_current_settings()

    def _check_il2cppdumper_on_startup(self):
        if not self.il2cppdumper_path_var.get():
            detected = find_il2cppdumper_path()
            if detected:
                self.il2cppdumper_path_var.set(detected)

    # ─────────────────────────────────────────────────────────────
    # WORKER THREAD & SUBPROCESS EXECUTION
    # ─────────────────────────────────────────────────────────────

    def _resolve_engine_name(self, game_folder: str, selected_engine: str) -> str:
        """Resolve engine name. If 'Auto-detect', run engine detector."""
        if selected_engine == "Auto-detect":
            self._append_log(f"[AUTO-DETECT] Detecting game engine for '{game_folder}'...\n")
            detected = auto_detect_engine(game_folder, ENGINE_REGISTRY)
            self._append_log(f"[AUTO-DETECT] Matched engine: '{detected.name}' ({detected.description})\n")
            return detected.name
        return selected_engine

    def _start_extraction(self):
        game_folder = self.game_folder_var.get().strip()
        if not game_folder or not os.path.exists(game_folder):
            messagebox.showwarning("Invalid Input", "Please select a valid game folder first.")
            return

        selected_engine = self.engine_var.get()
        try:
            engine = self._resolve_engine_name(game_folder, selected_engine)
        except Exception as err:
            messagebox.showerror("Engine Detection Failed", f"Could not auto-detect engine:\n{err}")
            return

        out_xliff = self.xliff_path_var.get().strip() or (game_folder.rstrip("/\\") + ".xliff")
        self.xliff_path_var.set(out_xliff)

        # Prepare CLI command
        cmd = [sys.executable, "-m", "gamestringer.cli"]
        if self.verbose_var.get():
            cmd.append("--verbose")

        cmd.extend(["extract", "--engine", engine, "--input", game_folder, "--output", out_xliff])

        if self.dry_run_var.get():
            cmd.append("--dry-run")

        dumper_path = self.il2cppdumper_path_var.get().strip()
        if dumper_path:
            cmd.extend(["--il2cppdumper-path", dumper_path])

        self._save_current_settings()
        self._set_running_state(True, task_type="extract")
        self._append_log(f"\n--- Starting Text Extraction --- [{engine}]\nCommand: {' '.join(cmd)}\n")

        # Launch worker thread
        threading.Thread(target=self._run_subprocess_task, args=(cmd, "extract", out_xliff), daemon=True).start()

    def _start_patching(self):
        xliff_path = self.xliff_path_var.get().strip()
        if not xliff_path or not os.path.exists(xliff_path):
            messagebox.showwarning("Invalid Input", "Please select a valid translated XLIFF file first.")
            return

        game_folder = self.game_folder_var.get().strip()
        if not game_folder or not os.path.exists(game_folder):
            messagebox.showwarning("Invalid Input", "Please select a valid game folder first.")
            return

        output_folder = self.output_folder_var.get().strip() or (game_folder.rstrip("/\\") + "_patched")
        self.output_folder_var.set(output_folder)

        selected_engine = self.engine_var.get()
        try:
            engine = self._resolve_engine_name(game_folder, selected_engine)
        except Exception as err:
            messagebox.showerror("Engine Detection Failed", f"Could not auto-detect engine:\n{err}")
            return

        cmd = [sys.executable, "-m", "gamestringer.cli"]
        if self.verbose_var.get():
            cmd.append("--verbose")

        cmd.extend(["patch", "--engine", engine, "--input", game_folder, "--xliff", xliff_path])

        if output_folder:
            cmd.extend(["--output", output_folder])

        dumper_path = self.il2cppdumper_path_var.get().strip()
        if dumper_path:
            cmd.extend(["--il2cppdumper-path", dumper_path])

        self._save_current_settings()
        self._set_running_state(True, task_type="patch")
        self._append_log(f"\n--- Starting Repatch Task --- [{engine}]\nCommand: {' '.join(cmd)}\n")

        threading.Thread(target=self._run_subprocess_task, args=(cmd, "patch", output_folder), daemon=True).start()

    def _run_subprocess_task(self, cmd: list, task_type: str, target_path: str):
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = PROJECT_ROOT + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")

            process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
            )

            for line in iter(process.stdout.readline, ""):
                if line:
                    self.msg_queue.put(("log", line))

            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.msg_queue.put(("success", (task_type, target_path)))
            else:
                self.msg_queue.put(("error", (task_type, f"Process exited with status code {return_code}")))

        except Exception as err:
            self.msg_queue.put(("error", (task_type, str(err))))

    def _poll_queue(self):
        """Poll thread queue for real-time log updates and task completion."""
        try:
            while True:
                msg_type, payload = self.msg_queue.get_nowait()
                if msg_type == "log":
                    self._append_log(payload)
                elif msg_type == "success":
                    task_type, target_path = payload
                    self._on_task_success(task_type, target_path)
                elif msg_type == "error":
                    task_type, err_msg = payload
                    self._on_task_error(task_type, err_msg)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    def _on_task_success(self, task_type: str, target_path: str):
        self._set_running_state(False)

        if task_type == "extract":
            self.last_generated_xliff = target_path
            self.last_generated_output_folder = os.path.dirname(os.path.abspath(target_path))

            # Calculate string count & size
            size_mb = 0.0
            if os.path.exists(target_path):
                size_mb = os.path.getsize(target_path) / (1024 * 1024)

            self.status_var.set(f"Result: Success | Extracted to '{os.path.basename(target_path)}' | Size: {size_mb:.2f} MB")
            self.lbl_result.configure(foreground="#2e7d32")

            self.btn_open_xliff.configure(state="normal")
            self.btn_open_out_folder.configure(state="normal")

            messagebox.showinfo("Extraction Complete", f"Text extraction complete!\nSaved to:\n{target_path}")

        elif task_type == "patch":
            self.last_generated_output_folder = target_path
            self.status_var.set(f"Result: Success | Repatched to '{os.path.basename(target_path)}'")
            self.lbl_result.configure(foreground="#2e7d32")

            self.btn_open_out_folder.configure(state="normal")

            messagebox.showinfo("Repatch Complete", f"Game files repatched successfully!\nOutput folder:\n{target_path}")

    def _on_task_error(self, task_type: str, err_msg: str):
        self._set_running_state(False)
        self.status_var.set(f"Result: ERROR ({task_type}) — See log for details.")
        self.lbl_result.configure(foreground="#c62828")
        self._append_log(f"\n[ERROR] Task '{task_type}' failed: {err_msg}\n")
        messagebox.showerror("Task Failed", f"Operation failed:\n{err_msg}")

    def _set_running_state(self, running: bool, task_type: str = ""):
        if running:
            self.btn_extract.configure(state="disabled")
            self.btn_patch.configure(state="disabled")
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(10)
            self.progress_percent_var.set("Running...")
        else:
            self.btn_extract.configure(state="normal")
            self.btn_patch.configure(state="normal")
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate", value=100)
            self.progress_percent_var.set("100%")

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _open_xliff_file(self):
        xliff_path = self.xliff_path_var.get().strip() or self.last_generated_xliff
        if xliff_path:
            open_system_path(xliff_path)

    def _open_output_folder(self):
        out_folder = self.output_folder_var.get().strip() or self.last_generated_output_folder
        if out_folder:
            open_system_path(out_folder)

    # ─────────────────────────────────────────────────────────────
    # SETTINGS PERSISTENCE
    # ─────────────────────────────────────────────────────────────

    def _load_saved_settings(self):
        s = load_settings()
        if "game_folder" in s:
            self.game_folder_var.set(s["game_folder"])
        if "xliff_path" in s:
            self.xliff_path_var.set(s["xliff_path"])
        if "output_folder" in s:
            self.output_folder_var.set(s["output_folder"])
        if "il2cppdumper_path" in s:
            self.il2cppdumper_path_var.set(s["il2cppdumper_path"])
        if "engine" in s:
            self.engine_var.set(s["engine"])
        if "dry_run" in s:
            self.dry_run_var.set(s["dry_run"])
        if "verbose" in s:
            self.verbose_var.set(s["verbose"])
        if "skip_garbage" in s:
            self.skip_garbage_var.set(s["skip_garbage"])

    def _save_current_settings(self):
        s = {
            "game_folder": self.game_folder_var.get(),
            "xliff_path": self.xliff_path_var.get(),
            "output_folder": self.output_folder_var.get(),
            "il2cppdumper_path": self.il2cppdumper_path_var.get(),
            "engine": self.engine_var.get(),
            "dry_run": self.dry_run_var.get(),
            "verbose": self.verbose_var.get(),
            "skip_garbage": self.skip_garbage_var.get(),
        }
        save_settings(s)


def main():
    root = tk.Tk()
    app = GameStringerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
