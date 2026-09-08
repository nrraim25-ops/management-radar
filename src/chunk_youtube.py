"""src/chunk_youtube.py — Group YouTube transcript lines into ~40-second timestamped chunks."""

import json
from pathlib import Path

from src.config import YOUTUBE_CHUNK_SECONDS
from src.db import get_conn


def _fmt_timestamp(seconds: float) -> str:
    """Format seconds as mm:ss."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def chunk_all_youtube() -> None:
    """Chunk all successfully-fetched YouTube sources that don't yet have chunks."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.local_path, s.title
            FROM sources s
            WHERE s.source_type = 'youtube'
              AND s.fetch_status = 'ok'
              AND s.local_path IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM chunks c WHERE c.source_id = s.id)
            """
        ).fetchall()

    if not rows:
        print("[chunk_youtube] no new YouTube sources to chunk")
        return

    for row in rows:
        source_id = row["id"]
        local_path = row["local_path"]
        title = row["title"]
        print(f"[chunk_youtube] chunking source {source_id}: {title}")
        try:
            _chunk_transcript(source_id, Path(local_path))
        except Exception as exc:
            print(f"[chunk_youtube] ✗ source {source_id} failed: {exc}")


def _chunk_transcript(source_id: int, path: Path) -> None:
    """Group transcript lines into ~YOUTUBE_CHUNK_SECONDS windows."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    # raw: list of {text, start, duration}

    chunks = []
    current_texts: list[str] = []
    current_start: float = raw[0]["start"] if raw else 0.0
    chunk_index = 0

    for line in raw:
        start = line.get("start", 0.0)
        text = line.get("text", "").strip()
        if not text:
            continue

        # Start a new chunk when we exceed the window size
        if start - current_start >= YOUTUBE_CHUNK_SECONDS and current_texts:
            chunks.append({
                "source_id": source_id,
                "text": " ".join(current_texts),
                "locator": _fmt_timestamp(current_start),
                "chunk_index": chunk_index,
            })
            chunk_index += 1
            current_texts = []
            current_start = start

        current_texts.append(text)

    # Flush remaining lines
    if current_texts:
        chunks.append({
            "source_id": source_id,
            "text": " ".join(current_texts),
            "locator": _fmt_timestamp(current_start),
            "chunk_index": chunk_index,
        })

    if not chunks:
        print(f"[chunk_youtube] WARNING: source {source_id} yielded no chunks")
        return

    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO chunks (source_id, text, locator, chunk_index) VALUES (:source_id, :text, :locator, :chunk_index)",
            chunks,
        )
    print(f"[chunk_youtube] ✓ source {source_id}: {len(chunks)} chunks ({YOUTUBE_CHUNK_SECONDS}s windows)")
