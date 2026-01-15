from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, EmailStr

from app.services.auth import hash_password, verify_password, create_session_token, verify_session_token, hash_api_key
from app.services.database import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    count_users,
    update_user_last_login,
    get_api_key_by_hash,
    update_api_key_last_used,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def get_current_user(request: Request) -> dict | None:
    """Get current user from session cookie or API key."""
    # Check for API key first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token.startswith("shipit_"):
            key_hash = hash_api_key(token)
            api_key = get_api_key_by_hash(key_hash)
            if api_key:
                # Check expiry
                expires_at = datetime.fromisoformat(api_key["expires_at"])
                if expires_at > datetime.utcnow():
                    update_api_key_last_used(api_key["id"])
                    return get_user_by_id(api_key["user_id"])
            return None

    # Fall back to session cookie
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    payload = verify_session_token(session_token)
    if not payload:
        return None
    user = get_user_by_id(payload["sub"])
    return user


def require_auth(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/setup")
def setup_first_user(request: SetupRequest, response: Response):
    """Create the first admin user. Only works when no users exist."""
    if count_users() > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    password_hash = hash_password(request.password)
    user = create_user(
        email=request.email,
        name=request.name,
        auth_type="local",
        password_hash=password_hash,
        is_admin=True,
    )

    # Auto-login after setup
    token = create_session_token(user["id"])
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=8 * 60 * 60,  # 8 hours
    )

    return user


@router.post("/login")
def login(request: LoginRequest, response: Response):
    """Login with email and password."""
    user = get_user_by_email(request.email)
    if not user or user["auth_type"] != "local":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    update_user_last_login(user["id"])

    token = create_session_token(user["id"])
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=8 * 60 * 60,
    )

    return {"message": "Login successful", "user": user}


@router.get("/me")
def get_me(user: dict = Depends(require_auth)):
    """Get current authenticated user."""
    return user


@router.post("/logout")
def logout(response: Response):
    """Logout - clear session cookie."""
    response.delete_cookie(key="session")
    return {"message": "Logged out"}
