from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import settings
from app.services.database import create_session, get_session


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(user_id: str, session_id: str | None, expires_hours: int) -> str:
    """Create a JWT token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_hours)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def create_session_token(user_id: str) -> str:
    """Create a session JWT token with database-tracked session."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.session_duration_hours)
    session_id = create_session(user_id, expires_at)
    return _create_token(user_id, session_id, settings.session_duration_hours)


def verify_session_token(token: str) -> dict | None:
    """Verify a session token. Returns payload if valid, None otherwise.

    Checks both JWT validity and that the session exists in the database.
    """
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=["HS256"])

        # If token has a session ID, verify it exists in the database
        session_id = payload.get("sid")
        if session_id:
            session = get_session(session_id)
            if not session:
                return None  # Session was invalidated

        return payload
    except JWTError:
        return None


def generate_api_key() -> tuple[str, str]:
    """Generate an API key. Returns (raw_key, key_hash)."""
    raw_key = "shipit_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    """Hash an API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
