"""
Phase 2 — LLM-assisted DRAFT of the eval_queries table for the Legal RAG
evaluation system (resume bullet 2: "基于 150 条专家标注法律查询构建 Legal
RAG 评估体系").

For each seed legal topic, retrieves a topically-coherent cluster of real
corpus cases via app.rag.retriever.retrieve (free, local, no LLM cost — this
is just embedding similarity), then asks an LLM to actually read the case
texts and label each one relevant/adverse/not-relevant to a natural-language
question about that topic.

IMPORTANT: this is a machine-assisted DRAFT pass, not gold-standard ground
truth. Every row is inserted with source='llm_draft'. A resume-worthy claim
like "adverse-precedent recall 51% -> 76%" needs someone with legal
background to review and correct these labels before they're trustworthy —
this script only gets you from zero to a reviewable starting point cheaply.

Usage:
    venv/bin/python -m scripts.build_eval_queries
"""

import json
import logging
from typing import List, Literal

from openai import OpenAI
from pydantic import BaseModel

from app.db.connection import get_connection
from app.rag.retriever import retrieve

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LABEL_MODEL = "gpt-5-mini"
K_PER_TOPIC = 6
MAX_CASE_CHARS = 4000

# Seed topics drawn from legal issues actually observed in the corpus_cases
# pilot (136 Delaware Chancery opinions, ~1963-1965). Some may retrieve only
# weakly-related cases if the topic is thin in this small corpus — that's
# expected and handled by skipping topics with no relevant hits.
SEED_TOPICS = [
    "fraudulent conveyance to a purchaser for fair consideration without knowledge",
    "demand futility in a derivative shareholder suit",
    "sequestration of a non-resident defendant's property",
    "sale of substantially all corporate assets requiring shareholder approval",
    "breach of fiduciary duty by corporate directors",
    "statute of limitations for a bond obligor's official misconduct",
    "counsel fees awarded in a derivative action",
    "injunction against sale of pledged stock",
    "corporate indenture default and debenture redemption",
    "summary judgment on a stock transfer dispute",
    "partnership property exempt from attachment",
    "collateral estoppel from a prior bankruptcy proceeding",
    "waste of corporate assets through excessive salaries",
    "creditor's claim barred for lack of notice before distribution",
    "receiver's duty to notify creditors before distribution",
    "choice of law in a stock pledge agreement",
    "jurisdiction over foreign corporation directors",
    "unilateral change to a corporate retirement plan",
    "validity of a stockholder's proof of claim",
    "corporate default under a trust indenture triggering a redemption premium",
]


class CaseLabel(BaseModel):
    case_id: str
    relevance: Literal["relevant_favorable", "relevant_adverse", "not_relevant"]
    rationale: str


class QueryLabels(BaseModel):
    query: str
    labels: List[CaseLabel]


def label_cluster(client: OpenAI, seed_topic: str, cases) -> QueryLabels:
    context = "\n\n".join(
        f"[case_id: {c['case_id']}] {c['case_name']} ({c['citation']})\n"
        f"{c['case_text'][:MAX_CASE_CHARS]}"
        for c in cases
    )
    system = (
        "You are helping build a legal-RAG evaluation dataset. Given a legal "
        "topic and a set of real case opinions, write ONE natural-language "
        "legal question a user might ask about this topic, phrased so it "
        "implies a specific position (e.g. 'can a purchaser who paid fair "
        "consideration keep the property despite an earlier fraud?'). Then, "
        "for EVERY case provided, decide: 'relevant_favorable' if the case's "
        "holding supports a 'yes' answer consistent with the position "
        "implied by the question; 'relevant_adverse' if the case is on-topic "
        "but its holding actually cuts the other way (undermines that "
        "position) — an important precedent a one-sided search would miss; "
        "'not_relevant' if the case has nothing meaningful to do with the "
        "question. Base every label strictly on what the case text actually "
        "says, not on the case name or your prior knowledge."
    )
    user = f"Topic: {seed_topic}\n\nCases:\n{context}"

    completion = client.chat.completions.parse(
        model=LABEL_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=QueryLabels,
    )
    return completion.choices[0].message.parsed


def main():
    client = OpenAI()
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for topic in SEED_TOPICS:
                cases = retrieve(topic, k=K_PER_TOPIC)
                if not cases:
                    logger.warning(f"no cases retrieved for topic: {topic}")
                    continue

                result = label_cluster(client, topic, cases)
                relevant = [
                    l.case_id for l in result.labels
                    if l.relevance in ("relevant_favorable", "relevant_adverse")
                ]
                adverse = [l.case_id for l in result.labels if l.relevance == "relevant_adverse"]

                if not relevant:
                    logger.info(f"skipping (no relevant cases found): {topic}")
                    continue

                notes = json.dumps([l.model_dump() for l in result.labels])
                cur.execute(
                    """
                    INSERT INTO eval_queries (query, relevant_case_ids, adverse_case_ids, notes, source)
                    VALUES (%s, %s, %s, %s, 'llm_draft')
                    """,
                    (result.query, json.dumps(relevant), json.dumps(adverse), notes),
                )
                inserted += 1
                logger.info(
                    f"[{inserted}] {result.query!r} -> "
                    f"{len(relevant)} relevant ({len(adverse)} adverse)"
                )
        conn.commit()
    finally:
        conn.close()

    print(
        f"\n✅ Inserted {inserted} draft eval queries (source='llm_draft'). "
        f"These need human legal review before being used to report eval numbers."
    )


if __name__ == "__main__":
    main()
