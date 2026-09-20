"""
Applies app/db/schema.sql to the Postgres database. Idempotent — every
statement is CREATE ... IF NOT EXISTS, safe to re-run.

Usage:
    venv/bin/python -m app.db.migrate
"""

import os
import logging

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def apply_schema():
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        logger.info("Schema applied successfully")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_schema()
    print("✅ Schema applied to", os.getenv("DATABASE_URL", "postgresql:///legal_ai_experiment"))
