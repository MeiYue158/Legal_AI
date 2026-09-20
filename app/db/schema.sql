-- Phase 0 schema for the experiment-centric pivot.
-- Applied idempotently by app/db/migrate.py.

-- ── Users ────────────────────────────────────────────────────────────────
-- Replaces the old SQLite users table. Adds a stable numeric user_id
-- (assignment hashing keys off this, not username) and legal_expertise
-- (needed for stratified randomization + heterogeneous-effect analysis).
CREATE TABLE IF NOT EXISTS users (
    user_id         SERIAL PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    legal_expertise TEXT CHECK (legal_expertise IN ('law', 'non_law')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Experiments ──────────────────────────────────────────────────────────
-- One row per experiment. `cells` holds the arm definitions (the 2x2 grid);
-- `salt` is the per-experiment secret mixed into the assignment hash.
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'running', 'paused', 'completed')),
    cells         JSONB NOT NULL,
    salt          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Assignments ──────────────────────────────────────────────────────────
-- Sticky bucketing: written once on first eligible exposure, read on every
-- subsequent visit so the same user always lands in the same cell.
CREATE TABLE IF NOT EXISTS assignments (
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    cell_id       TEXT NOT NULL,
    stratum       TEXT,              -- legal_expertise value at assignment time
    assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, experiment_id)
);

-- ── Corpus cases ─────────────────────────────────────────────────────────
-- Ingested case-law documents (source of "citations" for the product
-- surface / retrieval). embedding_row points into the FAISS index file.
CREATE TABLE IF NOT EXISTS corpus_cases (
    case_id        TEXT PRIMARY KEY,
    jurisdiction   TEXT,
    court          TEXT,
    case_name      TEXT,
    citation       TEXT,
    decision_date  TEXT,
    case_text      TEXT NOT NULL,
    source_file    TEXT,
    embedding_row  INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Tasks ────────────────────────────────────────────────────────────────
-- The task bank shown to participants: one row = one claim+citation
-- verification item. `candidate_citations` holds all options shown;
-- `correct_index` is the ground truth; `is_planted_error` marks items
-- deliberately rigged with an unsupported/mismatched claim for the
-- overreliance measurement.
CREATE TABLE IF NOT EXISTS tasks (
    task_id              SERIAL PRIMARY KEY,
    source               TEXT NOT NULL,   -- 'casehold' | 'cap' | 'authored'
    context              TEXT NOT NULL,
    candidate_citations  JSONB NOT NULL,
    correct_index        INTEGER NOT NULL,
    shown_index          INTEGER,         -- which candidate is presented as "the AI's claim"
    is_planted_error     BOOLEAN NOT NULL DEFAULT FALSE,
    case_id              TEXT REFERENCES corpus_cases(case_id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Eval queries ─────────────────────────────────────────────────────────
-- Phase 2 RAG evaluation set (bullet 2: "基于 150 条专家标注法律查询构建 Legal
-- RAG 评估体系"). relevant_case_ids is the recall ground truth; adverse_case_ids
-- is the subset unfavorable to the position implied by `query` — the ground
-- truth for the "unfavorable-precedent recall" / one-sided-bias metrics.
-- source='llm_draft' rows are a machine-assisted first pass (see
-- scripts/build_eval_queries.py) and must be human-reviewed before being
-- used to report eval numbers.
CREATE TABLE IF NOT EXISTS eval_queries (
    eval_query_id      SERIAL PRIMARY KEY,
    query              TEXT NOT NULL,
    relevant_case_ids  JSONB NOT NULL,
    adverse_case_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes              TEXT,
    source             TEXT NOT NULL DEFAULT 'llm_draft'
                           CHECK (source IN ('llm_draft', 'human_reviewed')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Events ───────────────────────────────────────────────────────────────
-- The data backbone. Every trigger/impression/answer/completion writes here.
CREATE TABLE IF NOT EXISTS events (
    event_id      BIGSERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    experiment_id TEXT REFERENCES experiments(experiment_id),
    cell_id       TEXT,
    task_id       INTEGER REFERENCES tasks(task_id),
    event_type    TEXT NOT NULL,   -- 'trigger' | 'impression' | 'verification_response'
                                    -- | 'task_complete' | 'highlight_interaction'
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload       JSONB
);

CREATE INDEX IF NOT EXISTS idx_events_user_exp ON events(user_id, experiment_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_assignments_experiment ON assignments(experiment_id);

-- ── Documents ────────────────────────────────────────────────────────────
-- Metadata for uploaded contracts/documents. Content itself is stored by
-- whatever pipeline processes it (not this table) — this is the product
-- backend's record of "who uploaded what, when."
CREATE TABLE IF NOT EXISTS documents (
    document_id   SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    filename      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── AI queries ───────────────────────────────────────────────────────────
-- One row per request the product backend forwarded to the AI backend
-- (RAG query, contract analysis, ...). document_id is null for queries not
-- tied to an uploaded document (e.g. free-text case research).
CREATE TABLE IF NOT EXISTS ai_queries (
    query_id      SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    document_id   INTEGER REFERENCES documents(document_id),
    query         TEXT NOT NULL,
    response      JSONB NOT NULL,
    model         TEXT NOT NULL,
    latency_ms    INTEGER NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Feedback ─────────────────────────────────────────────────────────────
-- User rating/comment on one ai_queries row.
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   SERIAL PRIMARY KEY,
    query_id      INTEGER NOT NULL REFERENCES ai_queries(query_id),
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    rating        INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── User events ──────────────────────────────────────────────────────────
-- General product-analytics event log (page views, clicks, funnel steps) —
-- distinct from `events`, which is scoped to the A/B-test experiment
-- mechanism above. session_id groups events within one browser session.
CREATE TABLE IF NOT EXISTS user_events (
    event_id      BIGSERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(user_id),
    session_id    TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    page          TEXT,
    metadata      JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_queries_user ON ai_queries(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_query ON feedback(query_id);
CREATE INDEX IF NOT EXISTS idx_user_events_user ON user_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_session ON user_events(session_id);
CREATE INDEX IF NOT EXISTS idx_user_events_type ON user_events(event_type);
