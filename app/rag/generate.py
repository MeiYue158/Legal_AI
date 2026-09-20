"""
Phase 2 — LLM answer generation with self-reported citations ("method B").

The model answers the user's query using only the retrieved cases, and for
each claim quotes the exact passage it relied on. Quotes are then verified
against the source text: an exact (whitespace-tolerant) substring match
locates the real span. When the model paraphrases instead of quoting
verbatim — a known LLM failure mode — we fall back to the similarity
heuristic in app.rag.retriever.find_evidence_span rather than showing an
unverified claim as if it were a real quote.
"""

import html
import os
import re
from typing import List, Optional, Tuple, TypedDict

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from app.rag.retriever import RetrievedCase, find_evidence_span

load_dotenv()

GENERATION_MODEL = "gpt-5-mini"
MAX_CASE_CHARS = 8000  # per-case context cap, keeps cost bounded


class _Citation(BaseModel):
    case_id: str
    quote: str


class _GeneratedAnswer(BaseModel):
    answer: str
    citations: List[_Citation]


class VerifiedCitation(TypedDict):
    case_id: str
    quote: str
    span: Optional[Tuple[int, int]]
    verified: bool  # True = exact quote found in case_text; False = fallback used


class GenerationResult(TypedDict):
    answer: str
    citations: List[VerifiedCitation]


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _locate_quote(case_text: str, quote: str) -> Optional[Tuple[int, int]]:
    """Find quote in case_text. Exact match first, then whitespace-tolerant
    (LLMs often collapse newlines/multiple spaces when quoting)."""
    quote = quote.strip()
    if not quote:
        return None

    idx = case_text.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))

    tokens = quote.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in tokens)
    m = re.search(pattern, case_text)
    return m.span() if m else None


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


def render_citations_html(case_text: str, citations: List[VerifiedCitation]) -> str:
    """Render case_text as HTML with every citation's span highlighted —
    green for a verified verbatim quote, orange for a heuristic fallback
    match. Citations without a locatable span are skipped."""
    spans = sorted(
        ((c["span"], c["verified"]) for c in citations if c["span"] is not None),
        key=lambda item: item[0][0],
    )
    if not spans:
        return html.escape(case_text)

    pieces = []
    cursor = 0
    for (start, end), verified in spans:
        if start < cursor:
            continue  # overlapping citation spans — keep the first
        color = "#c8e6c9" if verified else "#ffe0b2"
        title = "exact quote, verified against source text" if verified else \
            "model's quote did not match the source verbatim — showing closest matching sentence instead"
        pieces.append(html.escape(case_text[cursor:start]))
        pieces.append(
            f'<mark style="background-color:{color};" title="{title}">'
            f'{html.escape(case_text[start:end])}</mark>'
        )
        cursor = end
    pieces.append(html.escape(case_text[cursor:]))
    return "".join(pieces)
