"""
Tests for citation verification (app.rag.verify) and the MCP tools built
on it (app.mcp.server).

The distinction under test throughout is between *verification* — the quote
is genuinely in the document — and *similarity* — this is the closest
sentence we could find. Conflating the two is the failure the whole module
exists to prevent, so most of these assertions are about keeping them apart.

Quote matching is pure string/regex work and needs no model. The embedding
tests are marked so they can be skipped where loading ~90MB is unwelcome:
    pytest -m "not embedding"
"""

import pytest

from app.rag.verify import locate_quote, match_kind

DOC = (
    "Section 4. Termination.\n"
    "We may suspend or terminate your account at any time, with or without\n"
    "notice, for any reason.\n\n"
    "Section 5. Limitation of Liability.\n"
    "In no event shall the Company be liable for any indirect, incidental, or\n"
    "consequential damages arising out of your use of the Service.\n\n"
    "Section 6. Governing Law.\n"
    "These Terms are governed by the laws of the State of Delaware."
)


# ── locate_quote / match_kind ────────────────────────────────────────────

def test_exact_quote_is_located_at_the_right_offsets():
    quote = "governed by the laws of the State of Delaware"
    span = locate_quote(DOC, quote)
    assert span is not None
    start, end = span
    assert DOC[start:end] == quote


def test_exact_match_is_reported_as_exact():
    assert match_kind(DOC, "In no event shall the Company be liable") == "exact"


def test_quote_spanning_a_newline_matches_whitespace_tolerantly():
    # The source wraps between "without" and "notice"; a model quoting it
    # back will almost always collapse that to a single space.
    quote = "with or without notice, for any reason."
    assert quote not in DOC  # the literal form really is absent
    assert match_kind(DOC, quote) == "whitespace_tolerant"
    span = locate_quote(DOC, quote)
    assert span is not None
    assert DOC[span[0]:span[1]].split() == quote.split()


def test_collapsed_double_space_matches_whitespace_tolerantly():
    doc = "The parties agree.  The contract is binding."
    quote = "The parties agree. The contract is binding."  # one space
    assert match_kind(doc, quote) == "whitespace_tolerant"


def test_fabricated_quote_is_not_found():
    assert match_kind(DOC, "The Company guarantees a full refund") == "not_found"
    assert locate_quote(DOC, "The Company guarantees a full refund") is None


def test_empty_and_whitespace_quotes_are_not_found():
    # A blank quote must never report as verified — returning a zero-length
    # match at offset 0 would make every empty citation look confirmed.
    for quote in ("", "   ", "\n\t"):
        assert locate_quote(DOC, quote) is None
        assert match_kind(DOC, quote) == "not_found"


def test_regex_metacharacters_in_a_quote_are_matched_literally():
    doc = "Damages are capped at $1,000 (one thousand dollars) [see Ex. A]."
    quote = "$1,000 (one thousand dollars) [see Ex. A]"
    assert match_kind(doc, quote) == "exact"
    span = locate_quote(doc, quote)
    assert span is not None and doc[span[0]:span[1]] == quote


def test_quote_longer_than_the_document_is_not_found():
    assert locate_quote("short text", "a much longer quote than the document") is None


def test_first_occurrence_is_returned_for_a_repeated_quote():
    doc = "The term applies. The term applies."
    span = locate_quote(doc, "The term applies.")
    assert span == (0, len("The term applies."))


# ── find_evidence_span / score_evidence_spans ────────────────────────────

@pytest.mark.embedding
def test_evidence_lands_on_the_relevant_sentence():
    from app.rag.verify import score_evidence_spans

    spans = score_evidence_spans(DOC, "The company limits its liability.", top_n=1)
    assert len(spans) == 1
    assert "liable" in spans[0]["sentence"] or "Liability" in spans[0]["sentence"]


@pytest.mark.embedding
def test_unrelated_claim_scores_below_the_weak_threshold():
    # Guards the calibration: an unrelated claim must stay under the cutoff,
    # or locate_evidence will present noise as a lead.
    from app.mcp.server import WEAK_EVIDENCE_THRESHOLD
    from app.rag.verify import score_evidence_spans

    spans = score_evidence_spans(
        DOC, "Employees receive twenty days of paid parental leave.", top_n=3
    )
    assert max(s["similarity"] for s in spans) < WEAK_EVIDENCE_THRESHOLD


@pytest.mark.embedding
def test_related_claim_scores_above_the_weak_threshold():
    from app.mcp.server import WEAK_EVIDENCE_THRESHOLD
    from app.rag.verify import score_evidence_spans

    spans = score_evidence_spans(DOC, "Delaware law governs this agreement.", top_n=3)
    assert max(s["similarity"] for s in spans) >= WEAK_EVIDENCE_THRESHOLD


@pytest.mark.embedding
def test_spans_come_back_in_reading_order_not_score_order():
    # Callers highlight in place, so out-of-order spans would corrupt the
    # rendered output.
    from app.rag.verify import find_evidence_span

    spans = find_evidence_span(DOC, "termination and liability", top_n=3)
    assert spans == sorted(spans)


@pytest.mark.embedding
def test_empty_inputs_yield_no_spans():
    from app.rag.verify import find_evidence_span

    assert find_evidence_span("", "a claim") == []
    assert find_evidence_span(DOC, "") == []


# ── HTML rendering ───────────────────────────────────────────────────────

def test_render_escapes_html_outside_the_marks():
    from app.rag.verify import render_citations_html

    doc = 'A <script>alert("x")</script> clause applies here.'
    span = locate_quote(doc, "clause applies here")
    html_out = render_citations_html(
        doc, [{"case_id": "c1", "quote": "clause applies here",
               "span": span, "verified": True}]
    )
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "<mark" in html_out


def test_verified_and_unverified_citations_render_differently():
    # The colour difference is the only thing telling a reader that one
    # quote was confirmed and the other was merely the closest sentence.
    from app.rag.verify import render_citations_html

    doc = "First sentence here. Second sentence there."
    verified = render_citations_html(
        doc, [{"case_id": "c", "quote": "First sentence here",
               "span": (0, 19), "verified": True}]
    )
    fallback = render_citations_html(
        doc, [{"case_id": "c", "quote": "First sentence here",
               "span": (0, 19), "verified": False}]
    )
    assert verified != fallback
    assert "#c8e6c9" in verified      # green = verified
    assert "#ffe0b2" in fallback      # orange = heuristic


def test_citations_without_a_span_are_skipped():
    from app.rag.verify import render_citations_html

    out = render_citations_html(
        DOC, [{"case_id": "c", "quote": "nowhere", "span": None, "verified": False}]
    )
    assert "<mark" not in out


def test_overlapping_spans_keep_the_first():
    from app.rag.verify import render_citations_html

    doc = "Alpha beta gamma delta."
    out = render_citations_html(doc, [
        {"case_id": "a", "quote": "Alpha beta", "span": (0, 10), "verified": True},
        {"case_id": "b", "quote": "beta gamma", "span": (6, 16), "verified": True},
    ])
    assert out.count("<mark") == 1


# ── MCP tool layer ───────────────────────────────────────────────────────

def test_verify_quote_tool_reports_exact_match():
    from app.mcp.server import verify_quote

    r = verify_quote(DOC, "In no event shall the Company be liable")
    assert r.verified is True
    assert r.match_type == "exact"
    assert DOC[r.start:r.end] == "In no event shall the Company be liable"


def test_verify_quote_tool_rejects_a_fabricated_quote():
    from app.mcp.server import verify_quote

    r = verify_quote(DOC, "The Company guarantees a full refund")
    assert r.verified is False
    assert r.match_type == "not_found"
    assert r.start is None and r.end is None
    assert "does not appear" in r.note


def test_whitespace_tolerant_result_points_the_caller_at_matched_text():
    # The input quote has the wrong whitespace, so reproducing the source
    # means quoting matched_text instead.
    from app.mcp.server import verify_quote

    r = verify_quote(DOC, "with or without notice, for any reason.")
    assert r.verified is True
    assert r.match_type == "whitespace_tolerant"
    assert r.matched_text is not None
    assert r.matched_text != "with or without notice, for any reason."
    assert "matched_text" in r.note


def test_oversized_document_raises_a_readable_tool_error():
    # ToolError reaches the client with its message; any other exception is
    # reported as an opaque crash, leaving the caller unable to react.
    from mcp.server.mcpserver.exceptions import ToolError

    from app.mcp.server import MAX_DOCUMENT_CHARS, verify_quote

    with pytest.raises(ToolError, match="limit is"):
        verify_quote("x" * (MAX_DOCUMENT_CHARS + 1), "x")


def test_check_citations_separates_verified_from_fabricated():
    from app.mcp.server import check_citations

    report = check_citations(DOC, [
        "governed by the laws of the State of Delaware",   # exact
        "The Company guarantees a full refund",            # fabricated
    ])
    assert report.total == 2
    assert report.verified_count == 1
    assert report.unverified_count == 1

    good, bad = report.citations
    assert good.verified and good.match_type == "exact"
    assert not bad.verified and bad.match_type == "not_found"
    assert "should not be presented as quotations" in report.summary


def test_check_citations_on_an_empty_list():
    from app.mcp.server import check_citations

    report = check_citations(DOC, [])
    assert report.total == 0
    assert report.citations == []


@pytest.mark.embedding
def test_check_citations_offers_the_closest_sentence_for_a_miss():
    # A miss returns what the document does say — explicitly not a
    # correction of the quote, and the field name has to keep saying so.
    from app.mcp.server import check_citations

    report = check_citations(DOC, ["The Company guarantees a full refund"])
    miss = report.citations[0]
    assert miss.verified is False
    assert miss.fallback_sentence is not None
    assert miss.fallback_sentence in DOC


@pytest.mark.embedding
def test_locate_evidence_flags_weak_matches():
    from app.mcp.server import locate_evidence

    weak = locate_evidence(DOC, "Employees receive paid parental leave.", top_n=1)
    assert weak.note.startswith("WEAK")

    strong = locate_evidence(DOC, "Delaware law governs these terms.", top_n=1)
    assert not strong.note.startswith("WEAK")


@pytest.mark.embedding
def test_locate_evidence_clamps_top_n():
    from app.mcp.server import locate_evidence

    result = locate_evidence(DOC, "liability", top_n=999)
    assert 0 < len(result.spans) <= 20


# ── architectural guarantee ──────────────────────────────────────────────

def test_verify_module_does_not_depend_on_faiss_or_the_database():
    """The MCP server's whole premise is that verification works on any
    document. That holds only while app.rag.verify stays free of the
    retrieval index and Postgres, so assert it rather than trusting it."""
    import ast

    source = open("app/rag/verify.py").read()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "faiss" not in imported
    assert "psycopg2" not in imported
    assert not any(m.startswith("app") for m in imported), (
        f"verify.py must not import from the rest of the app; found {imported}"
    )
