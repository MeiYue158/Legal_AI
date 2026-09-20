"""
AI Backend (FastAPI) — wraps the RAG retrieval + generation pipeline
(app.rag.retriever, app.rag.generate) as a REST API.

Architecture: browser -> React -> Express (product backend: auth, users,
Postgres, logging) -> this FastAPI service (AI backend: RAG/LLM/NLP) ->
OpenAI. The browser never calls this service directly.

Run: venv/bin/uvicorn app.api.main:app --reload --port 8000
"""

import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.rag.generate import GENERATION_MODEL, generate_answer, render_citations_html
from app.rag.retriever import highlight_evidence_html, retrieve

app = FastAPI(title="Legal AI — AI Backend")

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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/rag/query", response_model=RagQueryResponse)
def rag_query(req: RagQueryRequest) -> RagQueryResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    start = time.monotonic()
    try:
        cases = retrieve(req.query, k=req.k)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not cases:
        return RagQueryResponse(
            query=req.query, answer=None, cases=[],
            latency_ms=int((time.monotonic() - start) * 1000), model="none",
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
    )
