"""
GameStringer CLI / GUI Main Package Entry Point.
"""

import sys
import os

# Add parent directory to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gamestringer.desktop_gui.app import main as main_desktop_gui
from gamestringer.cli import main as main_cli


def main():
    if "--gui" in sys.argv:
        sys.argv.remove("--gui")
        main_desktop_gui()
    else:
        main_cli()


if __name__ == "__main__":
    main()
