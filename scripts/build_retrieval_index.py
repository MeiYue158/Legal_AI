"""
Phase 1 — embed corpus_cases with a pretrained sentence-transformer
(all-MiniLM-L6-v2, already a dependency of this repo — inference only, no
training) and build a small FAISS index for retrieval.

Writes:
    data/index/cap_cases.faiss        — the FAISS index (cosine via inner
                                          product on normalized vectors)
    data/index/cap_case_ids.json      — row i in the index -> case_id in db
Also back-fills corpus_cases.embedding_row so the db and index stay in sync.

Usage:
    venv/bin/python -m scripts.build_retrieval_index
"""

import json
import logging
import os

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.db.connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEX_DIR = os.path.join("data", "index")
INDEX_PATH = os.path.join(INDEX_DIR, "cap_cases.faiss")
IDS_PATH = os.path.join(INDEX_DIR, "cap_case_ids.json")
MODEL_NAME = "all-MiniLM-L6-v2"


def fetch_cases():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT case_id, case_text FROM corpus_cases ORDER BY case_id")
            return cur.fetchall()
    finally:
        conn.close()


def main():
    os.makedirs(INDEX_DIR, exist_ok=True)

    rows = fetch_cases()
    if not rows:
        print("No cases in corpus_cases — run scripts/ingest_cap_corpus.py first.")
        return

    case_ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    logger.info(f"Embedding {len(texts)} cases with {MODEL_NAME} (pretrained, inference only)")

    model = SentenceTransformer(MODEL_NAME)
    # Truncate very long opinions to keep embedding fast/representative of
    # the opening holding-relevant material.
    embeddings = model.encode(
        [t[:2000] for t in texts],
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True,  # so inner product == cosine similarity
    )
    embeddings = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, INDEX_PATH)

    with open(IDS_PATH, "w") as f:
        json.dump(case_ids, f)

    # Back-fill embedding_row so corpus_cases <-> index stay addressable
    # from the db side too.
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for row_idx, case_id in enumerate(case_ids):
                cur.execute(
                    "UPDATE corpus_cases SET embedding_row = %s WHERE case_id = %s",
                    (row_idx, case_id),
                )
        conn.commit()
    finally:
        conn.close()

    print(f"✅ Built FAISS index with {index.ntotal} vectors -> {INDEX_PATH}")


if __name__ == "__main__":
    main()
