"""
V3 — stance-aware candidate generation (bullet 2).

Diagnosis from the V1/V2 eval: hybrid retrieval (dense+BM25 via RRF)
substantially raised overall relevant recall, but did NOT reliably raise
adverse-precedent recall. Digging in with "Candidate Adverse Recall@20"
(see scripts/run_rag_eval.py) showed why — for several queries the gold
adverse case never entered the top-20 candidate pool at all, from either
retriever. app.rag.balance's re-ranking can only promote cases that are
already in the pool; it cannot fix a pool that never fetched the right
document in the first place.

V3 fixes the candidate-GENERATION stage: instead of retrieving with only
the original query, it also retrieves with an LLM-generated "adverse"
reformulation (phrased to surface cases where a court denied/rejected/
limited the position the original query implies), fuses dense+BM25 rankings
across {original, supporting, adverse} query variants into one enlarged
pool via RRF, then applies the same stance-classification + promotion
re-ranking as V2's retrieve_balanced.
"""

from typing import Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel

from app.rag.balance import classify_stances, promote_adverse
from app.rag.retriever import (
    RetrievedCase,
    _bm25_ranking,
    _dense_ranking,
    _fetch_cases_by_id,
    _reciprocal_rank_fusion,
)

EXPANSION_MODEL = "gpt-5-nano"

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


class _QueryVariants(BaseModel):
    supporting_query: str
    adverse_query: str


def generate_query_variants(query: str) -> Dict[str, str]:
    """
    Rewrite `query` into two short search-style reformulations:
      - supporting: phrased to find cases whose holding supports the
        position the original query implies
      - adverse: phrased to find cases where a court denied, rejected, or
        limited that position (outcome language: "denied", "barred",
        "refused", "insufficient", etc.)

    Returns {"original": query, "supporting": ..., "adverse": ...}.
    """
    client = _get_client()
    system = (
        "You rewrite legal questions into search queries for a case-law "
        "retrieval system. Given a legal question that implies a specific "
        "position, write two short search queries: "
        "'supporting_query' — phrased to find cases whose holding supports "
        "that position; "
        "'adverse_query' — phrased to find cases where a court denied, "
        "rejected, or limited that position (use outcome language like "
        "'denied', 'barred', 'refused', 'insufficient' as appropriate). "
        "Keep both short and search-engine-like, not full sentences."
    )
    completion = client.chat.completions.parse(
        model=EXPANSION_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        response_format=_QueryVariants,
    )
    parsed = completion.choices[0].message.parsed
    return {
        "original": query,
        "supporting": parsed.supporting_query,
        "adverse": parsed.adverse_query,
    }


def retrieve_stance_aware_pool(query: str, pool_size: int = 20) -> List[RetrievedCase]:
    """Fuse dense + BM25 rankings across the original query and its
    supporting/adverse reformulations into one enlarged candidate pool."""
    variants = generate_query_variants(query)

    rankings = []
    for variant_query in variants.values():
        rankings.append(_dense_ranking(variant_query))
        rankings.append(_bm25_ranking(variant_query))

    fused = _reciprocal_rank_fusion(rankings)
    top = fused[:pool_size]

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


def retrieve_stance_aware(
    query: str,
    k: int = 5,
    pool_size: int = 20,
    min_adverse: int = 2,
) -> List[RetrievedCase]:
    """V3: stance-aware candidate pool + stance-classification promotion."""
    pool = retrieve_stance_aware_pool(query, pool_size=pool_size)
    if not pool:
        return []
    stances = classify_stances(query, pool)
    return promote_adverse(pool, stances, k, min_adverse)
