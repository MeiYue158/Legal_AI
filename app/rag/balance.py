"""
Evidence balancing (bullet 2): given a query, hybrid-retrieve a larger
candidate pool, classify each candidate's stance toward the position
implied by the query, then re-rank so the final top-k always surfaces some
adverse-stance cases instead of letting a pure-relevance ranking bury them.

This is the mechanism behind "reduce one-sided citation bias" / raise
adverse-precedent recall: stance classification happens at query time by an
LLM reading the actual case text, and must NOT see eval_queries' gold
adverse_case_ids — using the gold labels here would leak ground truth into
the algorithm the eval is supposed to be testing.
"""

from typing import List, Literal, Optional

from openai import OpenAI
from pydantic import BaseModel

from app.rag.retriever import RetrievedCase, retrieve_hybrid

STANCE_MODEL = "gpt-5-nano"
MAX_CASE_CHARS = 3000

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


class _StanceLabel(BaseModel):
    case_id: str
    stance: Literal["favorable", "adverse", "unclear"]


class _StanceLabels(BaseModel):
    labels: List[_StanceLabel]


def classify_stances(query: str, cases: List[RetrievedCase]) -> dict:
    """Ask an LLM whether each case's holding supports ('favorable') or
    undermines ('adverse') the position implied by `query`, based only on
    the case text. Returns {case_id: stance}."""
    if not cases:
        return {}

    client = _get_client()
    context = "\n\n".join(
        f"[case_id: {c['case_id']}] {c['case_name']}\n{c['case_text'][:MAX_CASE_CHARS]}"
        for c in cases
    )
    system = (
        "A user asked a legal question phrased to imply a specific position "
        "(e.g. 'can X do Y?' implies the position 'yes, X can do Y'). For "
        "each case below, decide whether its holding is 'favorable' (supports "
        "that position), 'adverse' (its holding actually cuts the other way), "
        "or 'unclear' (doesn't clearly resolve the question either way). "
        "Base this strictly on what the case text says, not on the case name."
    )
    user = f"Question: {query}\n\nCases:\n{context}"

    completion = client.chat.completions.parse(
        model=STANCE_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=_StanceLabels,
    )
    parsed = completion.choices[0].message.parsed
    return {label.case_id: label.stance for label in parsed.labels}


def promote_adverse(
    pool: List[RetrievedCase],
    stances: dict,
    k: int,
    min_adverse: int = 2,
) -> List[RetrievedCase]:
    """
    Given a candidate pool (in whatever rank order it was retrieved) and a
    {case_id: stance} map already computed for it, build a top-k that
    includes up to `min_adverse` adverse-stance cases — promoted even if
    their rank in the pool is lower — backfilled by pool rank with the rest.

    Split out from retrieve_balanced so callers who need the same pool/
    stances at multiple k (e.g. an eval harness comparing k=5 and k=10)
    only pay for one classify_stances call.
    """
    pool_by_id = {c["case_id"]: c for c in pool}

    # pool is already in rank order, so these preserve relative rank
    adverse_ids = [c["case_id"] for c in pool if stances.get(c["case_id"]) == "adverse"]
    other_ids = [c["case_id"] for c in pool if stances.get(c["case_id"]) != "adverse"]

    selected: List[str] = adverse_ids[:min_adverse]
    remaining = k - len(selected)
    if remaining > 0:
        selected += other_ids[:remaining]
    remaining = k - len(selected)
    if remaining > 0:
        leftover = [cid for cid in adverse_ids[min_adverse:] if cid not in selected]
        selected += leftover[:remaining]

    return [pool_by_id[cid] for cid in selected[:k]]


def retrieve_balanced(
    query: str,
    k: int = 5,
    pool_size: int = 20,
    min_adverse: int = 2,
) -> List[RetrievedCase]:
    """Hybrid-retrieve a candidate pool, classify each candidate's stance,
    then promote_adverse() into the final top-k."""
    pool = retrieve_hybrid(query, k=max(pool_size, k))
    if not pool:
        return []
    stances = classify_stances(query, pool)
    return promote_adverse(pool, stances, k, min_adverse)
