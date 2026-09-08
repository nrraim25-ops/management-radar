"""src/fetch_pdfs.py — Download and cache BSE PDF filings."""

import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.config import FETCH_TIMEOUT, PDF_DIR, PDF_USER_AGENT
from src.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_all_pdfs() -> None:
    """Download all pending BSE_PDF sources. Idempotent — skips already-cached files."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, url, local_path, fetch_status FROM sources WHERE source_type='pdf'"
        ).fetchall()

    for row in rows:
        source_id = row["id"]
        url = row["url"]
        local_path = row["local_path"]

        # Skip if already successfully fetched and file exists on disk
        if row["fetch_status"] == "ok" and local_path and Path(local_path).exists():
            print(f"[fetch_pdfs] source {source_id} already cached, skipping")
            continue

        dest = PDF_DIR / f"{source_id}.pdf"

        # Also skip if the file was previously downloaded (idempotency)
        if dest.exists():
            print(f"[fetch_pdfs] source {source_id} file exists, marking ok")
            _mark_ok(source_id, str(dest))
            continue

        print(f"[fetch_pdfs] fetching source {source_id}: {url}")
        _download(source_id, url, dest)


def _download(source_id: int, url: str, dest: Path) -> None:
    try:
        headers = {"User-Agent": PDF_USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT, stream=True)
        resp.raise_for_status()

        # Validate content type
        ct = resp.headers.get("Content-Type", "")
        if "pdf" not in ct.lower() and not url.lower().endswith(".pdf"):
            raise ValueError(f"Unexpected content-type: {ct}")

        dest.write_bytes(resp.content)
        _mark_ok(source_id, str(dest))
        print(f"[fetch_pdfs] ✓ source {source_id} saved to {dest}")

    except Exception as exc:
        _mark_failed(source_id, str(exc))
        print(f"[fetch_pdfs] ✗ source {source_id} failed: {exc}")


def _mark_ok(source_id: int, local_path: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET fetch_status='ok', local_path=?, fetched_at=?, fetch_error=NULL WHERE id=?",
            (local_path, _now(), source_id),
        )


def _mark_failed(source_id: int, error: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET fetch_status='failed', fetch_error=?, fetched_at=? WHERE id=?",
            (error[:1000], _now(), source_id),
        )
