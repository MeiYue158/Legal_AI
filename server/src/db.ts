import { Pool } from "pg";

// Same Postgres database the Python side (app/db/connection.py) uses —
// this backend owns users/documents/ai_queries/feedback/user_events;
// corpus_cases/tasks/experiments stay Python's concern.
export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});
