
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(user_id: str, expires_hours: int) -> str:
    """Create a JWT token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_hours)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def create_session_token(user_id: str) -> str:
    """Create a session JWT token."""
    return _create_token(user_id, settings.session_duration_hours)


def verify_session_token(token: str) -> dict | None:
    """Verify a session token. Returns payload if valid, None otherwise."""
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=["HS256"])
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
