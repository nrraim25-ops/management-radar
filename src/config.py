"""src/config.py — environment loading and project-wide settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from repo root (two levels up from this file)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# ── LLM ──────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-3.6-flash"   # current free-tier model, google-genai v2

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = _ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
DB_PATH = _ROOT / "db" / "management_radar.db"
CSV_PATH = DATA_DIR / "disclosure_links.csv"

# Ensure directories exist
PDF_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
(DB_PATH.parent).mkdir(parents=True, exist_ok=True)

# ── Fetch ─────────────────────────────────────────────────────────────────────
FETCH_TIMEOUT: int = 20          # seconds for HTTP requests
PDF_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Chunking ──────────────────────────────────────────────────────────────────
YOUTUBE_CHUNK_SECONDS: int = 40  # group transcript lines into ~40s windows

# ── Embeddings ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
TOP_K: int = 6                   # chunks to retrieve per question

# ── Tagging / LLM calls ───────────────────────────────────────────────────────
TAG_SLEEP_BETWEEN: float = 4.0   # seconds between tagging calls (free tier ~15 RPM)
TAG_BACKOFF_SECONDS: float = 25.0  # sleep on 429 before retry
TAG_MAX_RETRIES: int = 3
TAGGING_MAX_WORDS: int = 8000    # truncate source text before sending to LLM

# ── Security ──────────────────────────────────────────────────────────────────
MAX_QUERY_LENGTH: int = 2000     # cap user input length
SESSION_RATE_LIMIT: int = 20     # max questions per session
