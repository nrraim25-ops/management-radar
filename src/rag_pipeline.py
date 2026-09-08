"""src/rag_pipeline.py — Retrieval-augmented Q&A with grounded, cited answers."""

import json
import re
import time
from datetime import datetime, timezone

import google.generativeai as genai

from src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TAG_BACKOFF_SECONDS,
    TAG_MAX_RETRIES,
)
from src.db import get_conn
from src.embeddings import search
from src.security import build_rag_prompt, sanitize_query


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call_gemini(prompt: str) -> str:
    """Call Gemini with backoff on 429. Returns raw text."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    last_exc = None
    for attempt in range(TAG_MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as exc:
            err_str = str(exc).lower()
            is_rate_limit = "429" in err_str or "quota" in err_str or "rate" in err_str
            if is_rate_limit:
                sleep_time = TAG_BACKOFF_SECONDS * (attempt + 1)
                print(f"[rag] 429 rate limit, sleeping {sleep_time}s")
                time.sleep(sleep_time)
            else:
                raise
            last_exc = exc

    raise last_exc or RuntimeError("Max retries exceeded")


def answer(question: str, company_id: int) -> dict:
    """
    Full RAG pipeline:
    1. Sanitize input
    2. Retrieve top-k chunks for the company
    3. Build grounded prompt with injection defense
    4. Call Gemini, parse structured response
    5. Log to qa_log
    6. Return {answer, cited_source_ids, chunks_used}

    On rate-limit: returns a friendly error message instead of raising.
    """
    question = sanitize_query(question)

    if not question:
        return {
            "answer": "Please enter a valid question.",
            "cited_source_ids": [],
            "chunks_used": [],
            "error": True,
        }

    # Retrieve relevant chunks
    chunks = search(question, company_id)

    if not chunks:
        return {
            "answer": "No indexed content found for this company. Please run the pipeline first.",
            "cited_source_ids": [],
            "chunks_used": [],
            "error": True,
        }

    # Build grounded prompt
    prompt = build_rag_prompt(question, chunks)

    # Call LLM
    try:
        raw = _call_gemini(prompt)
    except Exception as exc:
        err_str = str(exc).lower()
        if "429" in err_str or "quota" in err_str or "rate" in err_str:
            return {
                "answer": "⚠️ The AI service is temporarily rate-limited. Please wait a few seconds and try again.",
                "cited_source_ids": [],
                "chunks_used": chunks,
                "error": True,
            }
        return {
            "answer": f"⚠️ An error occurred while generating the answer: {exc}",
            "cited_source_ids": [],
            "chunks_used": chunks,
            "error": True,
        }

    # Parse structured JSON response
    answer_text, cited_ids = _parse_response(raw)

    # Log to qa_log
    cited_str = ",".join(str(i) for i in cited_ids)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO qa_log (question, answer, cited_source_ids, answered_at) VALUES (?,?,?,?)",
            (question, answer_text, cited_str, _now()),
        )

    return {
        "answer": answer_text,
        "cited_source_ids": cited_ids,
        "chunks_used": chunks,
        "error": False,
    }


def _parse_response(raw: str) -> tuple[str, list[int]]:
    """Parse the structured JSON response from the LLM."""
    # Strip markdown fences if present
    clean = raw
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean.strip())

    try:
        data = json.loads(clean)
        answer_text = str(data.get("answer", raw)).strip()
        raw_ids = data.get("cited_source_ids", [])
        cited_ids = []
        for sid in raw_ids:
            try:
                cited_ids.append(int(sid))
            except (TypeError, ValueError):
                pass
        return answer_text, cited_ids
    except (json.JSONDecodeError, ValueError):
        # Fallback: return raw text with no parsed citations
        return raw, []
