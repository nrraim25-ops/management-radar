"""src/tagging.py — LLM-based summarisation and tagging of sources (one call per source)."""

import json
import re
import time
from datetime import datetime, timezone

import google.genai as genai
from google.genai import types

from src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TAG_BACKOFF_SECONDS,
    TAG_MAX_RETRIES,
    TAG_SLEEP_BETWEEN,
    TAGGING_MAX_WORDS,
)
from src.db import get_conn

VALID_TAGS = {"results", "expansion", "management_change", "new_orders", "risks"}

TAGGING_PROMPT_TEMPLATE = """You are a financial analyst assistant. Read the following source text from a company disclosure or interview transcript.

Your task:
1. Write a 2-4 sentence plain-language summary of what this source covers.
2. Select 1-3 tags from this exact list that genuinely apply: results, expansion, management_change, new_orders, risks.
   - Only pick tags that are actually discussed. Do NOT force-fit tags that don't belong.

{truncation_note}

SOURCE TEXT:
---
{source_text}
---

Respond with ONLY valid JSON in exactly this format:
{{"summary": "...", "tags": ["tag1", "tag2"]}}

No explanation, no markdown, no preamble — just the JSON object."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call_gemini_with_backoff(prompt: str) -> dict:
    """Call Gemini with retry-on-429 backoff. Returns parsed JSON dict."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    last_exc = None
    for attempt in range(TAG_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            raw = response.text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)

            return json.loads(raw)

        except Exception as exc:
            err_str = str(exc).lower()
            is_rate_limit = "429" in err_str or "quota" in err_str or "rate" in err_str

            if is_rate_limit:
                sleep_time = TAG_BACKOFF_SECONDS * (attempt + 1)
                print(f"[tagging] 429 rate limit hit, sleeping {sleep_time}s (attempt {attempt+1}/{TAG_MAX_RETRIES})")
                time.sleep(sleep_time)
            else:
                # If parse failed, retry with stricter prompt
                if "json" in err_str or isinstance(exc, (json.JSONDecodeError, ValueError)):
                    print(f"[tagging] JSON parse failed (attempt {attempt+1}), retrying with stricter prompt")
                    prompt = "Respond with ONLY valid JSON, nothing else.\n\n" + prompt
                    time.sleep(2)
                else:
                    raise

            last_exc = exc

    raise last_exc or RuntimeError("Max retries exceeded")


def tag_all_sources() -> None:
    """Tag all sources that don't yet have a source_tags row."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.source_type
            FROM sources s
            WHERE s.fetch_status = 'ok'
              AND NOT EXISTS (SELECT 1 FROM source_tags t WHERE t.source_id = s.id)
            """
        ).fetchall()

    if not rows:
        print("[tagging] all sources already tagged")
        return

    print(f"[tagging] tagging {len(rows)} sources...")

    for i, row in enumerate(rows):
        source_id = row["id"]
        title = row["title"]
        print(f"[tagging] source {source_id}: {title}")

        try:
            # Gather all chunks for this source
            with get_conn() as conn:
                chunks = conn.execute(
                    "SELECT text FROM chunks WHERE source_id=? ORDER BY chunk_index",
                    (source_id,),
                ).fetchall()

            if not chunks:
                print(f"[tagging] WARNING: source {source_id} has no chunks, skipping")
                continue

            full_text = "\n\n".join(c["text"] for c in chunks)
            words = full_text.split()
            truncation_note = ""
            if len(words) > TAGGING_MAX_WORDS:
                full_text = " ".join(words[:TAGGING_MAX_WORDS])
                truncation_note = f"[NOTE: Text was truncated to the first {TAGGING_MAX_WORDS} words for context length.]"

            prompt = TAGGING_PROMPT_TEMPLATE.format(
                source_text=full_text,
                truncation_note=truncation_note,
            )

            result = _call_gemini_with_backoff(prompt)
            summary = str(result.get("summary", "")).strip()
            raw_tags = result.get("tags", [])

            # Validate tags — only keep recognised ones
            valid = [t for t in raw_tags if t in VALID_TAGS]
            tags_str = ",".join(valid) if valid else "results"

            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO source_tags (source_id, summary, tags) VALUES (?,?,?)",
                    (source_id, summary, tags_str),
                )
            print(f"[tagging] ✓ source {source_id} tagged: {valid}")

        except Exception as exc:
            print(f"[tagging] ✗ source {source_id} tagging failed: {exc}")

        # Rate-limit friendly delay between calls (skip after last item)
        if i < len(rows) - 1:
            time.sleep(TAG_SLEEP_BETWEEN)
