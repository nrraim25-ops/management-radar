# NOTES

## Decisions
- Stack: Streamlit + SQLite + Gemini (google-genai SDK) — default per spec, fastest path to a working system.
- Embeddings: sentence-transformers `all-MiniLM-L6-v2` — small, fast, free, runs locally, no quota issues.
- PDF parsing: pdfplumber — table-aware, page-level extraction; avoids table rows mangling into prose.
- YouTube: youtube-transcript-api — no video download, just captions + timestamps; cleanest approach.
- Chunking: 40-second windows for YouTube (between 30–45s spec range); page-level for PDFs.
- Tagging: one Gemini call per source, structured JSON output with retry-on-parse-fail.
- Rate limiting: 4s sleep between tagging calls + exponential backoff (20s → 40s) on 429; same pattern in RAG pipeline.
- DB: `source_tags` is a separate table from `sources` — derived AI output must not pollute fetched ground truth; allows re-running tagging independently.
- `.env` excluded from git from commit #1; `db/management_radar.db` intentionally committed per spec §7.

## Prompts that mattered
- (will be populated as build progresses)

## Corners cut
- (will be populated if anything is skipped under time pressure)

## Rate-limit log
- (will be populated if 429s are hit during pipeline run)
