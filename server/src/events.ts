import { Request } from "express";
import { pool } from "./db";

/**
 * Product-analytics event log — funnel steps (registered, query submitted,
 * feedback given, ...), independent of the A/B-test `events` table on the
 * Python side. Never throws: logging must not break the request it's
 * attached to.
 */
export async function logEvent(
  req: Request,
  eventType: string,
  opts: { page?: string; metadata?: Record<string, unknown> } = {}
): Promise<void> {
  const sessionId = (req.header("x-session-id") || "unknown").slice(0, 200);
  const userId = req.user?.userId ?? null;

  try {
    await pool.query(
      `INSERT INTO user_events (user_id, session_id, event_type, page, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [
        userId,
        sessionId,
        eventType,
        opts.page ?? null,
        opts.metadata ? JSON.stringify(opts.metadata) : null,
      ]
    );
  } catch (err) {
    console.error("logEvent failed:", err);
  }
}
