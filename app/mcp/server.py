"""
Citation verification MCP server.

Exposes this project's citation-checking machinery (app.rag.verify) to any
MCP client — Claude Desktop, Claude Code, or another agent. The point is
that these tools need no corpus: they take the document text as an argument,
so a client can check a quote against a contract, a paper, or a court
opinion this project has never seen.

Why this capability and not the retrieval pipeline: verification is the one
piece here that is useful outside this application. Retrieval only means
something against our 136-case index, and the product calls it directly as
a Python function, so putting it behind a protocol would add hops without
adding reach.

Three tools:
  verify_quote      did the model actually quote this document verbatim?
  locate_evidence   which sentence best supports this claim? (a guess)
  check_citations   both of the above, over a batch of claimed quotes

The distinction matters and is preserved in every response: an exact match
is evidence, a similarity match is a lead. A client that conflates them
reintroduces the failure this server exists to catch.

Run:
    venv/bin/python -m app.mcp.server
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.rag.verify import (
    find_evidence_span,
    locate_quote,
    match_kind,
    score_evidence_spans,
)

MAX_DOCUMENT_CHARS = 400_000  # ~100k tokens; guards against pathological input

# Below this cosine similarity, warn that the document probably does not
# address the claim at all. Calibrated rather than guessed: against a
# sample document, claims the text genuinely covers scored 0.67-0.80 while
# unrelated claims scored 0.12-0.35, so the midpoint of that gap separates
# them. all-MiniLM-L6-v2 rates even unrelated English sentence pairs around
# 0.1-0.35, which is why a naive 0.3 cutoff lets obvious misses through.
WEAK_EVIDENCE_THRESHOLD = 0.5

mcp = MCPServer(
    name="legal-citation-verifier",
    title="Citation Verifier",
    instructions=(
        "Verifies whether quoted passages actually appear in a source document, "
        "and locates the sentences most likely to support a claim.\n\n"
        "Use verify_quote when something is presented as a direct quotation and "
        "you need to know whether it is real. Use locate_evidence when you have "
        "a claim and want to find where (or whether) the document supports it. "
        "Use check_citations to check several quotes against one document.\n\n"
        "Treat the two outcomes differently: match_type 'exact' or "
        "'whitespace_tolerant' means the quote is genuinely in the document. "
        "A locate_evidence result is only the closest sentence found by "
        "embedding similarity — it is a lead, never proof, and a low similarity "
        "score means the document probably does not support the claim at all."
    ),
)


class QuoteVerification(BaseModel):
    """Whether a quote genuinely appears in the document."""

    verified: bool = Field(description="True only for a real verbatim match.")
    match_type: str = Field(
        description="'exact' | 'whitespace_tolerant' | 'not_found'. "
        "whitespace_tolerant means the words match but spacing/newlines differ."
    )
    start: Optional[int] = Field(default=None, description="Character offset of the match.")
    end: Optional[int] = Field(default=None, description="End character offset.")
    matched_text: Optional[str] = Field(
        default=None,
        description="The text actually found at that span, as it appears in the document.",
    )
    note: str = Field(description="How to read this result.")


class EvidenceSpan(BaseModel):
    """A sentence that may support a claim. Similarity, not proof."""

    start: int
    end: int
    sentence: str
    similarity: float = Field(
        description="Cosine similarity to the claim, 0-1. Unrelated English "
        "sentences typically score 0.1-0.35 with this model, so a score near "
        "0.3 is NOT weak support — it is noise. Genuine topical matches run "
        "0.65 and above."
    )


class EvidenceResult(BaseModel):
    spans: List[EvidenceSpan]
    note: str = Field(description="How to read these results.")


class CitationCheck(BaseModel):
    quote: str
    verified: bool
    match_type: str
    start: Optional[int] = None
    end: Optional[int] = None
    fallback_sentence: Optional[str] = Field(
        default=None,
        description="When the quote was not found, the closest sentence in the "
        "document. Shown so you can see what the source actually says — it is "
        "NOT a correction of the quote.",
    )


class CitationReport(BaseModel):
    total: int
    verified_count: int
    unverified_count: int
    citations: List[CitationCheck]
    summary: str


def _check_length(document_text: str) -> None:
    """Reject oversized input as a ToolError, not a bare exception — the SDK
    turns ToolError into an is_error result the client can read and act on,
    whereas any other exception becomes an opaque crash with the message
    stripped. The caller needs to know to send a section instead."""
    if len(document_text) > MAX_DOCUMENT_CHARS:
        raise ToolError(
            f"document_text is {len(document_text):,} characters; the limit is "
            f"{MAX_DOCUMENT_CHARS:,}. Pass the relevant section or chapter "
            "instead of the whole file."
        )


@mcp.tool(
    title="Verify a quote against its source",
    description=(
        "Check whether `quote` actually appears in `document_text`. Exact match "
        "first, then a whitespace-tolerant match (models routinely collapse "
        "newlines and runs of spaces when quoting). Returns the character span "
        "when found. A 'not_found' result means the quote is not in the document "
        "in any form — treat it as fabricated or misattributed."
    ),
)
def verify_quote(document_text: str, quote: str) -> QuoteVerification:
    _check_length(document_text)

    kind = match_kind(document_text, quote)
    if kind == "not_found":
        return QuoteVerification(
            verified=False,
            match_type="not_found",
            note=(
                "This quote does not appear in the document, even allowing for "
                "whitespace differences. Do not present it as a quotation. Use "
                "locate_evidence if you want to find what the document does say."
            ),
        )

    span = locate_quote(document_text, quote)
    assert span is not None  # match_kind already established there is one
    start, end = span
    return QuoteVerification(
        verified=True,
        match_type=kind,
        start=start,
        end=end,
        matched_text=document_text[start:end],
        note=(
            "Verbatim match — safe to present as a direct quotation."
            if kind == "exact"
            else "The words match but whitespace differs. Quote matched_text, "
            "not the input, to reproduce the source exactly."
        ),
    )


@mcp.tool(
    title="Locate supporting evidence for a claim",
    description=(
        "Find the sentence(s) in `document_text` most similar to `claim`, by "
        "embedding cosine similarity. Use this when you have a claim rather than "
        "a quotation, or after verify_quote returns not_found. Results are "
        "ranked guesses, not verification: a high score means the sentence is "
        "topically close, not that it supports the claim."
    ),
)
def locate_evidence(document_text: str, claim: str, top_n: int = 3) -> EvidenceResult:
    _check_length(document_text)
    top_n = max(1, min(top_n, 20))

    scored = score_evidence_spans(document_text, claim, top_n=top_n)
    if not scored:
        return EvidenceResult(
            spans=[],
            note="No sentences could be extracted from the document.",
        )

    best = max(s["similarity"] for s in scored)
    if best < WEAK_EVIDENCE_THRESHOLD:
        note = (
            f"WEAK — best similarity is only {best:.2f}, below the "
            f"{WEAK_EVIDENCE_THRESHOLD} mark that separates claims this kind of "
            "document actually covers from ones it does not. Treat the document "
            "as silent on this claim and say so, rather than citing the closest "
            "sentence as though it were support."
        )
    else:
        note = (
            "These are the closest sentences by similarity, in reading order. "
            "They are leads, not verification — read them before relying on them, "
            "and quote them through verify_quote if you intend to present a quotation."
        )
    return EvidenceResult(spans=[EvidenceSpan(**s) for s in scored], note=note)


@mcp.tool(
    title="Check a batch of citations against one document",
    description=(
        "Verify several claimed quotations against the same `document_text` in "
        "one call. For each quote that is not found, also returns the closest "
        "sentence so you can see what the source actually says. Use this to "
        "audit a summary or answer that cites a document repeatedly."
    ),
)
def check_citations(document_text: str, quotes: List[str]) -> CitationReport:
    _check_length(document_text)
    if not quotes:
        return CitationReport(
            total=0, verified_count=0, unverified_count=0, citations=[],
            summary="No quotes supplied.",
        )

    checks: List[CitationCheck] = []
    for quote in quotes:
        kind = match_kind(document_text, quote)
        if kind == "not_found":
            fallback = find_evidence_span(document_text, quote, top_n=1)
            checks.append(CitationCheck(
                quote=quote,
                verified=False,
                match_type="not_found",
                fallback_sentence=(
                    document_text[fallback[0][0]:fallback[0][1]] if fallback else None
                ),
            ))
        else:
            start, end = locate_quote(document_text, quote)  # type: ignore[misc]
            checks.append(CitationCheck(
                quote=quote, verified=True, match_type=kind, start=start, end=end,
            ))

    verified_count = sum(1 for c in checks if c.verified)
    unverified = len(checks) - verified_count
    if unverified == 0:
        summary = f"All {len(checks)} quotes verified against the document."
    else:
        summary = (
            f"{verified_count} of {len(checks)} quotes verified. "
            f"{unverified} could not be found in the document and should not be "
            "presented as quotations."
        )
    return CitationReport(
        total=len(checks),
        verified_count=verified_count,
        unverified_count=unverified,
        citations=checks,
        summary=summary,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
