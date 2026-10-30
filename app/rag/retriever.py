"""
Minimal retrieval layer over the corpus_cases FAISS index built by
scripts/build_retrieval_index.py.

Deliberately simple (flat cosine index, ~hundreds of cases) — per the
project's own priority table, retrieval architecture is not where the
engineering effort should go; the citation-highlight UI (Phase 2) is.
"""

import json
import os
import re
from functools import lru_cache
from typing import List, Tuple, TypedDict

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.db.connection import get_connection

# Evidence highlighting lives in app.rag.verify, which stays free of FAISS
# and psycopg2 so the MCP server can use it on arbitrary documents. These
# are re-exported here because callers (app.api.main, app.pages.case_research)
# have always imported them from this module.
from app.rag.verify import (  # noqa: F401  (re-exported for callers)
    MODEL_NAME,
    find_evidence_span,
    highlight_evidence_html,
    load_model as _load_model,
)

INDEX_DIR = os.path.join("data", "index")
INDEX_PATH = os.path.join(INDEX_DIR, "cap_cases.faiss")
IDS_PATH = os.path.join(INDEX_DIR, "cap_case_ids.json")


class RetrievedCase(TypedDict):
    case_id: str
    case_name: str
    citation: str
    score: float
    case_text: str


@lru_cache(maxsize=1)
def _load_index():
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(
            f"No index at {INDEX_PATH} — run scripts/build_retrieval_index.py first"
        )
    index = faiss.read_index(INDEX_PATH)
    with open(IDS_PATH) as f:
        case_ids = json.load(f)
    return index, case_ids


def _fetch_cases_by_id(case_ids: List[str]) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT case_id, case_name, citation, case_text FROM corpus_cases "
                "WHERE case_id = ANY(%s)",
                (case_ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return {r[0]: {"case_name": r[1], "citation": r[2], "case_text": r[3]} for r in rows}


def retrieve(query: str, k: int = 5) -> List[RetrievedCase]:
    """Return the top-k most similar corpus cases for a free-text query."""
    index, case_ids = _load_index()
    model = _load_model()

    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.asarray(query_vec, dtype="float32")

    scores, indices = index.search(query_vec, k)
    hits = [
        (case_ids[i], float(s))
        for s, i in zip(scores[0], indices[0])
        if i != -1
    ]

    meta = _fetch_cases_by_id([case_id for case_id, _ in hits])
    results: List[RetrievedCase] = []
    for case_id, score in hits:
        m = meta.get(case_id)
        if not m:
            continue
        results.append({
            "case_id": case_id,
            "case_name": m["case_name"],
            "citation": m["citation"],
            "score": score,
            "case_text": m["case_text"],
        })
    return results


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


@lru_cache(maxsize=1)
def _load_bm25_corpus():
    """Load every corpus case and build a BM25 index over case_text."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT case_id, case_text FROM corpus_cases ORDER BY case_id")
            rows = cur.fetchall()
    finally:
        conn.close()
    case_ids = [r[0] for r in rows]
    bm25 = BM25Okapi([_tokenize(r[1]) for r in rows])
    return bm25, case_ids


def _dense_ranking(query: str) -> List[str]:
    """Full corpus ranking by dense similarity, best case_id first."""
    index, case_ids = _load_index()
    model = _load_model()
    query_vec = np.asarray(model.encode([query], normalize_embeddings=True), dtype="float32")
    _, indices = index.search(query_vec, index.ntotal)
    return [case_ids[i] for i in indices[0] if i != -1]


def _bm25_ranking(query: str) -> List[str]:
    """Full corpus ranking by BM25 lexical score, best case_id first."""
    bm25, case_ids = _load_bm25_corpus()
    scores = bm25.get_scores(_tokenize(query))
    return [case_ids[i] for i in np.argsort(scores)[::-1]]


def _reciprocal_rank_fusion(
    rankings: List[List[str]], k_constant: int = 60
) -> List[Tuple[str, float]]:
    """Combine several best-first case_id rankings via Reciprocal Rank
    Fusion: score(doc) = sum(1 / (k_constant + rank)) across rankings."""
    scores: dict = {}
    for ranking in rankings:
        for rank, case_id in enumerate(ranking):
            scores[case_id] = scores.get(case_id, 0.0) + 1.0 / (k_constant + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def retrieve_hybrid(query: str, k: int = 5) -> List[RetrievedCase]:
    """
    Like retrieve(), but fuses dense (embedding) and BM25 (lexical) rankings
    via Reciprocal Rank Fusion instead of dense similarity alone.

    Motivation: dense-only retrieval underrepresents cases whose holding
    goes against the query's framing, partly because an opinion that denies
    a claim tends to use different vocabulary than the claim's own framing
    (e.g. "denied", "barred", "no cause of action") — BM25 keyword overlap
    on statute cites / procedural terms surfaces some of these that
    embedding similarity alone ranks low.
    """
    fused = _reciprocal_rank_fusion([_dense_ranking(query), _bm25_ranking(query)])
    top = fused[:k]

    meta = _fetch_cases_by_id([case_id for case_id, _ in top])
    results: List[RetrievedCase] = []
    for case_id, score in top:
        m = meta.get(case_id)
        if not m:
            continue
        results.append({
            "case_id": case_id,
            "case_name": m["case_name"],
            "citation": m["citation"],
            "score": score,
            "case_text": m["case_text"],
        })
    return results
