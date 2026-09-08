"""src/fetch_youtube.py — Pull and cache YouTube transcript JSONs with timestamps."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

from src.config import TRANSCRIPT_DIR
from src.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract video ID from URL: {url}")


def fetch_all_transcripts() -> None:
    """Fetch transcripts for all pending YouTube sources. Idempotent."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, url, local_path, fetch_status FROM sources WHERE source_type='youtube'"
        ).fetchall()

    for row in rows:
        source_id = row["id"]
        url = row["url"]
        local_path = row["local_path"]

        # Skip if already successfully fetched and file exists
        if row["fetch_status"] == "ok" and local_path and Path(local_path).exists():
            print(f"[fetch_youtube] source {source_id} already cached, skipping")
            continue

        dest = TRANSCRIPT_DIR / f"{source_id}.json"

        if dest.exists():
            print(f"[fetch_youtube] source {source_id} transcript exists, marking ok")
            _mark_ok(source_id, str(dest))
            continue

        print(f"[fetch_youtube] fetching transcript for source {source_id}: {url}")
        _fetch_transcript(source_id, url, dest)


def _fetch_transcript(source_id: int, url: str, dest: Path) -> None:
    try:
        video_id = _extract_video_id(url)
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        # transcript is a list of {text, start, duration}
        dest.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        _mark_ok(source_id, str(dest))
        print(f"[fetch_youtube] ✓ source {source_id} transcript saved ({len(transcript)} lines)")

    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        _mark_failed(source_id, f"No transcript available: {exc}")
        print(f"[fetch_youtube] ✗ source {source_id} no transcript: {exc}")

    except Exception as exc:
        _mark_failed(source_id, str(exc))
        print(f"[fetch_youtube] ✗ source {source_id} failed: {exc}")


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
