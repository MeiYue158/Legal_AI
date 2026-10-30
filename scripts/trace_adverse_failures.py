"""
Failure-tracing diagnostic for the 7 eval queries with adverse ground truth.

For each gold adverse case, traces its rank at every stage of the V3
pipeline — dense, BM25, adverse-reformulated-query dense/BM25, the 6-way
RRF fusion, and stance-based re-ranking — to see exactly which stage drops
it before it can reach the final top-10, instead of guessing from the
aggregate recall numbers in scripts/run_rag_eval.py alone.

No new retrieval algorithm here — this is purely instrumentation over the
existing app.rag.retriever / app.rag.balance / app.rag.stance_retrieval
internals.

Usage:
    venv/bin/python -m scripts.trace_adverse_failures
"""

from app.db.connection import get_connection
from app.rag.balance import classify_stances, promote_adverse
from app.rag.retriever import (
    _bm25_ranking,
    _dense_ranking,
    _fetch_cases_by_id,
    _reciprocal_rank_fusion,
)
from app.rag.stance_retrieval import generate_query_variants

POOL_SIZE = 20  # matches the pool size the real retrieve_* strategies use
RANK_DISPLAY_CUTOFF = 20


def load_adverse_queries():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT eval_query_id, query, adverse_case_ids FROM eval_queries "
                "ORDER BY eval_query_id"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"eval_query_id": r[0], "query": r[1], "adverse": r[2]}
        for r in rows if r[2]
    ]


def rank_of(case_id, ranking):
    """1-indexed rank of case_id in a best-first ranking list, or None."""
    try:
        return ranking.index(case_id) + 1
    except ValueError:
        return None


def fmt_rank(rank):
    if rank is None:
        return "-"
    if rank > RANK_DISPLAY_CUTOFF:
        return f">{RANK_DISPLAY_CUTOFF}"
    return str(rank)


def main():
    queries = load_adverse_queries()
    print(f"Tracing {len(queries)} queries with adverse ground truth\n")

    header = (
        f"{'q':>3}  {'gold case':<20} {'dense':>6} {'bm25':>6} "
        f"{'adv-dns':>8} {'adv-bm25':>9} {'rrf':>5} {'rerank':>7} {'top10?':>7}  loss stage"
    )
    print(header)
    print("-" * len(header))

    for q in queries:
        variants = generate_query_variants(q["query"])

        dense_full = _dense_ranking(q["query"])
        bm25_full = _bm25_ranking(q["query"])
        adv_dense_full = _dense_ranking(variants["adverse"])
        adv_bm25_full = _bm25_ranking(variants["adverse"])

        # same 6-way fusion app.rag.stance_retrieval.retrieve_stance_aware_pool uses
        rankings = []
        for v in variants.values():
            rankings.append(_dense_ranking(v))
            rankings.append(_bm25_ranking(v))
        fused = _reciprocal_rank_fusion(rankings)
        fused_ids = [case_id for case_id, _ in fused]

        pool_ids = fused_ids[:POOL_SIZE]
        pool_meta = _fetch_cases_by_id(pool_ids)
        pool_cases = [
            {
                "case_id": cid,
                "case_name": pool_meta[cid]["case_name"],
                "citation": pool_meta[cid]["citation"],
                "score": 0.0,
                "case_text": pool_meta[cid]["case_text"],
            }
            for cid in pool_ids if cid in pool_meta
        ]
        stances = classify_stances(q["query"], pool_cases) if pool_cases else {}
        full_reranked = (
            [c["case_id"] for c in promote_adverse(pool_cases, stances, k=len(pool_cases))]
            if pool_cases else []
        )

        for case_id in q["adverse"]:
            dense_rank = rank_of(case_id, dense_full)
            bm25_rank = rank_of(case_id, bm25_full)
            adv_dense_rank = rank_of(case_id, adv_dense_full)
            adv_bm25_rank = rank_of(case_id, adv_bm25_full)
            rrf_rank = rank_of(case_id, fused_ids)
            rerank_rank = rank_of(case_id, full_reranked)  # None => never reached the pool

            top10 = rerank_rank is not None and rerank_rank <= 10

            if top10:
                stage = "-"
            elif rrf_rank is None or rrf_rank > POOL_SIZE:
                individual_hits = [
                    r for r in (dense_rank, bm25_rank, adv_dense_rank, adv_bm25_rank)
                    if r is not None and r <= POOL_SIZE
                ]
                stage = "retrieval (no signal found it)" if not individual_hits else \
                    "fusion (found by one signal, diluted out of pool)"
            else:
                stage = "reranking (in pool, not promoted to top10)"

            print(
                f"{q['eval_query_id']:>3}  {case_id:<20} "
                f"{fmt_rank(dense_rank):>6} {fmt_rank(bm25_rank):>6} "
                f"{fmt_rank(adv_dense_rank):>8} {fmt_rank(adv_bm25_rank):>9} "
                f"{fmt_rank(rrf_rank):>5} {fmt_rank(rerank_rank):>7} "
                f"{'YES' if top10 else 'NO':>7}  {stage}"
            )


if __name__ == "__main__":
    main()
