"""
Postgres connection helper.

Reads DATABASE_URL from the environment (.env supported). Defaults to a
local trust-auth connection to the `legal_ai_experiment` database, which is
what Phase 0 set up on this machine's Homebrew Postgres.
"""

import os
import logging

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql:///legal_ai_experiment"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_connection():
    """Return a new psycopg2 connection to the experiment database."""
    return psycopg2.connect(DATABASE_URL)


def dict_cursor(conn):
    """Return a cursor that yields rows as dicts (RealDictRow)."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
