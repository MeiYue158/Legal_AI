"""
Authentication helper module for Streamlit app
Handles user registration, login, and database operations
"""

import sqlite3
import bcrypt
import os
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Database path configurable via environment variable
DB_PATH = os.getenv("AUTH_DB_PATH", "auth.db")

def init_db(db_path: str = None) -> None:
    """
    Initialize the SQLite database and create users table if it doesn't exist.
    
    Args:
        db_path: Path to the database file (defaults to AUTH_DB_PATH env var or "auth.db")
    """
    db_path = db_path or DB_PATH
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized successfully at {db_path}")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def hash_password(plain: str) -> str:
    """
    Hash a plain text password using bcrypt.
    
    Args:
        plain: Plain text password
        
    Returns:
        Hashed password string
    """
    try:
        # Generate salt and hash password
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(plain.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to hash password: {e}")
        raise

def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain text password against a stored hash.
    
    Args:
        plain: Plain text password to verify
        hashed: Stored password hash
        
    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to verify password: {e}")
        return False

def create_user(username: str, email: str, password: str, db_path: str = None) -> Tuple[bool, str]:
    """
    Create a new user account.
    
    Args:
        username: Username for the account
        email: Email address (must be unique)
        password: Plain text password
        db_path: Database path (optional, defaults to global DB_PATH)
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    db_path = db_path or DB_PATH
    
    try:
        # Validate input
        if not username or not email or not password:
            return False, "All fields are required"
        
        if len(username) < 3:
            return False, "Username must be at least 3 characters long"
        
        if len(password) < 6:
            return False, "Password must be at least 6 characters long"
        
        # Basic email validation
        if '@' not in email or '.' not in email:
            return False, "Please enter a valid email address"
        
        # Hash password
        password_hash = hash_password(password)
        
        # Store in database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
            """, (username, email, password_hash, datetime.now().isoformat()))
            
            conn.commit()
            logger.info(f"User {username} created successfully")
            return True, "User created successfully"
            
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                if "username" in str(e):
                    return False, "Username already exists"
                else:
                    return False, "Email already registered"
            else:
                return False, "Database error occurred"
        
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        return False, "An error occurred while creating the account"

def get_user(username: str, db_path: str = None) -> Optional[dict]:
    """
    Retrieve user information by username.
    
    Args:
        username: Username to look up
        db_path: Database path (optional, defaults to global DB_PATH)
        
    Returns:
        User dictionary with fields or None if not found
    """
    db_path = db_path or DB_PATH
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT username, email, password_hash, created_at
            FROM users WHERE username = ?
        """, (username,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "username": row[0],
                "email": row[1],
                "password_hash": row[2],
                "created_at": row[3]
            }
        else:
            return None
            
    except Exception as e:
        logger.error(f"Failed to get user {username}: {e}")
        return None

def authenticate_user(username: str, password: str, db_path: str = None) -> Tuple[bool, str, Optional[dict]]:
    """
    Authenticate a user with username and password.
    
    Args:
        username: Username to authenticate
        password: Plain text password
        db_path: Database path (optional, defaults to global DB_PATH)
        
    Returns:
        Tuple of (success: bool, message: str, user_data: Optional[dict])
    """
    db_path = db_path or DB_PATH
    
    try:
        # Get user from database
        user = get_user(username, db_path)
        if not user:
            return False, "Invalid username or password", None
        
        # Verify password
        if verify_password(password, user["password_hash"]):
            # Don't return password hash in user data
            safe_user_data = {
                "username": user["username"],
                "email": user["email"],
                "created_at": user["created_at"]
            }
            return True, "Login successful", safe_user_data
        else:
            return False, "Invalid username or password", None
            
    except Exception as e:
        logger.error(f"Authentication failed for {username}: {e}")
        return False, "An error occurred during authentication", None

def delete_user(username: str, db_path: str = None) -> bool:
    """
    Delete a user account (for testing/cleanup purposes).
    
    Args:
        username: Username to delete
        db_path: Database path (optional, defaults to global DB_PATH)
        
    Returns:
        True if successful, False otherwise
    """
    db_path = db_path or DB_PATH
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        if deleted:
            logger.info(f"User {username} deleted successfully")
        else:
            logger.warning(f"User {username} not found for deletion")
            
        return deleted
        
    except Exception as e:
        logger.error(f"Failed to delete user {username}: {e}")
        return False
