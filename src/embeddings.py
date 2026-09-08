"""src/embeddings.py — Local sentence-transformers embeddings + cosine similarity search."""

import struct
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL, TOP_K
from src.db import get_conn

_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[embeddings] loading model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> np.ndarray:
    """Return a float32 numpy vector for the given text."""
    model = _get_model()
    return model.encode(text, normalize_embeddings=True).astype(np.float32)


def vec_to_blob(vec: np.ndarray) -> bytes:
    """Serialize float32 numpy array to raw bytes for SQLite BLOB storage."""
    return vec.tobytes()


def blob_to_vec(blob: bytes) -> np.ndarray:
    """Deserialize SQLite BLOB back to float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def embed_all_chunks() -> None:
    """Embed all chunks that currently have NULL embeddings."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text FROM chunks WHERE embedding IS NULL"
        ).fetchall()

    if not rows:
        print("[embeddings] all chunks already embedded")
        return

    print(f"[embeddings] embedding {len(rows)} chunks...")
    model = _get_model()

    texts = [row["text"] for row in rows]
    ids = [row["id"] for row in rows]

    # Batch encode for efficiency
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True)

    with get_conn() as conn:
        for chunk_id, vec in zip(ids, vecs):
            blob = vec_to_blob(vec.astype(np.float32))
            conn.execute("UPDATE chunks SET embedding=? WHERE id=?", (blob, chunk_id))

    print(f"[embeddings] ✓ embedded {len(rows)} chunks")


def search(query: str, company_id: int, top_k: int = TOP_K) -> list[dict]:
    """
    Embed query and return top-k most similar chunks for the given company.
    Returns list of dicts with keys: id, source_id, text, locator, chunk_index, score,
    source_title, source_type, published_date.
    """
    q_vec = embed_text(query)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.source_id, c.text, c.locator, c.chunk_index, c.embedding,
                   s.title AS source_title, s.source_type, s.published_date
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
            WHERE s.company_id = ?
              AND c.embedding IS NOT NULL
            """,
            (company_id,),
        ).fetchall()

    if not rows:
        return []

    results = []
    for row in rows:
        vec = blob_to_vec(row["embedding"])
        score = float(np.dot(q_vec, vec))  # cosine sim (both normalized)
        results.append({
            "id": row["id"],
            "source_id": row["source_id"],
            "text": row["text"],
            "locator": row["locator"],
            "chunk_index": row["chunk_index"],
            "score": score,
            "source_title": row["source_title"],
            "source_type": row["source_type"],
            "published_date": row["published_date"],
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
