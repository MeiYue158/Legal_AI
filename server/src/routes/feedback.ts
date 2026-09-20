import { Router } from "express";
import { pool } from "../db";
import { requireAuth } from "../middleware/auth";
import { logEvent } from "../events";

export const feedbackRouter = Router();

feedbackRouter.post("/", requireAuth, async (req, res) => {
  const { queryId, rating, comment } = req.body ?? {};
  const ratingNum = Number(rating);

  if (!Number.isInteger(queryId)) {
    return res.status(400).json({ error: "queryId is required" });
  }
  if (!Number.isInteger(ratingNum) || ratingNum < 1 || ratingNum > 5) {
    return res.status(400).json({ error: "rating must be an integer 1-5" });
  }

  try {
    const result = await pool.query(
      `INSERT INTO feedback (query_id, user_id, rating, comment)
       VALUES ($1, $2, $3, $4)
       RETURNING feedback_id, created_at`,
      [queryId, req.user!.userId, ratingNum, comment ?? null]
    );

    await logEvent(req, "feedback_submitted", {
      page: "case-research",
      metadata: { queryId, rating: ratingNum },
    });

    res.status(201).json(result.rows[0]);
  } catch (err: any) {
    if (err.code === "23503") {
      // foreign_key_violation — queryId doesn't reference a real ai_queries row
      return res.status(404).json({ error: "queryId not found" });
    }
    console.error("feedback insert failed:", err);
    res.status(500).json({ error: "failed to record feedback" });
  }
});
