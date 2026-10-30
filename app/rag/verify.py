"""
Citation verification — deciding whether a quoted passage really appears in
a source document, and if not, where the closest supporting sentence is.

Deliberately standalone: this module takes document text as an argument and
imports neither FAISS nor psycopg2. Nothing here knows about corpus_cases,
the retrieval index, or the product's database. That is what lets the same
code serve three callers — the RAG pipeline (app.rag.generate), the product
API (app.api.main), and the MCP server (app.mcp.server), which exposes it to
MCP clients for documents this project has never seen.

Two mechanisms, in order of how much they prove:

  locate_quote()       exact substring, then whitespace-tolerant regex.
                       A hit means the quote is verbatim in the source.
  find_evidence_span() embedding similarity over sentences. A hit means
                       "this is the closest sentence we could find", which
                       is a guess, not verification.

Callers must keep those apart when rendering: presenting a similarity match
as if it were a verified quote is the exact failure this module exists to
prevent.
"""

import html
import re
from functools import lru_cache
from typing import List, Optional, Tuple, TypedDict

import nltk
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


class VerifiedCitation(TypedDict):
    case_id: str
    quote: str
    span: Optional[Tuple[int, int]]
    verified: bool  # True = exact quote found in source; False = fallback used


@lru_cache(maxsize=1)
def load_model() -> SentenceTransformer:
    """The shared sentence-embedding model. Cached, so the retrieval path
    and the verification path hold one instance between them rather than
    loading ~90MB twice."""
    return SentenceTransformer(MODEL_NAME)


def _ensure_punkt() -> None:
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            nltk.download(resource)


@lru_cache(maxsize=1)
def _sentence_tokenizer():
    _ensure_punkt()
    return nltk.data.load("tokenizers/punkt/english.pickle")


def locate_quote(document_text: str, quote: str) -> Optional[Tuple[int, int]]:
    """Find `quote` in `document_text`. Exact match first, then
    whitespace-tolerant (LLMs routinely collapse newlines and runs of
    spaces when quoting). Returns (start, end) character offsets, or None
    when the quote is not present in any form."""
    quote = quote.strip()
    if not quote:
        return None

    idx = document_text.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))

    tokens = quote.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in tokens)
    m = re.search(pattern, document_text)
    return m.span() if m else None


def match_kind(document_text: str, quote: str) -> str:
    """Classify how a quote matches: 'exact' | 'whitespace_tolerant' |
    'not_found'. Split out from locate_quote so callers can report *how*
    a quote was verified, not merely that it was."""
    quote = quote.strip()
    if not quote:
        return "not_found"
    if document_text.find(quote) != -1:
        return "exact"
    return "whitespace_tolerant" if locate_quote(document_text, quote) else "not_found"


def find_evidence_span(
    document_text: str, claim: str, top_n: int = 1
) -> List[Tuple[int, int]]:
    """
    Locate which sentence(s) in document_text most likely support `claim`,
    by embedding cosine similarity.

    Heuristic, not verification — good enough to point a reader at the
    right sentence rather than the whole document. Returns (start, end)
    character offsets in reading order (not score order), so callers can
    highlight in place.
    """
    if not document_text or not claim:
        return []

    spans = list(_sentence_tokenizer().span_tokenize(document_text))
    if not spans:
        return []

    sentences = [document_text[start:end] for start, end in spans]
    model = load_model()
    embeddings = model.encode(sentences + [claim], normalize_embeddings=True)
    sentence_vecs, claim_vec = embeddings[:-1], embeddings[-1]

    scores = sentence_vecs @ claim_vec
    top_n = max(1, min(top_n, len(spans)))
    top_indices = sorted(np.argsort(scores)[-top_n:].tolist())
    return [spans[i] for i in top_indices]


def score_evidence_spans(
    document_text: str, claim: str, top_n: int = 1
) -> List[dict]:
    """Like find_evidence_span, but also returns each sentence's text and
    its cosine similarity to the claim — so a caller can show *how weak*
    a fallback match is instead of presenting every guess as equivalent."""
    if not document_text or not claim:
        return []

    spans = list(_sentence_tokenizer().span_tokenize(document_text))
    if not spans:
        return []

    sentences = [document_text[start:end] for start, end in spans]
    model = load_model()
    embeddings = model.encode(sentences + [claim], normalize_embeddings=True)
    scores = embeddings[:-1] @ embeddings[-1]

    top_n = max(1, min(top_n, len(spans)))
    top_indices = sorted(np.argsort(scores)[-top_n:].tolist())
    return [
        {
            "start": spans[i][0],
            "end": spans[i][1],
            "sentence": sentences[i],
            "similarity": float(scores[i]),
        }
        for i in top_indices
    ]


def highlight_evidence_html(document_text: str, claim: str, top_n: int = 1) -> str:
    """
    Render document_text as HTML with the sentence(s) supporting `claim`
    wrapped in <mark>.

    document_text is untrusted input, so everything outside the <mark>
    tags is HTML-escaped before assembly.
    """
    spans = find_evidence_span(document_text, claim, top_n=top_n)
    if not spans:
        return html.escape(document_text)

    pieces = []
    cursor = 0
    for start, end in spans:
        pieces.append(html.escape(document_text[cursor:start]))
        pieces.append(
            '<mark style="background-color:#fff59d;">'
            f'{html.escape(document_text[start:end])}</mark>'
        )
        cursor = end
    pieces.append(html.escape(document_text[cursor:]))
    return "".join(pieces)


def render_citations_html(
    document_text: str, citations: List[VerifiedCitation]
) -> str:
    """Render document_text as HTML with every citation's span highlighted —
    green for a verified verbatim quote, orange for a heuristic fallback
    match. Citations without a locatable span are skipped."""
    spans = sorted(
        ((c["span"], c["verified"]) for c in citations if c["span"] is not None),
        key=lambda item: item[0][0],
    )
    if not spans:
        return html.escape(document_text)

    pieces = []
    cursor = 0
    for (start, end), verified in spans:
        if start < cursor:
            continue  # overlapping citation spans — keep the first
        color = "#c8e6c9" if verified else "#ffe0b2"
        title = "exact quote, verified against source text" if verified else \
            "model's quote did not match the source verbatim — showing closest matching sentence instead"
        pieces.append(html.escape(document_text[cursor:start]))
        pieces.append(
            f'<mark style="background-color:{color};" title="{title}">'
            f'{html.escape(document_text[start:end])}</mark>'
        )
        cursor = end
    pieces.append(html.escape(document_text[cursor:]))
    return "".join(pieces)
