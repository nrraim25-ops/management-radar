"""scripts/reset_db.py — Wipe and recreate the SQLite schema for clean re-runs."""

import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH
from src.db import init_db


def main():
    if DB_PATH.exists():
        print(f"[reset_db] deleting existing DB at {DB_PATH}")
        DB_PATH.unlink()
    init_db()
    print("[reset_db] ✓ database reset complete")


if __name__ == "__main__":
    main()
