"""
Persistent cache for LLM outputs used by the RAG eval scripts
(scripts/run_ablation.py, scripts/trace_adverse_failures.py, ...).

Why this exists: query-rewrite generation and stance classification are LLM
calls with real run-to-run non-determinism. When comparing algorithm
changes (different pool-construction rules, different promotion quotas),
that non-determinism is a confound — a difference between two runs might be
the algorithm change, or might just be a different LLM draw for the same
query. Freezing these LLM outputs once and reusing them for every
subsequent algorithm comparison removes that confound for everything
downstream of retrieval (dense/BM25 ranking itself is already
deterministic, so it doesn't need caching).

This does NOT prove results are "stable" — it only guarantees that two
runs which reuse the cache are comparing the same LLM draw. Whether that
one frozen draw is representative of the LLM's behavior in general is a
separate question (would need multiple independent draws, averaged).

Cache file: data/eval_cache/llm_outputs.json, keyed by eval_query_id:
    {
      "<eval_query_id>": {
        "query": "...",
        "variants": {"original": ..., "supporting": ..., "adverse": ...},
        "stances": {"<case_id>": "favorable" | "adverse" | "unclear", ...}
      },
      ...
    }

`stances` accumulates as a UNION across every case_id ever classified for
that query, across every pool-construction variant tried — so an algorithm
change that reuses a subset of previously-seen candidates costs zero new
LLM calls, and only genuinely new candidates trigger a fresh (then cached)
classify_stances call.
"""

import json
import os
from typing import Callable, Dict, List

CACHE_PATH = os.path.join("data", "eval_cache", "llm_outputs.json")

# Simple counters so callers can report how many calls were actually made
# vs served from cache, for a given process run.
stats = {"variant_calls": 0, "variant_hits": 0, "stance_calls": 0, "stance_case_hits": 0}


def load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH) as f:
        return json.load(f)


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _get_entry(cache: dict, eval_query_id, query: str) -> dict:
    key = str(eval_query_id)
    if key not in cache:
        cache[key] = {"query": query, "variants": None, "stances": {}}
    return cache[key]


def get_or_create_variants(
    cache: dict, eval_query_id, query: str, generate_fn: Callable[[str], dict]
) -> dict:
    """Return the cached {original, supporting, adverse} variants for this
    query, generating (and caching) them only on the first call ever."""
    entry = _get_entry(cache, eval_query_id, query)
    if entry["variants"] is None:
        entry["variants"] = generate_fn(query)
        stats["variant_calls"] += 1
        save_cache(cache)
    else:
        stats["variant_hits"] += 1
    return entry["variants"]


def get_or_create_stances(
    cache: dict,
    eval_query_id,
    query: str,
    cases: List[dict],
    classify_fn: Callable[[str, List[dict]], dict],
) -> Dict[str, str]:
    """Return {case_id: stance} for exactly `cases`, classifying (and
    caching) only the case_ids not already classified for this query in a
    prior call — regardless of which pool they came from."""
    entry = _get_entry(cache, eval_query_id, query)
    cached = entry["stances"]

    missing = [c for c in cases if c["case_id"] not in cached]
    if missing:
        new_labels = classify_fn(query, missing)
        cached.update(new_labels)
        stats["stance_calls"] += 1
        save_cache(cache)
    stats["stance_case_hits"] += len(cases) - len(missing)

    return {c["case_id"]: cached[c["case_id"]] for c in cases if c["case_id"] in cached}
