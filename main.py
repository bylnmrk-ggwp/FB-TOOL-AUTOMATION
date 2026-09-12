"""Launcher for the FB Tool desktop app.

    python main.py    open the desktop (Tkinter) window

The window drives the DriverManager, the SQLite database and the Brave
profiles on this PC.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from src.app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
