import { Router } from "express";
import { pool } from "../db";
import { requireAuth } from "../middleware/auth";

export const historyRouter = Router();

historyRouter.get("/", requireAuth, async (req, res) => {
  try {
    const result = await pool.query(
      `SELECT q.query_id, q.query, q.model, q.latency_ms, q.created_at,
              f.rating, f.comment
       FROM ai_queries q
       LEFT JOIN feedback f ON f.query_id = q.query_id
       WHERE q.user_id = $1
       ORDER BY q.created_at DESC
       LIMIT 50`,
      [req.user!.userId]
    );
    res.json(result.rows);
  } catch (err) {
    console.error("history query failed:", err);
    res.status(500).json({ error: "failed to load history" });
  }
});
