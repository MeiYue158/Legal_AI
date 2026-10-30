"""
AI Backend (FastAPI) — wraps the RAG retrieval + generation pipeline
(app.rag.retriever, app.rag.generate) as a REST API.

Architecture: browser -> React -> Express (product backend: auth, users,
Postgres, logging) -> this FastAPI service (AI backend: RAG/LLM/NLP) ->
OpenAI. The browser never calls this service directly.

Run: venv/bin/uvicorn app.api.main:app --reload --port 8000
"""

import time
from typing import Callable, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.rag.balance import retrieve_balanced
from app.rag.generate import GENERATION_MODEL, generate_answer, render_citations_html
from app.rag.retriever import highlight_evidence_html, retrieve, retrieve_hybrid
from app.rag.stance_retrieval import retrieve_stance_aware

app = FastAPI(title="Legal AI — AI Backend")

RetrievalStrategy = Literal["dense", "hybrid", "balanced", "stance_aware"]

# Each strategy carries how to read its score and what it costs, because
# those differ in ways the caller has to surface:
#   - dense returns cosine similarity (0-1, higher = more similar)
#   - the other three return Reciprocal Rank Fusion scores (~0.01-0.05),
#     which rank correctly but are NOT similarities and must not be
#     labelled as such in a UI
#   - balanced/stance_aware each make LLM calls per query, so they cost
#     money and are an order of magnitude slower
_STRATEGIES: dict[str, tuple[Callable, str, int]] = {
    "dense": (retrieve, "similarity", 0),
    "hybrid": (retrieve_hybrid, "rrf", 0),
    "balanced": (retrieve_balanced, "rrf", 1),
    "stance_aware": (retrieve_stance_aware, "rrf", 2),
}

# Only Express calls this service, but CORS is left permissive for local
# dev in case a browser hits it directly while wiring things up.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RagQueryRequest(BaseModel):
    query: str
    k: int = 5
    use_llm: bool = False
    strategy: RetrievalStrategy = "dense"


class CaseResult(BaseModel):
    case_id: str
    case_name: str
    citation: str
    score: float
    highlighted_html: str
    verified: Optional[bool] = None  # None = not cited by the LLM (or use_llm=False)


class RagQueryResponse(BaseModel):
    query: str
    answer: Optional[str] = None
    cases: List[CaseResult]
    latency_ms: int
    model: str
    strategy: RetrievalStrategy = "dense"
    # "similarity" = cosine (0-1); "rrf" = fusion score, rank-meaningful
    # only. Clients must not print an rrf score as a similarity.
    score_type: str = "similarity"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/rag/query", response_model=RagQueryResponse)
def rag_query(req: RagQueryRequest) -> RagQueryResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    retrieve_fn, score_type, llm_calls = _STRATEGIES[req.strategy]

    start = time.monotonic()
    try:
        cases = retrieve_fn(req.query, k=req.k)
    except FileNotFoundError as e:
        # No FAISS index on disk — operator has to build it; not the
        # caller's fault and not retryable by them.
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        if llm_calls:
            # balanced/stance_aware reach OpenAI during retrieval itself,
            # so a failure here is an upstream problem, not a bad request.
            raise HTTPException(
                status_code=502,
                detail=f"retrieval strategy '{req.strategy}' failed: {e}",
            )
        raise

    if not cases:
        return RagQueryResponse(
            query=req.query, answer=None, cases=[],
            latency_ms=int((time.monotonic() - start) * 1000), model="none",
            strategy=req.strategy, score_type=score_type,
        )

    answer: Optional[str] = None
    model_used = "none"
    citations_by_case: dict = {}

    if req.use_llm:
        try:
            generation = generate_answer(req.query, cases)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"generation failed: {e}")
        answer = generation["answer"]
        model_used = GENERATION_MODEL
        for citation in generation["citations"]:
            citations_by_case.setdefault(citation["case_id"], []).append(citation)

    results: List[CaseResult] = []
    for case in cases:
        case_citations = citations_by_case.get(case["case_id"])
        if case_citations:
            highlighted_html = render_citations_html(case["case_text"], case_citations)
            verified: Optional[bool] = any(c["verified"] for c in case_citations)
        else:
            highlighted_html = highlight_evidence_html(case["case_text"], req.query, top_n=2)
            verified = None
        results.append(CaseResult(
            case_id=case["case_id"],
            case_name=case["case_name"],
            citation=case["citation"],
            score=case["score"],
            highlighted_html=highlighted_html,
            verified=verified,
        ))

    return RagQueryResponse(
        query=req.query, answer=answer, cases=results,
        latency_ms=int((time.monotonic() - start) * 1000), model=model_used,
        strategy=req.strategy, score_type=score_type,
    )
