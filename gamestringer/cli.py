"""
GameStringer CLI — Standalone Python Command Line Tool for Game Text Extraction & Repatching.
"""

import sys
import os

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add parent directory to sys.path for direct execution support
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List
from gamestringer.core.logger import setup_logger, logger
from gamestringer.core.base_engine import BaseEngine
from gamestringer.core.xliff_exporter import parse_xliff, validate_xliff, update_xliff
from gamestringer.core.batch import run_batch, auto_detect_engine
from gamestringer.core.quote_checker import check_xliff_quotes
from gamestringer.core.font_checker import check_game_fonts
from gamestringer.core.addressables_crc import fix_catalog_crc_command
from gamestringer.engines.renpy import RenpyEngine
from gamestringer.engines.unreal import UnrealEngine
from gamestringer.engines.unity_mono import UnityMonoEngine
from gamestringer.engines.cri import CriEngine
from gamestringer.engines.il2cpp_hybrid import IL2CppHybridEngine, find_il2cppdumper_path, IL2CPPDUMPER_URL

# Register all engine implementations
ENGINE_REGISTRY: Dict[str, BaseEngine] = {
    "renpy": RenpyEngine(),
    "unreal": UnrealEngine(),
    "unity": UnityMonoEngine(),
    "cri": CriEngine(),
    "il2cpp": IL2CppHybridEngine(),
}


def get_engine(name: str) -> BaseEngine:
    """Retrieve an engine instance by name."""
    engine = ENGINE_REGISTRY.get(name.lower())
    if not engine:
        available = ", ".join(ENGINE_REGISTRY.keys())
        raise ValueError(f"Unknown engine '{name}'. Available engines: {available}")
    return engine


# ─────────────────────────────────────────────────────────────
# CLI INTERFACE (Click with Argparse fallback)
# ─────────────────────────────────────────────────────────────

try:
    import click

    @click.group()
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose DEBUG logging.")
    @click.option("--quiet", "-q", is_flag=True, help="Enable quiet mode (show ERRORs only).")
    @click.version_option(version="1.0.0", prog_name="gamestringer")
    def main(verbose: bool, quiet: bool):
        """GameStringer CLI — Standalone game text extractor and repatcher."""
        setup_logger(verbose=verbose, quiet=quiet)

    @main.command(name="extract")
    @click.option("--engine", "-e", required=True, type=str, help="Engine name (renpy, unreal, unity, cri, il2cpp)")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input game file or directory")
    @click.option("--output", "-o", "output_path", required=True, type=click.Path(), help="Output XLIFF file path")
    @click.option("--dry-run", is_flag=True, help="Scan files and report string counts without writing output files.")
    @click.option("--il2cppdumper-path", type=click.Path(), help="Optional custom path to IL2CppDumper.exe binary.")
    def extract_cmd(engine: str, input_path: str, output_path: str, dry_run: bool, il2cppdumper_path: str):
        """Extract strings from game files into an XLIFF 1.2 file."""
        try:
            eng = get_engine(engine)
            logger.info(f"Extracting strings using engine '{eng.name}' from '{input_path}' (dry-run: {dry_run})...")
            if eng.name == "il2cpp":
                res_msg = eng.extract(input_path, output_path, dry_run=dry_run, il2cppdumper_path=il2cppdumper_path)
            else:
                res_msg = eng.extract(input_path, output_path, dry_run=dry_run)
            click.secho(f"[SUCCESS] {res_msg}", fg="green")
            sys.exit(0)
        except Exception as err:
            click.secho(f"[ERROR] Extraction error: {err}", fg="red", err=True)
            sys.exit(1)

    @main.command(name="patch")
    @click.option("--engine", "-e", required=True, type=str, help="Engine name (renpy, unreal, unity, cri, il2cpp)")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input game file or directory")
    @click.option("--xliff", "-x", "xliff_path", required=True, type=click.Path(exists=True), help="Translated XLIFF file path")
    @click.option("--output", "-o", "output_path", type=click.Path(), help="Optional output path for patched files")
    @click.option("--il2cppdumper-path", type=click.Path(), help="Optional custom path to IL2CppDumper.exe binary.")
    def patch_cmd(engine: str, input_path: str, xliff_path: str, output_path: str, il2cppdumper_path: str):
        """Repatch game files using translated strings from an XLIFF file."""
        try:
            eng = get_engine(engine)
            logger.info(f"Repatching game files using engine '{eng.name}'...")
            msg = eng.patch(input_path, xliff_path, output_path)
            click.secho(f"[SUCCESS] Repatch complete! {msg}", fg="green")
            sys.exit(0)
        except Exception as err:
            click.secho(f"[ERROR] Patch error: {err}", fg="red", err=True)
            sys.exit(1)

    @main.command(name="setup-il2cppdumper")
    def setup_il2cppdumper_cmd():
        """Check for IL2CppDumper installation and print setup guidance."""
        bin_path = find_il2cppdumper_path()
        if bin_path:
            click.secho(f"[FOUND] IL2CppDumper is installed at: {bin_path}", fg="green")
        else:
            click.secho("[NOT FOUND] IL2CppDumper is not installed in standard system locations.", fg="yellow")
            click.echo("\nInstallation Guidance:")
            click.echo(f"  1. Download IL2CppDumper release from: {IL2CPPDUMPER_URL}")
            click.echo("  2. Extract Il2CppDumper-v6.x.x-win.zip to: C:\\Tools\\IL2CppDumper\\")
            click.echo("  3. Or pass '--il2cppdumper-path \"C:\\path\\to\\IL2CppDumper.exe\"' to extract/patch commands.")

    @main.command(name="detect")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input game file or directory")
    def detect_cmd(input_path: str):
        """Detect which game engine matches the target input file or directory."""
        click.echo(f"[SCAN] Scanning '{input_path}' for matching engines...")
        matches = []
        for name, eng in ENGINE_REGISTRY.items():
            if eng.detect(input_path):
                matches.append(eng)

        if matches:
            click.secho(f"[MATCH] Matched {len(matches)} engine(s):", fg="green")
            for m in matches:
                click.echo(f"  • [{m.name}] {m.description}")
            sys.exit(0)
        else:
            click.secho("[NONE] No matching engines detected for input path.", fg="yellow")
            sys.exit(1)

    @main.command(name="batch")
    @click.option("--config", "-c", "config_path", required=True, type=click.Path(exists=True), help="Path to JSON or TOML batch configuration file")
    @click.option("--workers", "-w", default=4, type=int, help="Max worker threads (default: 4)")
    def batch_cmd(config_path: str, workers: int):
        """Run batch extraction or patching tasks from a configuration file."""
        try:
            results = run_batch(config_path, ENGINE_REGISTRY, max_workers=workers)
            failed = [r for r in results if r["status"] == "error"]
            if failed:
                click.secho(f"[WARNING] Batch finished with {len(failed)} error(s).", fg="yellow", err=True)
                sys.exit(1)
            else:
                click.secho(f"[SUCCESS] Batch completed successfully ({len(results)} task(s)).", fg="green")
                sys.exit(0)
        except Exception as err:
            click.secho(f"[ERROR] Batch execution error: {err}", fg="red", err=True)
            sys.exit(1)

    @main.command(name="validate")
    @click.option("--xliff", "-x", "xliff_path", required=True, type=click.Path(exists=True), help="XLIFF file path to validate")
    def validate_cmd(xliff_path: str):
        """Validate an XLIFF file for translation completeness and token safety."""
        try:
            report = validate_xliff(xliff_path)
            click.echo(f"Validation Report for: {xliff_path}")
            click.echo(f"  • Total strings: {report['total']}")
            click.echo(f"  • Translated:    {report['translated']}")
            click.echo(f"  • Untranslated:  {report['untranslated']}")

            if report["token_mismatches"]:
                click.secho(f"  • Token Mismatches: {len(report['token_mismatches'])} string(s)", fg="yellow")
                for m in report["token_mismatches"]:
                    click.echo(f"    - ID [{m['id']}]: missing {m['missing_tokens']}")

            if report["valid"]:
                click.secho("[SUCCESS] Validation PASSED! 100% translated with valid tokens.", fg="green")
                sys.exit(0)
            else:
                click.secho("[FAILURE] Validation FAILED! File has untranslated strings or token mismatches.", fg="red", err=True)
                sys.exit(1)
        except Exception as err:
            click.secho(f"[ERROR] Validation error: {err}", fg="red", err=True)
            sys.exit(1)

    @main.command(name="update")
    @click.option("--engine", "-e", default="auto", type=str, help="Engine name (default: auto-detect)")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Updated game file or directory")
    @click.option("--old-xliff", "-old", "old_xliff", required=True, type=click.Path(exists=True), help="Old translated XLIFF file")
    @click.option("--output", "-o", "output_path", required=True, type=click.Path(), help="Output merged XLIFF file path")
    def update_cmd(engine: str, input_path: str, old_xliff: str, output_path: str):
        """Re-extract game strings from updated game files and merge with old XLIFF."""
        try:
            if engine == "auto":
                eng = auto_detect_engine(input_path, ENGINE_REGISTRY)
            else:
                eng = get_engine(engine)

            click.echo(f"🔄 Re-extracting strings using '{eng.name}'...")
            tmp_new_xliff = output_path + ".new_tmp"
            eng.extract(input_path, tmp_new_xliff, dry_run=False)

            new_units = parse_xliff(tmp_new_xliff)
            os.remove(tmp_new_xliff)

            saved_path, stats = update_xliff(old_xliff, new_units, output_path)
            click.secho(
                f"[SUCCESS] Update complete! Kept: {stats['kept']} | New: {stats['new']} | Deprecated: {stats['deprecated']}. Saved to: {saved_path}",
                fg="green",
            )
            sys.exit(0)
        except Exception as err:
            click.secho(f"[ERROR] Update error: {err}", fg="red", err=True)
            sys.exit(1)

    @main.command(name="list-engines")
    def list_engines_cmd():
        """List all supported engine plugins."""
        click.echo("Available Game Engine Adapters:")
        for name, eng in ENGINE_REGISTRY.items():
            click.echo(f"  • {name:<10} - {eng.description}")

    @main.command(name="check-quotes")
    @click.option("--xliff", "-x", "xliff_path", required=True, type=click.Path(exists=True), help="Input XLIFF file path")
    @click.option("--output", "-o", "output_path", type=click.Path(), help="Optional JSON output report path")
    def check_quotes_cmd(xliff_path: str, output_path: str):
        """Check XLIFF file for quote style mismatches, font incompatibility, and unbalanced quotes."""
        res = check_xliff_quotes(xliff_path, output_path)
        issues_found = res["issues_found"]
        total = res["total_checked"]
        if issues_found > 0:
            click.secho(f"[WARNING] Found {issues_found} quote issue(s) across {total} checked string(s).", fg="yellow")
            for iss in res["issues"][:10]:
                click.echo(f"  [{iss['id']}] [{iss['issue']}] Source: {iss['source']} | Target: {iss['target']} -> Rec: {iss['recommendation']}")
            if issues_found > 10:
                click.echo(f"  ... and {issues_found - 10} more issue(s).")
            sys.exit(1)
        else:
            click.secho(f"[SUCCESS] Checked {total} string(s). No quote mismatches or unbalanced quotes found!", fg="green")
            sys.exit(0)

    @main.command(name="check-fonts")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input game file or directory")
    @click.option("--engine", "-e", required=True, type=str, help="Engine name (unity, il2cpp, unreal, renpy, cri)")
    def check_fonts_cmd(input_path: str, engine: str):
        """Check game font assets for Hungarian character glyph support (ő/ű)."""
        res = check_game_fonts(input_path, engine)
        status = res.get("status")
        if status == "supported":
            click.secho(f"{res['message']}", fg="green")
        elif status == "warning":
            click.secho(f"{res['message']}", fg="yellow")
        else:
            click.echo(res.get("message"))

    @main.command(name="fix-catalog")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input Unity game directory containing Addressables catalog.json")
    def fix_catalog_cmd(input_path: str):
        """Recalculate CRC32 hashes for patched asset bundles and update catalog.json."""
        res = fix_catalog_crc_command(input_path)
        if res.get("catalog_found"):
            click.secho(f"[SUCCESS] {res['message']}", fg="green")
        else:
            click.secho(f"[WARNING] {res['message']}", fg="yellow")

except ImportError:
    # Argparse fallback
    import argparse

    def main():
        setup_logger()
        parser = argparse.ArgumentParser(prog="gamestringer", description="GameStringer CLI — Game text extractor and repatcher.")
        parser.add_argument("--verbose", "-v", action="store_true")
        parser.add_argument("--quiet", "-q", action="store_true")
        subparsers = parser.add_subparsers(dest="command")

        # extract
        ext_p = subparsers.add_parser("extract")
        ext_p.add_argument("--engine", "-e", required=True)
        ext_p.add_argument("--input", "-i", required=True)
        ext_p.add_argument("--output", "-o", required=True)
        ext_p.add_argument("--dry-run", action="store_true")
        ext_p.add_argument("--il2cppdumper-path")

        # patch
        patch_p = subparsers.add_parser("patch")
        patch_p.add_argument("--engine", "-e", required=True)
        patch_p.add_argument("--input", "-i", required=True)
        patch_p.add_argument("--xliff", "-x", required=True)
        patch_p.add_argument("--output", "-o")
        patch_p.add_argument("--il2cppdumper-path")

        # setup-il2cppdumper
        setup_p = subparsers.add_parser("setup-il2cppdumper")

        # detect
        det_p = subparsers.add_parser("detect")
        det_p.add_argument("--input", "-i", required=True)

        # validate
        val_p = subparsers.add_parser("validate")
        val_p.add_argument("--xliff", "-x", required=True)

        # check-quotes
        cq_p = subparsers.add_parser("check-quotes")
        cq_p.add_argument("--xliff", "-x", required=True)
        cq_p.add_argument("--output", "-o")

        # check-fonts
        cf_p = subparsers.add_parser("check-fonts")
        cf_p.add_argument("--input", "-i", required=True)
        cf_p.add_argument("--engine", "-e", required=True)

        # fix-catalog
        fc_p = subparsers.add_parser("fix-catalog")
        fc_p.add_argument("--input", "-i", required=True)

        args = parser.parse_args()

        if args.command == "extract":
            eng = get_engine(args.engine)
            if eng.name == "il2cpp":
                res = eng.extract(args.input, args.output, dry_run=args.dry_run, il2cppdumper_path=args.il2cppdumper_path)
            else:
                res = eng.extract(args.input, args.output, dry_run=args.dry_run)
            print(f"Extraction complete! {res}")
            sys.exit(0)
        elif args.command == "patch":
            eng = get_engine(args.engine)
            res = eng.patch(args.input, args.xliff, args.output)
            print(f"Patch complete! {res}")
            sys.exit(0)
        elif args.command == "setup-il2cppdumper":
            b_path = find_il2cppdumper_path()
            if b_path:
                print(f"IL2CppDumper found at: {b_path}")
            else:
                print(f"IL2CppDumper not found. Download from: {IL2CPPDUMPER_URL}")
        elif args.command == "validate":
            rep = validate_xliff(args.xliff)
            print(f"Validation result: {rep}")
            sys.exit(0 if rep["valid"] else 1)
        elif args.command == "check-quotes":
            rep = check_xliff_quotes(args.xliff, args.output)
            print(f"Quote check result: {rep}")
            sys.exit(0 if rep["issues_found"] == 0 else 1)
        elif args.command == "check-fonts":
            rep = check_game_fonts(args.input, args.engine)
            print(f"Font check result: {rep}")
            sys.exit(0)
        elif args.command == "fix-catalog":
            rep = fix_catalog_crc_command(args.input)
            print(f"Fix catalog result: {rep}")
            sys.exit(0)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
