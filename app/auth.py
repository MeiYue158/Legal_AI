"""
Authentication helper module for Streamlit app
Handles user registration, login, and database operations

Phase 0: migrated from SQLite to Postgres (app.db.connection). Function
signatures are kept the same as the old SQLite version so pages/*.py did
not need to change, except: user dicts now include `user_id` and
`legal_expertise`, and create_user() takes an optional legal_expertise arg.
"""

import bcrypt
import logging
from typing import Optional, Tuple

import psycopg2

from app.db.connection import get_connection, dict_cursor
from app.db.migrate import apply_schema

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Initialize the Postgres schema if it doesn't exist yet."""
    apply_schema()


def hash_password(plain: str) -> str:
    """Hash a plain text password using bcrypt."""
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to hash password: {e}")
        raise


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a stored hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to verify password: {e}")
        return False


def create_user(
    username: str,
    email: str,
    password: str,
    legal_expertise: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Create a new user account.

    Args:
        username: Username for the account
        email: Email address (must be unique)
        password: Plain text password
        legal_expertise: 'law' or 'non_law' (used for stratified randomization);
            optional so existing callers/tests without it still work.

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not username or not email or not password:
        return False, "All fields are required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters long"

    if len(password) < 6:
        return False, "Password must be at least 6 characters long"

    if "@" not in email or "." not in email:
        return False, "Please enter a valid email address"

    if legal_expertise is not None and legal_expertise not in ("law", "non_law"):
        return False, "Invalid legal_expertise value"

    password_hash = hash_password(password)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, legal_expertise)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, email, password_hash, legal_expertise),
                )
                conn.commit()
                logger.info(f"User {username} created successfully")
                return True, "User created successfully"
            except psycopg2.errors.UniqueViolation as e:
                conn.rollback()
                msg = str(e)
                if "username" in msg:
                    return False, "Username already exists"
                else:
                    return False, "Email already registered"
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        return False, "An error occurred while creating the account"
    finally:
        conn.close()


def get_user(username: str) -> Optional[dict]:
    """Retrieve user information by username."""
    conn = get_connection()
    try:
        with dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT user_id, username, email, password_hash, legal_expertise, created_at
                FROM users WHERE username = %s
                """,
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get user {username}: {e}")
        return None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """Authenticate a user with username and password."""
    try:
        user = get_user(username)
        if not user:
            return False, "Invalid username or password", None

        if verify_password(password, user["password_hash"]):
            safe_user_data = {
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "legal_expertise": user["legal_expertise"],
                "created_at": user["created_at"].isoformat(),
            }
            return True, "Login successful", safe_user_data
        else:
            return False, "Invalid username or password", None
    except Exception as e:
        logger.error(f"Authentication failed for {username}: {e}")
        return False, "An error occurred during authentication", None


def delete_user(username: str) -> bool:
    """Delete a user account (for testing/cleanup purposes)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
            deleted = cur.rowcount > 0
        conn.commit()
        if deleted:
            logger.info(f"User {username} deleted successfully")
        else:
            logger.warning(f"User {username} not found for deletion")
        return deleted
    except Exception as e:
        logger.error(f"Failed to delete user {username}: {e}")
        return False
    finally:
        conn.close()
