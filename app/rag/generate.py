"""
Phase 2 — LLM answer generation with self-reported citations ("method B").

The model answers the user's query using only the retrieved cases, and for
each claim quotes the exact passage it relied on. Quotes are then verified
against the source text: an exact (whitespace-tolerant) substring match
locates the real span. When the model paraphrases instead of quoting
verbatim — a known LLM failure mode — we fall back to the similarity
heuristic in app.rag.verify.find_evidence_span rather than showing an
unverified claim as if it were a real quote.

The matching and rendering primitives themselves live in app.rag.verify,
which depends on neither FAISS nor the database; this module adds the
OpenAI call and the retrieved-case plumbing around them.
"""

from typing import List, Optional, TypedDict

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from app.rag.retriever import RetrievedCase
from app.rag.verify import (  # noqa: F401  (render_citations_html re-exported for callers)
    VerifiedCitation,
    find_evidence_span,
    locate_quote as _locate_quote,
    render_citations_html,
)

load_dotenv()

GENERATION_MODEL = "gpt-5-mini"
MAX_CASE_CHARS = 8000  # per-case context cap, keeps cost bounded


class _Citation(BaseModel):
    case_id: str
    quote: str


class _GeneratedAnswer(BaseModel):
    answer: str
    citations: List[_Citation]


class GenerationResult(TypedDict):
    answer: str
    citations: List[VerifiedCitation]


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def generate_answer(query: str, cases: List[RetrievedCase]) -> GenerationResult:
    """Generate an answer to `query` grounded in `cases`, with each citation
    verified against the actual case text (or heuristically relocated if the
    model's quote doesn't match verbatim)."""
    if not cases:
        raise ValueError("generate_answer requires at least one retrieved case")

    client = _get_client()

    context = "\n\n".join(
        f"[case_id: {c['case_id']}] {c['case_name']} ({c['citation']})\n"
        f"{c['case_text'][:MAX_CASE_CHARS]}"
        for c in cases
    )
    system = (
        "You are a legal research assistant. Answer the user's question using "
        "only the cases provided below. For every factual or legal claim, cite "
        "the case_id you relied on and quote the exact sentence(s) from that "
        "case's text that support the claim — copy the words verbatim, do not "
        "paraphrase or summarize the quote. If none of the cases support an "
        "answer, say so plainly instead of guessing."
    )
    user = f"Cases:\n{context}\n\nQuestion: {query}"

    completion = client.chat.completions.parse(
        model=GENERATION_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=_GeneratedAnswer,
    )
    parsed = completion.choices[0].message.parsed

    cases_by_id = {c["case_id"]: c for c in cases}
    verified: List[VerifiedCitation] = []
    for citation in parsed.citations:
        case = cases_by_id.get(citation.case_id)
        if case is None:
            # Model cited a case_id outside the retrieved set entirely.
            verified.append({
                "case_id": citation.case_id, "quote": citation.quote,
                "span": None, "verified": False,
            })
            continue

        span = _locate_quote(case["case_text"], citation.quote)
        if span is not None:
            verified.append({
                "case_id": citation.case_id, "quote": citation.quote,
                "span": span, "verified": True,
            })
        else:
            fallback = find_evidence_span(case["case_text"], citation.quote, top_n=1)
            verified.append({
                "case_id": citation.case_id, "quote": citation.quote,
                "span": fallback[0] if fallback else None, "verified": False,
            })

    return {"answer": parsed.answer, "citations": verified}
