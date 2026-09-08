"""src/ingest.py — Parse PDF files into page-level text chunks (pdfplumber)."""

from pathlib import Path

import pdfplumber

from src.db import get_conn


def ingest_all_pdfs() -> None:
    """Chunk all successfully-fetched PDF sources that don't yet have chunks."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.local_path, s.title
            FROM sources s
            WHERE s.source_type = 'pdf'
              AND s.fetch_status = 'ok'
              AND s.local_path IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM chunks c WHERE c.source_id = s.id)
            """
        ).fetchall()

    if not rows:
        print("[ingest] no new PDF sources to ingest")
        return

    for row in rows:
        source_id = row["id"]
        local_path = row["local_path"]
        title = row["title"]
        print(f"[ingest] processing source {source_id}: {title}")
        try:
            _chunk_pdf(source_id, Path(local_path))
        except Exception as exc:
            print(f"[ingest] ✗ source {source_id} failed: {exc}")


def _chunk_pdf(source_id: int, path: Path) -> None:
    """Extract one chunk per page using pdfplumber (text + tables)."""
    chunks = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            parts = []

            # Extract prose text
            text = page.extract_text()
            if text:
                parts.append(text.strip())

            # Extract tables separately to avoid mangling into prose
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                # Render table as pipe-delimited text for readability
                rows_text = []
                for row in table:
                    clean_row = [str(cell).strip() if cell else "" for cell in row]
                    rows_text.append(" | ".join(clean_row))
                parts.append("\n".join(rows_text))

            combined = "\n\n".join(parts).strip()
            if not combined:
                continue

            chunks.append({
                "source_id": source_id,
                "text": combined,
                "locator": f"page {page_num}",
                "chunk_index": page_num - 1,
            })

    if not chunks:
        print(f"[ingest] ⚠ source {source_id} yielded no text chunks")
        return

    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO chunks (source_id, text, locator, chunk_index) VALUES (:source_id, :text, :locator, :chunk_index)",
            chunks,
        )
    print(f"[ingest] ✓ source {source_id}: {len(chunks)} page-chunks inserted")
