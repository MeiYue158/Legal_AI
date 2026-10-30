import { Router } from "express";
import { pool } from "../db";
import { requireAuth } from "../middleware/auth";
import { logEvent } from "../events";

export const legalAnalysisRouter = Router();

const AI_BACKEND_URL = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

const RETRIEVAL_STRATEGIES = ["dense", "hybrid", "balanced", "stance_aware"] as const;
type RetrievalStrategy = (typeof RETRIEVAL_STRATEGIES)[number];

legalAnalysisRouter.post("/", requireAuth, async (req, res) => {
  const { query, k, useLlm, documentId, strategy } = req.body ?? {};
  if (!query || typeof query !== "string") {
    return res.status(400).json({ error: "query is required" });
  }
  if (strategy && !RETRIEVAL_STRATEGIES.includes(strategy as RetrievalStrategy)) {
    return res.status(400).json({
      error: `strategy must be one of: ${RETRIEVAL_STRATEGIES.join(", ")}`,
    });
  }
  const retrievalStrategy: RetrievalStrategy = strategy ?? "dense";

  const start = Date.now();
  let aiResponse: Response;
  try {
    aiResponse = await fetch(`${AI_BACKEND_URL}/rag/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        k: k ?? 5,
        use_llm: Boolean(useLlm),
        strategy: retrievalStrategy,
      }),
    });
  } catch (err) {
    console.error("AI backend unreachable:", err);
    return res.status(502).json({ error: "AI backend unreachable" });
  }

  const latencyMs = Date.now() - start;

  if (!aiResponse.ok) {
    const detail = await aiResponse.text();
    return res.status(502).json({ error: "AI backend error", detail });
  }

  const result = await aiResponse.json();

  let queryId: number | null = null;
  try {
    const insert = await pool.query(
      `INSERT INTO ai_queries (user_id, document_id, query, response, model, latency_ms)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING query_id`,
      [req.user!.userId, documentId ?? null, query, JSON.stringify(result), result.model, latencyMs]
    );
    queryId = insert.rows[0].query_id;
  } catch (err) {
    // A logging failure shouldn't hide a successful AI result from the user.
    console.error("failed to log ai_queries row:", err);
  }

  await logEvent(req, "rag_query_submitted", {
    page: "case-research",
    metadata: {
      useLlm: Boolean(useLlm),
      k: k ?? 5,
      strategy: retrievalStrategy,
      latencyMs,
      queryId,
    },
  });

  res.json({ ...result, queryId });
});
