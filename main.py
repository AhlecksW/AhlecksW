"""Entry point for the AhlecksW Macro Automator.

Run from source:  python main.py
Build an .exe:     see build.bat / README.md
"""

import os
import sys

# Make ``src`` importable whether run from source or frozen by PyInstaller.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from macroapp.app import main  # noqa: E402

if __name__ == "__main__":
    main()
