"""
Controlled 4-condition ablation (bullet 2, V3 failure-trace follow-up).

scripts/trace_adverse_failures.py found two distinct failure modes:
  - "fusion dilution": a strong individual signal (e.g. adv-dense rank 2)
    gets buried by 6-way equal-weight RRF because the other 5 rankings
    don't find the case at all.
  - "reranking capacity": a case makes the candidate pool but the fixed
    min_adverse=2 promotion quota is already filled by other adverse-
    labeled cases ranked higher in the pool.

This tests one concrete fix per failure mode, isolated and combined:

  1. current      : today's 6-way equal-weight RRF pool, min_adverse=2
  2. fusion_fix    : RESERVE_N reserved pool slots from the adverse-query's
                     own dense/BM25 top ranks, backfilled by the normal
                     fused ranking; min_adverse=2
  3. quota_fix     : today's pool; min_adverse=ceil(0.4*k) instead of a
                     fixed 2
  4. both          : fusion_fix pool + quota_fix min_adverse

All four conditions reuse the SAME per-query query rewrites, rankings, and
stance classifications. As of this version, those LLM outputs are also
PERSISTED across separate script runs via app.rag.eval_cache
(data/eval_cache/llm_outputs.json) — so re-running this script to test a
different algorithm tweak (pool construction, promotion quota, ...) makes
ZERO new LLM calls for any query/case combination already seen before, and
only pays for genuinely new (query, case_id) pairs. This removes LLM
non-determinism as a confound when comparing two runs, though it does NOT
prove a single frozen draw is representative (see app/rag/eval_cache.py).

Usage:
    venv/bin/python -m scripts.run_ablation
"""

import math

from app.db.connection import get_connection
from app.rag.balance import classify_stances, promote_adverse
from app.rag.eval_cache import get_or_create_stances, get_or_create_variants, load_cache
from app.rag.eval_cache import stats as cache_stats
from app.rag.retriever import (
    _bm25_ranking,
    _dense_ranking,
    _fetch_cases_by_id,
    _reciprocal_rank_fusion,
)
from app.rag.stance_retrieval import generate_query_variants

POOL_SIZE = 20
RESERVE_N = 5  # per adverse-query signal (adv-dense, adv-bm25), for fusion_fix
K_VALUES = [5, 10]

CONDITIONS = {
    "1_current":    ("pool_current", "stances_current", lambda k: 2),
    "2_fusion_fix": ("pool_fixed",   "stances_fixed",   lambda k: 2),
    "3_quota_fix":  ("pool_current", "stances_current", lambda k: math.ceil(0.4 * k)),
    "4_both":       ("pool_fixed",   "stances_fixed",   lambda k: math.ceil(0.4 * k)),
}


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


def recall_at_k(ids, ground_truth):
    if not ground_truth:
        return None
    return len(set(ids) & ground_truth) / len(ground_truth)


def avg(values):
    return sum(values) / len(values) if values else 0.0


def build_pool(fused_ids, meta):
    return [
        {
            "case_id": cid,
            "case_name": meta[cid]["case_name"],
            "citation": meta[cid]["citation"],
            "score": 0.0,
            "case_text": meta[cid]["case_text"],
        }
        for cid in fused_ids[:POOL_SIZE] if cid in meta
    ]


def main():
    queries = load_eval_queries()
    n_with_adverse = sum(1 for q in queries if q["adverse"])
    print(f"Loaded {len(queries)} eval queries ({n_with_adverse} with adverse cases)\n")

    cache = load_cache()
    per_query = {}
    for i, q in enumerate(queries, 1):
        query_text = q["query"]
        qid = q["eval_query_id"]
        variants = get_or_create_variants(cache, qid, query_text, generate_query_variants)

        rankings = {name: {"dense": _dense_ranking(v), "bm25": _bm25_ranking(v)}
                    for name, v in variants.items()}

        all_rankings = [r for v in rankings.values() for r in v.values()]
        fused_current_ids = [cid for cid, _ in _reciprocal_rank_fusion(all_rankings)]

        # fusion_fix: reserve top RESERVE_N from adv-dense and adv-bm25,
        # backfill the rest of the pool from the normal fused ranking
        adv_dense, adv_bm25 = rankings["adverse"]["dense"], rankings["adverse"]["bm25"]
        reserved = []
        for cid in adv_dense[:RESERVE_N] + adv_bm25[:RESERVE_N]:
            if cid not in reserved:
                reserved.append(cid)
        backfill = [cid for cid in fused_current_ids if cid not in reserved]
        fused_fixed_ids = (reserved + backfill)[:POOL_SIZE]

        needed_ids = set(fused_current_ids[:POOL_SIZE]) | set(fused_fixed_ids)
        meta = _fetch_cases_by_id(list(needed_ids))

        pool_current = build_pool(fused_current_ids, meta)
        pool_fixed = build_pool(fused_fixed_ids, meta)

        per_query[qid] = {
            "pool_current": pool_current,
            "pool_fixed": pool_fixed,
            "stances_current": get_or_create_stances(cache, qid, query_text, pool_current, classify_stances)
                if pool_current else {},
            "stances_fixed": get_or_create_stances(cache, qid, query_text, pool_fixed, classify_stances)
                if pool_fixed else {},
        }
        print(f"  processed query {i}/{len(queries)}: {query_text[:70]!r}")

    print(
        f"\nLLM cache stats: variant calls={cache_stats['variant_calls']} "
        f"(hits={cache_stats['variant_hits']}), stance calls={cache_stats['stance_calls']} "
        f"(case-level cache hits={cache_stats['stance_case_hits']})"
    )

    # ---- Candidate Adverse Recall@20 for both pool constructions ----
    print(f"\n=== Candidate Adverse Recall@{POOL_SIZE} ===")
    for name, key in [("current pool", "pool_current"), ("fusion_fix pool", "pool_fixed")]:
        recalls = []
        for q in queries:
            if not q["adverse"]:
                continue
            ids = [c["case_id"] for c in per_query[q["eval_query_id"]][key]]
            recalls.append(recall_at_k(ids, q["adverse"]))
        print(f"  {name:16s}: {avg(recalls):6.1%}  (n={len(recalls)})")

    # ---- Final top-k comparison across the 4 conditions ----
    print("\n=== Final top-k relevant/adverse recall (4-condition ablation) ===")
    for k in K_VALUES:
        print(f"k={k}:")
        for cond_name, (pool_key, stance_key, min_adv_fn) in CONDITIONS.items():
            min_adverse = min_adv_fn(k)
            rel, adv = [], []
            for q in queries:
                info = per_query[q["eval_query_id"]]
                pool, stances = info[pool_key], info[stance_key]
                final = promote_adverse(pool, stances, k, min_adverse=min_adverse) if pool else []
                ids = [c["case_id"] for c in final]
                r, a = recall_at_k(ids, q["relevant"]), recall_at_k(ids, q["adverse"])
                if r is not None:
                    rel.append(r)
                if a is not None:
                    adv.append(a)
            print(f"  [{cond_name:14s} min_adverse={min_adverse}] "
                  f"relevant: {avg(rel):6.1%}  adverse: {avg(adv):6.1%}  (n={len(adv)})")

    # ---- Per-case trace across the 4 conditions (k=10) ----
    print("\n=== Per-case trace at k=10 (gold adverse cases only; rank in final top-10, or '-') ===")
    header = f"{'q':>3}  {'gold case':<20}" + "".join(f"  {c:>14}" for c in CONDITIONS)
    print(header)
    for q in queries:
        if not q["adverse"]:
            continue
        info = per_query[q["eval_query_id"]]
        for case_id in q["adverse"]:
            row = f"{q['eval_query_id']:>3}  {case_id:<20}"
            for cond_name, (pool_key, stance_key, min_adv_fn) in CONDITIONS.items():
                pool, stances = info[pool_key], info[stance_key]
                min_adverse = min_adv_fn(10)
                final = promote_adverse(pool, stances, 10, min_adverse=min_adverse) if pool else []
                final_ids = [c["case_id"] for c in final]
                rank = final_ids.index(case_id) + 1 if case_id in final_ids else None
                row += f"  {('#' + str(rank)) if rank else '-':>14}"
            print(row)


if __name__ == "__main__":
    main()
