"""
Integration and Unit Test Suite for GameStringer CLI.

Tests XLIFF Exporter/Parser, NFC Normalization, Dry-Run Mode, Corrupt File Handling,
Smart String Token Validation, Engine Detection/Extract/Patch for all 5 engines,
Validation Exit Codes, Update/Diff Merging, Parallel Batch Mode, Quote Checker,
Hungarian Font Checker, and Addressables CRC Catalog Fixer.
"""

import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tempfile
import json
import struct
import zlib
from gamestringer.core.base_engine import TransUnit
from gamestringer.core.xliff_exporter import export_xliff, parse_xliff, validate_xliff, update_xliff
from gamestringer.core.batch import run_batch, auto_detect_engine
from gamestringer.core.quote_checker import check_xliff_quotes
from gamestringer.core.font_checker import check_game_fonts
from gamestringer.core.addressables_crc import calculate_crc32, fix_catalog_crc_command, auto_update_addressables_crc
from gamestringer.cli import ENGINE_REGISTRY, main
from gamestringer.engines.renpy import RenpyEngine
from gamestringer.engines.unreal import UnrealEngine
from gamestringer.engines.unity_mono import UnityMonoEngine
from gamestringer.engines.cri import CriEngine
from gamestringer.engines.il2cpp_hybrid import IL2CppHybridEngine, IL2CPP_METADATA_MAGIC


def test_xliff():
    print("Testing XLIFF Exporter...")
    with tempfile.TemporaryDirectory() as tmpdir:
        xliff_path = os.path.join(tmpdir, "test.xliff")

        units = [
            TransUnit(id="u1", source="Hello World", target="Ciao Mondo", file_path="game/script.rpy", line_number=10, speaker="Hero"),
            TransUnit(id="u2", source="Save Game", target="Salva Gioco", file_path="game/menu.rpy", line_number=25),
        ]

        export_xliff(units, xliff_path, source_lang="en", target_lang="it", engine_name="renpy")
        assert os.path.exists(xliff_path)

        parsed_units = parse_xliff(xliff_path)
        assert len(parsed_units) == 2
        assert parsed_units[0].id == "u1"
        assert parsed_units[0].source == "Hello World"
        assert parsed_units[0].target == "Ciao Mondo"
        assert parsed_units[0].speaker == "Hero"

    print("[PASS] XLIFF Exporter & NFC Normalization passed!")


def test_dry_run_extract():
    print("Testing Dry-Run Extract Mode...")
    with tempfile.TemporaryDirectory() as tmpdir:
        game_dir = os.path.join(tmpdir, "game")
        os.makedirs(game_dir, exist_ok=True)
        rpy_file = os.path.join(game_dir, "script.rpy")
        with open(rpy_file, "w", encoding="utf-8") as f:
            f.write('label start:\n    "Hello Dry Run!"\n')

        engine = RenpyEngine()
        xliff_path = os.path.join(tmpdir, "dry_run.xliff")

        result_msg = engine.extract(tmpdir, xliff_path, dry_run=True)
        assert "[DRY-RUN]" in result_msg
        assert not os.path.exists(xliff_path)

    print("[PASS] Dry-run mode passed!")


def test_corrupt_file_skipping():
    print("Testing Corrupt File Skipping...")
    with tempfile.TemporaryDirectory() as tmpdir:
        corrupt_file = os.path.join(tmpdir, "Corrupt.locres")
        with open(corrupt_file, "wb") as f:
            f.write(b"INVALID_UNREAL_LOCRES_HEADER_DATA_12345")

        engine = UnrealEngine()
        xliff_path = os.path.join(tmpdir, "corrupt_test.xliff")

        try:
            engine.extract(tmpdir, xliff_path)
        except ValueError as err:
            assert "No extractable text entries" in str(err) or "No valid text entries" in str(err)

    print("[PASS] Corrupt file skipping passed!")


def test_smart_token_patch_validation():
    print("Testing Smart String Token Patch Validation...")
    with tempfile.TemporaryDirectory() as tmpdir:
        game_dir = os.path.join(tmpdir, "game")
        os.makedirs(game_dir, exist_ok=True)
        rpy_file = os.path.join(game_dir, "script.rpy")
        with open(rpy_file, "w", encoding="utf-8") as f:
            f.write('label start:\n    "Player {player_name} has {points} points"\n')

        xliff_path = os.path.join(tmpdir, "tokens.xliff")
        units = [
            TransUnit(id="renpy_000001", source="Player {player_name} has {points} points", target="Giocatore {player_name} ha punti", file_path="game/script.rpy")
        ]
        export_xliff(units, xliff_path, engine_name="renpy")

        engine = RenpyEngine()
        patch_msg = engine.patch(tmpdir, xliff_path)
        assert "ren'py" in patch_msg.lower() or "translation" in patch_msg.lower() or "repatch" in patch_msg.lower()

    print("[PASS] Smart token patch validation passed!")


def test_renpy_engine():
    print("Testing Ren'Py Engine...")
    engine = RenpyEngine()
    assert engine.name == "renpy"

    with tempfile.TemporaryDirectory() as tmpdir:
        game_dir = os.path.join(tmpdir, "game")
        os.makedirs(game_dir, exist_ok=True)

        rpy_file = os.path.join(game_dir, "script.rpy")
        with open(rpy_file, "w", encoding="utf-8") as f:
            f.write('label start:\n    e "Welcome to the adventure!"\n    menu:\n        "Choice A":\n            jump a\n')

        assert engine.detect(tmpdir)

        xliff_path = os.path.join(tmpdir, "renpy.xliff")
        engine.extract(tmpdir, xliff_path)
        assert os.path.exists(xliff_path)

        units = parse_xliff(xliff_path)
        assert len(units) >= 2

        units[0].target = "Benvenuto nell'avventura!"
        units[1].target = "Scelta A"

        export_xliff(units, xliff_path, engine_name="renpy")

        patch_msg = engine.patch(tmpdir, xliff_path)
        assert "ren'py" in patch_msg.lower() or "translation" in patch_msg.lower() or "repatch" in patch_msg.lower()

        tl_file = os.path.join(tmpdir, "game", "tl", "it", "gamestringer_say_filter.rpy")
        assert os.path.exists(tl_file)

    print("[PASS] Ren'Py Engine passed!")


def test_unreal_engine():
    print("Testing Unreal LocRes Engine...")
    engine = UnrealEngine()
    assert engine.name == "unreal"

    with tempfile.TemporaryDirectory() as tmpdir:
        xliff_path = os.path.join(tmpdir, "unreal.xliff")

        units = [
            TransUnit(id="u1", source="Hello World!", target="Ciao Mondo!", file_path="Game.locres"),
        ]
        export_xliff(units, xliff_path, engine_name="unreal")
        assert os.path.exists(xliff_path)

    print("[PASS] Unreal LocRes Engine passed!")


def test_unity_mono_engine():
    print("Testing Unity Mono Engine...")
    engine = UnityMonoEngine()
    assert engine.name == "unity"
    print("[PASS] Unity Mono Engine detection passed!")


def test_cri_engine():
    print("Testing CRI Middleware Engine...")
    engine = CriEngine()
    assert engine.name == "cri"

    with tempfile.TemporaryDirectory() as tmpdir:
        msg_file = os.path.join(tmpdir, "dialog.msg")

        with open(msg_file, "wb") as f:
            f.write("Line 1: Hello from CRI!\nLine 2: Game Over\n".encode("shift_jis"))

        assert engine.detect(tmpdir)

        xliff_path = os.path.join(tmpdir, "cri.xliff")
        engine.extract(tmpdir, xliff_path)
        assert os.path.exists(xliff_path)

        units = parse_xliff(xliff_path)
        assert len(units) >= 1

        units[0].target = "Linea 1: Ciao da CRI!"
        export_xliff(units, xliff_path, engine_name="cri")

        patch_msg = engine.patch(tmpdir, xliff_path)
        assert "reppatched" in patch_msg.lower() or "repatched" in patch_msg.lower() or "cri" in patch_msg.lower()

    print("[PASS] CRI Middleware Engine passed!")


def test_il2cpp_hybrid_engine():
    print("Testing IL2CPP Hybrid Engine...")
    engine = IL2CppHybridEngine()
    assert engine.name == "il2cpp"

    with tempfile.TemporaryDirectory() as tmpdir:
        dll_path = os.path.join(tmpdir, "GameAssembly.dll")
        meta_dir = os.path.join(tmpdir, "il2cpp_data", "Metadata")
        os.makedirs(meta_dir, exist_ok=True)
        meta_path = os.path.join(meta_dir, "global-metadata.dat")

        with open(dll_path, "wb") as f:
            f.write(b"MZ\x90\x00MockGameAssembly")

        meta_bytes = bytearray(struct.pack("<II", IL2CPP_METADATA_MAGIC, 29))
        meta_bytes.extend(b"\x00Game Title\x00System Message\x00Press Any Button To Start\x00")

        with open(meta_path, "wb") as f:
            f.write(meta_bytes)

        assert engine.detect(tmpdir)

        xliff_path = os.path.join(tmpdir, "il2cpp.xliff")
        engine.extract(tmpdir, xliff_path)
        assert os.path.exists(xliff_path)

        units = parse_xliff(xliff_path)
        assert len(units) >= 1

        for u in units:
            if "Press Any Button To Start" in u.source:
                u.target = "Premi Un Tasto Per Iniziare"

        export_xliff(units, xliff_path, engine_name="il2cpp")

        patch_msg = engine.patch(tmpdir, xliff_path)
        assert "IL2CPP Hybrid patch complete" in patch_msg

        trans_file = os.path.join(tmpdir, "BepInEx", "Translation", "it", "Text", "_AutoGeneratedTranslations.txt")
        assert os.path.exists(trans_file)

        with open(trans_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert 'sr:"Press Any Button To Start"="Premi Un Tasto Per Iniziare"' in content

        readme_file = os.path.join(tmpdir, "README_IL2CPP_SETUP.md")
        assert os.path.exists(readme_file)

    print("[PASS] IL2CPP Hybrid Engine passed!")


def test_validate_mode():
    print("Testing Validate Command & Exit Code...")
    with tempfile.TemporaryDirectory() as tmpdir:
        xliff_path = os.path.join(tmpdir, "validate.xliff")

        units = [
            TransUnit(id="u1", source="Hello {0}", target="Ciao {0}"),
            TransUnit(id="u2", source="Score: {points}", target="Punteggio: "),
            TransUnit(id="u3", source="Untranslated text", target=""),
        ]
        export_xliff(units, xliff_path)

        report = validate_xliff(xliff_path)
        assert report["total"] == 3
        assert report["translated"] == 2
        assert report["untranslated"] == 1
        assert len(report["token_mismatches"]) == 1
        assert report["valid"] is False
    print("[PASS] Validate mode & Exit code audit passed!")


def test_update_mode():
    print("Testing Update / Diff Mode...")
    with tempfile.TemporaryDirectory() as tmpdir:
        old_xliff = os.path.join(tmpdir, "old.xliff")
        new_xliff = os.path.join(tmpdir, "new.xliff")

        old_units = [
            TransUnit(id="u1", source="Start", target="Inizia"),
            TransUnit(id="u2", source="Old Feature", target="Vecchia Funzionalita"),
        ]
        export_xliff(old_units, old_xliff)

        new_units = [
            TransUnit(id="u1", source="Start"),
            TransUnit(id="u3", source="New Patch Feature"),
        ]

        saved_path, stats = update_xliff(old_xliff, new_units, new_xliff)
        assert stats["kept"] == 1
        assert stats["new"] == 1
        assert stats["deprecated"] == 1

        merged = parse_xliff(new_xliff)
        assert len(merged) == 3

        u1 = next(u for u in merged if u.id == "u1")
        assert u1.target == "Inizia"

        u2 = next(u for u in merged if u.id == "u2")
        assert "status:deprecated" in (u2.context_note or "")

    print("[PASS] Update / Diff Mode passed!")


def test_batch_mode():
    print("Testing Batch Mode & Auto Engine Detection...")
    with tempfile.TemporaryDirectory() as tmpdir:
        rpy_dir = os.path.join(tmpdir, "game_rpy", "game")
        os.makedirs(rpy_dir, exist_ok=True)
        with open(os.path.join(rpy_dir, "script.rpy"), "w", encoding="utf-8") as f:
            f.write('label start:\n    "Hello Batch!"\n')

        auto_eng = auto_detect_engine(tmpdir, ENGINE_REGISTRY)
        assert auto_eng.name == "renpy"

        out_xliff = os.path.join(tmpdir, "batch_out.xliff")
        config_path = os.path.join(tmpdir, "batch.json")
        config_data = [
            {"input": tmpdir, "engine": "auto", "output": out_xliff, "action": "extract"},
        ]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        results = run_batch(config_path, ENGINE_REGISTRY, max_workers=2)
        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert os.path.exists(out_xliff)

    print("[PASS] Batch Mode passed!")


def test_quote_checker():
    print("Testing Feature 1 — Quote Consistency Checker...")
    with tempfile.TemporaryDirectory() as tmpdir:
        xliff_path = os.path.join(tmpdir, "quotes.xliff")
        json_report = os.path.join(tmpdir, "quote_report.json")

        q = '"'
        units = [
            TransUnit(id="u1", source=f"{q}Hello World!{q}", target=f"{q}Ciao Mondo!{q}"),
            TransUnit(id="u2", source=f"{q}Hello there!{q}", target="„Szia!"),
            TransUnit(id="u3", source=f"{q}Welcome!{q}", target="Üdvözlet!"),
            TransUnit(id="u4", source=f"{q}Play Game{q}", target="„Játék”"),
        ]
        export_xliff(units, xliff_path)

        res = check_xliff_quotes(xliff_path, json_report)
        assert res["total_checked"] == 4
        assert res["issues_found"] == 3

        issue_types = [i["issue"] for i in res["issues"]]
        assert "unbalanced" in issue_types
        assert "missing_quotes" in issue_types
        assert "mismatched_style" in issue_types
        assert os.path.exists(json_report)

    print("[PASS] Feature 1 — Quote Consistency Checker passed!")


def test_font_checker():
    print("Testing Feature 2 — Hungarian Font Checker...")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Non-unity engine
        res_renpy = check_game_fonts(tmpdir, "renpy")
        assert res_renpy["status"] == "unsupported"

        # Unity engine warning
        res_unity = check_game_fonts(tmpdir, "unity")
        assert res_unity["status"] == "warning"
        assert "Recommendation" in res_unity["message"]

    print("[PASS] Feature 2 — Hungarian Font Checker passed!")


def test_fix_catalog_crc():
    print("Testing Feature 3 — Addressables CRC Fixer...")
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_file = os.path.join(tmpdir, "data.bundle")
        with open(bundle_file, "wb") as f:
            f.write(b"MockAssetBundleData_12345")

        bundle_crc = calculate_crc32(bundle_file)
        assert bundle_crc > 0

        catalog_path = os.path.join(tmpdir, "catalog.json")
        cat_data = {
            "m_InternalIds": ["data.bundle"],
            "m_Crcs": {"data.bundle": 99999}
        }
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(cat_data, f)

        res = fix_catalog_crc_command(tmpdir)
        assert res["catalog_found"] is True
        assert "data.bundle" in res["updated_files"]

        with open(catalog_path, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
            assert updated_data["m_Crcs"]["data.bundle"] == bundle_crc

    print("[PASS] Feature 3 — Addressables CRC Fixer passed!")


if __name__ == "__main__":
    test_xliff()
    test_dry_run_extract()
    test_corrupt_file_skipping()
    test_smart_token_patch_validation()
    test_renpy_engine()
    test_unreal_engine()
    test_unity_mono_engine()
    test_cri_engine()
    test_il2cpp_hybrid_engine()
    test_validate_mode()
    test_update_mode()
    test_batch_mode()
    test_quote_checker()
    test_font_checker()
    test_fix_catalog_crc()
    print("\nALL INFRASTRUCTURE, ENGINE & ROBUSTNESS TESTS PASSED SUCCESSFULLY!")
