"""Run the analysis queue in a second terminal: python worker.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from yanji.worker import main

if __name__ == "__main__":
    main()
