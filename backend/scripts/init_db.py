from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import initialize_database


if __name__ == "__main__":
    initialize_database(Path("data") / "traderlens.sqlite3")
    print("Initialized data/traderlens.sqlite3")
