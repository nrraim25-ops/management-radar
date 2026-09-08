"""Reset YouTube sources to pending so they retry on next pipeline run."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import get_conn

with get_conn() as conn:
    n = conn.execute(
        "UPDATE sources SET fetch_status='pending', fetch_error=NULL WHERE source_type='youtube'"
    ).rowcount
    print(f"Reset {n} YouTube source(s) to pending")
