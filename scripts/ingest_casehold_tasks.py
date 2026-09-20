"""
Phase 1 — pull a small pilot batch of LexGLUE CaseHOLD examples and load them
into the tasks table as citation-verification items.

CaseHOLD structure (see huggingface.co/datasets/lex_glue, config case_hold):
    context: a passage from a citing opinion with a <HOLDING> placeholder
              where a citation to another case's holding used to be
    endings: 5 candidate holding statements, exactly one correct
    label:   index (0-4) of the correct ending

This maps directly onto the experiment's verification-accuracy mechanism
without needing to cross-reference full source documents:
  - correct_index = the real holding (ground truth for "does this citation
    support the claim?")
  - the 4 wrong endings are ready-made distractors for is_planted_error
    items (show a wrong holding as "the AI's claim" to measure overreliance)

PILOT run: only N_PILOT rows, half straight (shown_index = correct_index)
and half rigged (shown_index = a wrong ending) — small on purpose, per
instruction to try a small sample before scaling up.

Usage:
    venv/bin/python -m scripts.ingest_casehold_tasks
"""

import logging
import random

from datasets import load_dataset

from app.db.connection import get_connection
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

N_PILOT = 30  # small pilot batch — scale up only after review
random.seed(42)


def build_task_rows(n: int):
    ds = load_dataset("lex_glue", "case_hold", split=f"test[:{n}]")
    rows = []
    for i, ex in enumerate(ds):
        correct_index = ex["label"]
        candidates = ex["endings"]

        # Alternate: even i -> show the correct holding (control/treatment
        # item for a case where the AI's claim is right); odd i -> rig it
        # with a wrong candidate (overreliance measurement item).
        is_planted_error = (i % 2 == 1)
        if is_planted_error:
            wrong_choices = [j for j in range(len(candidates)) if j != correct_index]
            shown_index = random.choice(wrong_choices)
        else:
            shown_index = correct_index

        rows.append({
            "source": "casehold",
            "context": ex["context"],
            "candidate_citations": candidates,
            "correct_index": correct_index,
            "shown_index": shown_index,
            "is_planted_error": is_planted_error,
        })
    return rows


def main():
    rows = build_task_rows(N_PILOT)

    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO tasks
                        (source, context, candidate_citations, correct_index,
                         shown_index, is_planted_error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        r["source"], r["context"], json.dumps(r["candidate_citations"]),
                        r["correct_index"], r["shown_index"], r["is_planted_error"],
                    ),
                )
                inserted += 1
        conn.commit()
    finally:
        conn.close()

    n_planted = sum(1 for r in rows if r["is_planted_error"])
    print(f"✅ Inserted {inserted} pilot tasks from CaseHOLD "
          f"({n_planted} planted-error / {inserted - n_planted} correct)")


if __name__ == "__main__":
    main()
