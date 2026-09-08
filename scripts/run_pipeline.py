"""
scripts/run_pipeline.py — ONE command to run the full pipeline end-to-end.

Stages (all idempotent — safe to re-run):
  1. Load CSV → upsert companies + sources
  2. Fetch pending BSE PDFs
  3. Fetch pending YouTube transcripts
  4. Ingest (chunk) OK sources without chunks
  5. Tag sources without source_tags row
  6. Embed chunks with NULL embedding
"""

import csv
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CSV_PATH, GEMINI_API_KEY
from src.db import get_conn, init_db
from src.fetch_pdfs import fetch_all_pdfs
from src.fetch_youtube import fetch_all_transcripts
from src.ingest import ingest_all_pdfs
from src.chunk_youtube import chunk_all_youtube
from src.tagging import tag_all_sources
from src.embeddings import embed_all_chunks


TYPE_MAP = {"BSE_PDF": "pdf", "YOUTUBE": "youtube"}


def load_csv() -> None:
    """Stage 1: Parse disclosure_links.csv and upsert companies + sources."""
    print("\n── Stage 1: Loading CSV ──────────────────────────────────────────")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with get_conn() as conn:
        for row in rows:
            company_name = row["company"].strip()
            source_type = TYPE_MAP.get(row["type"].strip(), "pdf")
            title = row["title"].strip()
            url = row["url"].strip()
            published_date = row["date"].strip() or None

            # Upsert company
            conn.execute(
                "INSERT OR IGNORE INTO companies (name) VALUES (?)",
                (company_name,),
            )
            company_id = conn.execute(
                "SELECT id FROM companies WHERE name=?", (company_name,)
            ).fetchone()["id"]

            # Upsert source (by URL — skip if already exists)
            existing = conn.execute(
                "SELECT id FROM sources WHERE url=?", (url,)
            ).fetchone()
            if existing:
                continue

            conn.execute(
                """INSERT INTO sources
                   (company_id, source_type, title, url, published_date, fetch_status)
                   VALUES (?,?,?,?,?,'pending')""",
                (company_id, source_type, title, url, published_date),
            )

    # Print summary
    with get_conn() as conn:
        companies = conn.execute("SELECT id, name FROM companies").fetchall()
        sources = conn.execute("SELECT id, title, source_type, fetch_status FROM sources").fetchall()
    print(f"  Companies: {[c['name'] for c in companies]}")
    print(f"  Sources: {len(sources)} total")


def main():
    print("=" * 60)
    print("  Management Radar — Full Pipeline")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("\n[WARNING] GEMINI_API_KEY not set in .env -- tagging will fail.")
        print("   Set the key in .env and re-run to complete tagging + RAG.\n")

    # Ensure DB + schema exist
    init_db()

    # Stage 1: CSV → DB
    load_csv()

    # Stage 2: Fetch PDFs
    print("\n── Stage 2: Fetching PDFs ───────────────────────────────────────")
    fetch_all_pdfs()

    # Stage 3: Fetch YouTube transcripts
    print("\n── Stage 3: Fetching YouTube transcripts ────────────────────────")
    fetch_all_transcripts()

    # Stage 4: Ingest PDFs into chunks
    print("\n── Stage 4: Ingesting PDFs → chunks ─────────────────────────────")
    ingest_all_pdfs()

    # Stage 5: Chunk YouTube transcripts
    print("\n── Stage 4b: Chunking YouTube transcripts ───────────────────────")
    chunk_all_youtube()

    # Stage 5: Tag all unchunked sources
    print("\n── Stage 5: Tagging sources (LLM) ───────────────────────────────")
    if GEMINI_API_KEY:
        tag_all_sources()
    else:
        print("  Skipped — no GEMINI_API_KEY")

    # Stage 6: Embed all un-embedded chunks
    print("\n── Stage 6: Embedding chunks ────────────────────────────────────")
    embed_all_chunks()

    print("\n" + "=" * 60)
    print("  Pipeline complete! Run: streamlit run app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
