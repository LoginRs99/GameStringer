"""
Unit and Interaction Test Suite for GameStringer Desktop GUI.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
import tkinter as tk
from unittest.mock import patch, MagicMock

import pytest
import yaml

from gamestringer.desktop_gui.app import create_app, GameStringerApp, SETTINGS_FILE
from gamestringer.desktop_gui.tooltip import ToolTip, create_tooltip
from gamestringer.desktop_gui.widgets import labeled_entry, labeled_combo, labeled_checkbutton
from gamestringer.desktop_gui.tabs.projects_tab import ProjectsTab, CategoryEditDialog
from gamestringer.desktop_gui.tabs.preflight_tab import PreflightTab
from gamestringer.desktop_gui.tabs.audit_tab import AuditTab
from gamestringer.desktop_gui.tabs.run_tab import RunTab


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_tooltip_creation_and_events(tk_root):
    btn = tk.Button(tk_root, text="Test")
    tip = create_tooltip(btn, "Helpful tooltip text", delay_ms=10)
    assert tip.text == "Helpful tooltip text"

    # Simulate enter and show
    tip._show_tip()
    assert tip.tip_window is not None
    assert tip.tip_window.winfo_exists()

    # Simulate hide
    tip._hide_tip()
    assert tip.tip_window is None


def test_projects_tab_json_validation_blocks_bad_save(tk_root, tmp_path):
    # Setup test project
    proj_dir = tmp_path / "locpipe" / "projects" / "test_game"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(yaml.dump({
        "project": "test_game",
        "source_lang": "en",
        "target_lang": "hu",
        "format": "uabea_json",
        "format_options": {"character_replacements": {"a": "b"}}
    }), encoding="utf-8")

    with patch("gamestringer.desktop_gui.tabs.projects_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"):
        tab = ProjectsTab(tk.ttk.Notebook(tk_root), tk_root)
        tab._load_project_by_name("test_game")

        # Set invalid JSON
        tab.var_char_replacements.set("{bad_json: invalid")

        with patch("tkinter.messagebox.showerror") as mock_err:
            success = tab.save_project()
            assert success is False
            assert mock_err.called
            # Verify field was NOT silently reset to {}
            assert tab.var_char_replacements.get() == "{bad_json: invalid"


def test_projects_tab_dirty_tracking(tk_root, tmp_path):
    proj_dir = tmp_path / "locpipe" / "projects" / "test_game"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(yaml.dump({
        "project": "test_game",
        "source_lang": "en",
        "target_lang": "hu",
        "format": "uabea_json"
    }), encoding="utf-8")

    with patch("gamestringer.desktop_gui.tabs.projects_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"):
        tab = ProjectsTab(tk.ttk.Notebook(tk_root), tk_root)
        tab._load_project_by_name("test_game")
        assert tab.is_dirty is False

        # Modify a field
        tab.var_target_lang.set("de")
        assert tab.is_dirty is True


def test_preflight_tab_engine_dropdown_options(tk_root):
    tab = PreflightTab(tk.ttk.Notebook(tk_root), tk_root)
    # Target engine combobox values must only be unity and il2cpp
    combo = None
    for child in tab.winfo_children():
        for sub in child.winfo_children():
            for sub2 in sub.winfo_children():
                if isinstance(sub2, tk.ttk.Combobox):
                    combo = sub2
                    break

    # Check var values
    assert tab.var_font_engine.get() in ["unity", "il2cpp"]


def test_shared_project_selection(tk_root, tmp_path):
    # Setup two test projects
    p1 = tmp_path / "locpipe" / "projects" / "proj_alpha"
    p2 = tmp_path / "locpipe" / "projects" / "proj_beta"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)
    (p1 / "project.yaml").write_text("project: proj_alpha\nsource_lang: en\ntarget_lang: hu\nformat: uabea_json\n", encoding="utf-8")
    (p2 / "project.yaml").write_text("project: proj_beta\nsource_lang: en\ntarget_lang: hu\nformat: uabea_json\n", encoding="utf-8")

    with patch("gamestringer.desktop_gui.tabs.projects_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"), \
         patch("gamestringer.desktop_gui.tabs.audit_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"), \
         patch("gamestringer.desktop_gui.tabs.run_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"):

        app = GameStringerApp(tk_root)
        app.tab_projects.refresh_project_list()
        app.tab_audit.refresh_projects()
        app.tab_run.refresh_projects()

        # Switch project via ProjectsTab
        app.tab_projects.select_project("proj_beta")
        assert app.shared_project_var.get() == "proj_beta"
        assert app.tab_audit.var_selected_project.get() == "proj_beta"
        assert app.tab_run.var_selected_project.get() == "proj_beta"


def test_run_tab_confirmation_dialog(tk_root, tmp_path):
    p1 = tmp_path / "locpipe" / "projects" / "proj_run_test"
    p1.mkdir(parents=True)
    (p1 / "project.yaml").write_text("project: proj_run_test\nsource_lang: en\ntarget_lang: hu\nformat: uabea_json\n", encoding="utf-8")

    with patch("gamestringer.desktop_gui.tabs.run_tab.get_default_projects_dir", return_value=tmp_path / "locpipe" / "projects"):
        tab = RunTab(tk.ttk.Notebook(tk_root), tk_root)
        tab.select_project("proj_run_test")

        # When user clicks Cancel on confirmation, no process is started
        with patch("tkinter.messagebox.askyesno", return_value=False) as mock_confirm:
            tab._start_translation()
            assert mock_confirm.called
            assert tab.is_running is False
            assert tab.active_process is None


def test_settings_persistence(tk_root, tmp_path):
    test_settings = tmp_path / "gamestringer_gui_settings.json"
    with patch("gamestringer.desktop_gui.app.SETTINGS_FILE", test_settings):
        app = GameStringerApp(tk_root)
        app.shared_project_var.set("saved_project_xyz")
        app._save_settings()

        assert test_settings.exists()
        saved = json.loads(test_settings.read_text(encoding="utf-8"))
        assert saved["last_project"] == "saved_project_xyz"
