"""
RAG evaluation harness (bullet 2) — the three-stage progression:

  V1  dense     app.rag.retriever.retrieve              — pure embedding similarity (baseline)
  V2  hybrid    app.rag.retriever.retrieve_hybrid        — dense + BM25 via Reciprocal Rank Fusion
  V2' balanced  app.rag.balance.retrieve_balanced        — hybrid pool + stance-classification promotion
  V3  stance_aware app.rag.stance_retrieval.retrieve_stance_aware
                                                          — {original, supporting, adverse}-query
                                                            dense+BM25 fusion + stance promotion

Reports two distinct things, deliberately kept separate:

  - Candidate Adverse Recall@20: does the gold adverse case even enter the
    top-20 candidate pool? (diagnoses the RETRIEVAL/candidate-generation
    stage alone, before any re-ranking)
  - Final top-k relevant/adverse recall: after whatever re-ranking a
    strategy applies (diagnoses the full pipeline)

balanced/stance_aware call an LLM (gpt-5-nano) per query — see
app/rag/balance.py and app/rag/stance_retrieval.py for the real per-call
cost. Stance classification and query-variant generation are each computed
ONCE per query and reused across both k=5 and k=10 to avoid doubling the
LLM-call cost for no reason.

Usage:
    venv/bin/python -m scripts.run_rag_eval
"""

import logging

from app.db.connection import get_connection
from app.rag.balance import classify_stances, promote_adverse
from app.rag.retriever import retrieve, retrieve_hybrid
from app.rag.stance_retrieval import retrieve_stance_aware_pool

logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

K_VALUES = [5, 10]
POOL_SIZE = 20


def load_eval_queries():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT eval_query_id, query, relevant_case_ids, adverse_case_ids "
                "FROM eval_queries ORDER BY eval_query_id"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"eval_query_id": r[0], "query": r[1], "relevant": set(r[2]), "adverse": set(r[3])}
        for r in rows
    ]


def recall_at_k(retrieved_ids, ground_truth):
    if not ground_truth:
        return None
    return len(set(retrieved_ids) & ground_truth) / len(ground_truth)


def avg(values):
    return sum(values) / len(values) if values else 0.0


def main():
    queries = load_eval_queries()
    n_with_adverse = sum(1 for q in queries if q["adverse"])
    print(f"Loaded {len(queries)} eval queries ({n_with_adverse} with adverse cases)\n")

    # ---- Precompute per-query artifacts ONCE (pools + stance labels) ----
    per_query = {}
    for i, q in enumerate(queries, 1):
        query_text = q["query"]
        dense_pool = retrieve(query_text, k=POOL_SIZE)
        hybrid_pool = retrieve_hybrid(query_text, k=POOL_SIZE)
        hybrid_stances = classify_stances(query_text, hybrid_pool)
        stance_pool = retrieve_stance_aware_pool(query_text, pool_size=POOL_SIZE)
        stance_stances = classify_stances(query_text, stance_pool)
        per_query[q["eval_query_id"]] = {
            "dense_pool": dense_pool,
            "hybrid_pool": hybrid_pool,
            "hybrid_stances": hybrid_stances,
            "stance_pool": stance_pool,
            "stance_stances": stance_stances,
        }
        print(f"  processed query {i}/{len(queries)}: {query_text[:70]!r}")

    # ---- Candidate Adverse Recall@20 (retrieval stage alone) ----
    print(f"\n=== Candidate Adverse Recall@{POOL_SIZE} (pool coverage, before any re-ranking) ===")
    for name, pool_key in [("dense", "dense_pool"), ("hybrid", "hybrid_pool"), ("stance_aware", "stance_pool")]:
        recalls = []
        for q in queries:
            if not q["adverse"]:
                continue
            ids = [c["case_id"] for c in per_query[q["eval_query_id"]][pool_key]]
            recalls.append(recall_at_k(ids, q["adverse"]))
        print(f"  {name:12s}: {avg(recalls):6.1%}  (n={len(recalls)} queries with adverse cases)")

    # ---- Final top-k comparison (after re-ranking, where applicable) ----
    print("\n=== Final top-k relevant/adverse recall ===")
    for k in K_VALUES:
        by_strategy = {name: {"rel": [], "adv": []} for name in ("dense", "hybrid", "balanced", "stance_aware")}

        for q in queries:
            info = per_query[q["eval_query_id"]]
            candidates = {
                "dense": info["dense_pool"][:k],
                "hybrid": info["hybrid_pool"][:k],
                "balanced": promote_adverse(info["hybrid_pool"], info["hybrid_stances"], k),
                "stance_aware": promote_adverse(info["stance_pool"], info["stance_stances"], k),
            }
            for name, cases in candidates.items():
                ids = [c["case_id"] for c in cases]
                r = recall_at_k(ids, q["relevant"])
                a = recall_at_k(ids, q["adverse"])
                if r is not None:
                    by_strategy[name]["rel"].append(r)
                if a is not None:
                    by_strategy[name]["adv"].append(a)

        print(f"k={k}:")
        for name, vals in by_strategy.items():
            print(
                f"  [{name:12s}] relevant: {avg(vals['rel']):6.1%}  "
                f"adverse: {avg(vals['adv']):6.1%}  (n={len(vals['adv'])})"
            )


if __name__ == "__main__":
    main()
