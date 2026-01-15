from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.services.auth import hash_password, verify_password, create_session_token, verify_session_token, hash_api_key
from app.services.database import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    count_users,
    update_user_last_login,
    update_user,
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
                    user = get_user_by_id(api_key["user_id"])
                    # Check if user is deleted
                    if user and user.get("deleted_at"):
                        return None
                    return user
            return None

    # Fall back to session cookie
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    payload = verify_session_token(session_token)
    if not payload:
        return None
    user = get_user_by_id(payload["sub"])
    # Check if user is deleted
    if user and user.get("deleted_at"):
        return None
    return user


def require_auth(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/setup")
def check_setup_needed():
    """Check if initial setup is required (no users exist)."""
    return {"needs_setup": count_users() == 0}


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

    # Check if user is deleted
    if user.get("deleted_at"):
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

    return {
        "message": "Login successful",
        "user": user,
        "password_change_required": bool(user.get("password_change_required")),
    }


@router.get("/me")
def get_me(user: dict = Depends(require_auth)):
    """Get current authenticated user."""
    return {
        **user,
        "password_change_required": bool(user.get("password_change_required")),
    }


@router.post("/logout")
def logout(response: Response):
    """Logout - clear session cookie."""
    response.delete_cookie(key="session")
    return {"message": "Logged out"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(request: ChangePasswordRequest, user: dict = Depends(require_auth)):
    """Change the current user's password."""
    from app.services.database import get_user_by_id, update_user

    # Get fresh user data
    current_user = get_user_by_id(user["id"])
    if not current_user or current_user["auth_type"] != "local":
        raise HTTPException(status_code=400, detail="Cannot change password for this account")

    # Verify current password
    if not verify_password(request.current_password, current_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Validate new password
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Update password and clear change required flag
    update_user(
        user["id"],
        password_hash=hash_password(request.new_password),
        password_change_required=0,
    )

    return {"message": "Password changed successfully"}


@router.get("/config")
def get_auth_config():
    """Get auth configuration for the frontend."""
    return {
        "oidc_enabled": settings.oidc_enabled,
        "local_enabled": True,  # Always allow local auth
    }


@router.get("/oidc/login")
async def oidc_login(response: Response):
    """Initiate OIDC login flow."""
    if not settings.oidc_enabled:
        raise HTTPException(status_code=400, detail="OIDC is not enabled")

    from app.services.oidc import oidc_service, OIDCError

    try:
        state = oidc_service.generate_state()
        auth_url = await oidc_service.get_authorization_url(state)

        # Store state in cookie for CSRF protection
        redirect = RedirectResponse(url=auth_url, status_code=302)
        redirect.set_cookie(
            key="oidc_state",
            value=state,
            httponly=True,
            samesite="lax",
            max_age=600,  # 10 minutes
        )
        return redirect
    except OIDCError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Handle OIDC callback."""
    if not settings.oidc_enabled:
        raise HTTPException(status_code=400, detail="OIDC is not enabled")

    # Handle error response from IdP
    if error:
        error_msg = error_description or error
        # Redirect to frontend with error
        frontend_url = settings.app_url or "http://localhost:5173"
        return RedirectResponse(
            url=f"{frontend_url}?error={error_msg}",
            status_code=302,
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # Verify state matches cookie
    stored_state = request.cookies.get("oidc_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    from app.services.oidc import oidc_service, OIDCError

    try:
        # Exchange code for tokens
        tokens = await oidc_service.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise OIDCError("No access token in response")

        # Get user info
        user_info = await oidc_service.get_user_info(access_token)

        # Validate domain
        if not oidc_service.validate_domain(user_info.email):
            frontend_url = settings.app_url or "http://localhost:5173"
            return RedirectResponse(
                url=f"{frontend_url}?error=Email domain not allowed",
                status_code=302,
            )

        # Check if user exists
        user = get_user_by_email(user_info.email)

        if user:
            # Check if user is deleted
            if user.get("deleted_at"):
                frontend_url = settings.app_url or "http://localhost:5173"
                return RedirectResponse(
                    url=f"{frontend_url}?error=Account has been disabled",
                    status_code=302,
                )

            # Update user info from OIDC (name, admin status from groups)
            is_admin = oidc_service.is_admin_from_groups(user_info.groups)
            update_user(
                user["id"],
                name=user_info.name or user["name"],
                is_admin=1 if is_admin else user["is_admin"],  # Only upgrade, never downgrade
            )
            update_user_last_login(user["id"])
            user = get_user_by_id(user["id"])
        else:
            # Auto-provision new user
            is_admin = oidc_service.is_admin_from_groups(user_info.groups)
            user = create_user(
                email=user_info.email,
                name=user_info.name,
                auth_type="oidc",
                is_admin=is_admin,
            )
            update_user_last_login(user["id"])

        # Create session
        token = create_session_token(user["id"])

        # Redirect to frontend with session cookie
        frontend_url = settings.app_url or "http://localhost:5173"
        redirect = RedirectResponse(url=frontend_url, status_code=302)
        redirect.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=settings.session_duration_hours * 60 * 60,
        )
        # Clear the state cookie
        redirect.delete_cookie(key="oidc_state")
        return redirect

    except OIDCError as e:
        frontend_url = settings.app_url or "http://localhost:5173"
        return RedirectResponse(
            url=f"{frontend_url}?error={str(e)}",
            status_code=302,
        )
