"""
GameStringer CLI — Engine-independent preflight and post-patch utilities.
"""

import os
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add parent directory to sys.path for direct execution support
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gamestringer.core.logger import setup_logger, logger
from gamestringer.core.font_checker import check_game_fonts
from gamestringer.core.addressables_crc import fix_catalog_crc_command

try:
    import click

    @click.group()
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose DEBUG logging.")
    @click.option("--quiet", "-q", is_flag=True, help="Enable quiet mode (show ERRORs only).")
    @click.version_option(version="2.0.0", prog_name="gamestringer")
    def main(verbose: bool = False, quiet: bool = False):
        """GameStringer CLI — Engine-independent localization utilities."""
        setup_logger(verbose=verbose, quiet=quiet)

    @main.command(name="check-fonts")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input game file or directory")
    @click.option("--engine", "-e", required=True, type=str, help="Engine name (unity, il2cpp, unreal, renpy, cri)")
    def check_fonts_cmd(input_path: str, engine: str):
        """Check game font assets for Hungarian character glyph support (ő/ű)."""
        res = check_game_fonts(input_path, engine)
        status = res.get("status")
        if status == "supported":
            click.secho(f"{res.get('message')}", fg="green")
            sys.exit(0)
        elif status == "warning":
            click.secho(f"{res.get('message')}", fg="yellow")
            sys.exit(0)
        else:
            click.echo(res.get("message"))
            sys.exit(0)

    @main.command(name="fix-catalog")
    @click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input Unity game directory containing Addressables catalog.json")
    def fix_catalog_cmd(input_path: str):
        """Recalculate CRC32 hashes for patched asset bundles and update catalog.json."""
        res = fix_catalog_crc_command(input_path)
        if res.get("catalog_found"):
            click.secho(f"[SUCCESS] {res.get('message')}", fg="green")
            sys.exit(0)
        else:
            click.secho(f"[WARNING] {res.get('message')}", fg="yellow")
            sys.exit(0)

except ImportError:
    import argparse

    def main():
        setup_logger()
        parser = argparse.ArgumentParser(prog="gamestringer", description="GameStringer CLI — Localization utilities.")
        parser.add_argument("--verbose", "-v", action="store_true")
        parser.add_argument("--quiet", "-q", action="store_true")
        subparsers = parser.add_subparsers(dest="command")

        # check-fonts
        cf_p = subparsers.add_parser("check-fonts")
        cf_p.add_argument("--input", "-i", required=True)
        cf_p.add_argument("--engine", "-e", required=True)

        # fix-catalog
        fc_p = subparsers.add_parser("fix-catalog")
        fc_p.add_argument("--input", "-i", required=True)

        args = parser.parse_args()

        if args.command == "check-fonts":
            rep = check_game_fonts(args.input, args.engine)
            print(f"Font check result: {rep.get('message')}")
            sys.exit(0)
        elif args.command == "fix-catalog":
            rep = fix_catalog_crc_command(args.input)
            print(f"Fix catalog result: {rep.get('message')}")
            sys.exit(0)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
