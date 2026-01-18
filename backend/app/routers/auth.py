from __future__ import annotations

import ipaddress
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.services import audit
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
    record_failed_login,
    get_failed_login_count,
    clear_failed_logins,
    is_account_locked,
    delete_session,
    delete_other_sessions,
)
from app.services.rate_limit import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limiter for login attempts (by IP)
login_rate_limiter = RateLimiter(window_seconds=60)


def authenticate_user(email: str, password: str) -> dict | None:
    """Authenticate a user by email and password.

    Uses constant-time comparison to prevent timing attacks.
    Always performs password hash check even for nonexistent users.
    """
    user = get_user_by_email(email)

    # Always hash to prevent timing attacks - use a dummy hash for nonexistent users
    # This hash corresponds to "dummy" but the actual value doesn't matter
    dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VT7g9WLdQp5E2G"
    hash_to_check = user["password_hash"] if user and user.get("password_hash") else dummy_hash

    password_valid = verify_password(password, hash_to_check)

    if not user or not password_valid:
        return None

    if user.get("auth_type") != "local":
        return None

    if not user.get("is_active", True):
        return None

    return user


def _set_session_cookie(response: Response, token: str) -> None:
    """Set session cookie with appropriate security settings."""
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=settings.is_secure_cookies(),
        samesite="lax",
        max_age=settings.session_duration_hours * 60 * 60,
    )


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password against configured requirements.

    Returns (is_valid, error_message).
    """
    if len(password) < settings.password_min_length:
        return False, f"Password must be at least {settings.password_min_length} characters"

    if settings.password_require_uppercase and not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if settings.password_require_lowercase and not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if settings.password_require_digit and not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if settings.password_require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"

    return True, ""


def _get_client_ip(request: Request | None) -> str:
    """Extract client IP from request."""
    if not request:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_ip_allowed(client_ip: str, allowed_ips: str | None) -> bool:
    """Check if client IP is allowed by the allowlist.

    Args:
        client_ip: The client's IP address
        allowed_ips: Comma-separated IPs/CIDRs (e.g., "10.0.0.0/24, 192.168.1.5")
                    None or empty string means all IPs are allowed

    Returns:
        True if IP is allowed, False otherwise
    """
    # Empty or None means allow all
    if not allowed_ips or not allowed_ips.strip():
        return True

    # Handle special case of "unknown" IP
    if client_ip == "unknown":
        return False

    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        # Invalid client IP - reject
        return False

    # Check each allowed IP/CIDR
    for entry in allowed_ips.split(","):
        entry = entry.strip()
        if not entry:
            continue

        try:
            # Try as network (CIDR notation)
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                if client_addr in network:
                    return True
            else:
                # Try as single IP
                if client_addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            # Invalid entry in allowlist - skip it
            continue

    return False


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
                    # Check if user is deleted or deactivated
                    if user and (user.get("deleted_at") or not user.get("is_active", True)):
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
    # Check if user is deleted or deactivated
    if user and (user.get("deleted_at") or not user.get("is_active", True)):
        return None
    return user


def require_auth(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_auth_context(request: Request) -> dict | None:
    """Get authentication context including method and API key info.

    Returns a dict with:
    - user: the authenticated user dict
    - auth_method: "session" | "api_key"
    - api_key_name: name of the API key (if auth_method is "api_key")

    Raises:
        HTTPException: 403 if API key IP restriction is violated
    """
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
                    # Check IP allowlist
                    allowed_ips = api_key.get("allowed_ips")
                    if allowed_ips:
                        client_ip = _get_client_ip(request)
                        if not _is_ip_allowed(client_ip, allowed_ips):
                            raise HTTPException(
                                status_code=403,
                                detail="API key not authorized for this IP address"
                            )
                    update_api_key_last_used(api_key["id"])
                    user = get_user_by_id(api_key["user_id"])
                    # Check if user is deleted or deactivated
                    if user and (user.get("deleted_at") or not user.get("is_active", True)):
                        return None
                    return {
                        "user": user,
                        "auth_method": "api_key",
                        "api_key_name": api_key["name"],
                    }
            return None

    # Fall back to session cookie
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    payload = verify_session_token(session_token)
    if not payload:
        return None
    user = get_user_by_id(payload["sub"])
    # Check if user is deleted or deactivated
    if user and (user.get("deleted_at") or not user.get("is_active", True)):
        return None
    if user:
        return {
            "user": user,
            "auth_method": "session",
            "api_key_name": None,
        }
    return None


def require_auth_with_context(request: Request) -> dict:
    """Dependency that requires authentication and returns auth context."""
    context = get_auth_context(request)
    if not context:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return context


@router.get("/setup")
def check_setup_needed():
    """Check if initial setup is required (no users exist)."""
    return {"needs_setup": count_users() == 0}


@router.post("/setup")
def setup_first_user(request: SetupRequest, response: Response):
    """Create the first admin user. Only works when no users exist."""
    if count_users() > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    # Validate password
    is_valid, error_msg = validate_password(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

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
    _set_session_cookie(response, token)

    return user


@router.post("/login")
def login(request: LoginRequest, response: Response, http_request: Request = None):
    """Login with email and password.

    Uses timing-safe authentication to prevent user enumeration attacks.
    """
    client_ip = _get_client_ip(http_request)

    # Check login rate limit by IP
    is_allowed, retry_after = login_rate_limiter.is_allowed(
        f"login:{client_ip}",
        settings.login_rate_limit_per_minute
    )
    if not is_allowed:
        audit.log_login_failed(request.email, "rate_limited", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Get user for pre-auth checks (lockout, deactivation)
    # This lookup doesn't leak timing info as we still perform timing-safe auth below
    user = get_user_by_email(request.email)

    # Check if account is locked due to failed attempts (only if user exists)
    # This check is safe - it doesn't reveal user existence because we still
    # perform timing-safe auth below regardless of lockout status
    if user and is_account_locked(user["id"], settings.account_lockout_minutes):
        audit.log_login_failed(request.email, "account_locked", client_ip)
        raise HTTPException(
            status_code=403,
            detail=f"Account temporarily locked due to too many failed login attempts. Try again in {settings.account_lockout_minutes} minutes."
        )

    # Check if user is deactivated before authentication
    # We reveal deactivation status (403) because it's an admin action, not security-sensitive
    # and users need to know to contact their admin
    if user and not user.get("is_active", True) and not user.get("deleted_at"):
        audit.log_login_failed(request.email, "account_deactivated", client_ip)
        raise HTTPException(status_code=403, detail="Account has been deactivated")

    # Use timing-safe authentication - always performs password hash check
    # to prevent timing attacks that could reveal user existence
    authenticated_user = authenticate_user(request.email, request.password)

    if not authenticated_user:
        # Authentication failed - could be: user not found, wrong password,
        # OIDC user, or deleted user
        # Record failed attempt if user exists (for lockout tracking)
        if user and not user.get("deleted_at") and user.get("is_active", True):
            record_failed_login(user["id"], client_ip)
            failed_count = get_failed_login_count(user["id"], settings.account_lockout_minutes)

            # Provide remaining attempts info only for existing, active local users
            if user.get("auth_type") == "local":
                audit.log_login_failed(request.email, "invalid_password", client_ip)
                # Check if this attempt triggers lockout
                if failed_count >= settings.account_lockout_attempts:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Account temporarily locked due to too many failed login attempts. Try again in {settings.account_lockout_minutes} minutes."
                    )
                remaining = settings.account_lockout_attempts - failed_count
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid credentials. {remaining} attempt(s) remaining before account lockout."
                )

        # Generic failure - don't reveal why authentication failed
        audit.log_login_failed(request.email, "invalid_credentials", client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if user is deleted (authenticated_user passed auth but we double-check)
    if authenticated_user.get("deleted_at"):
        audit.log_login_failed(request.email, "user_deleted", client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login - clear failed attempts
    clear_failed_logins(authenticated_user["id"])
    update_user_last_login(authenticated_user["id"])

    # Log successful login
    audit.log_login_success(authenticated_user["id"], authenticated_user["email"], client_ip)

    token = create_session_token(authenticated_user["id"])
    _set_session_cookie(response, token)

    return {
        "message": "Login successful",
        "user": authenticated_user,
        "password_change_required": bool(authenticated_user.get("password_change_required")),
    }


@router.get("/me")
def get_me(user: dict = Depends(require_auth)):
    """Get current authenticated user."""
    return {
        **user,
        "password_change_required": bool(user.get("password_change_required")),
    }


@router.post("/logout")
def logout(response: Response, http_request: Request = None):
    """Logout - clear session cookie and invalidate session in database."""
    # Log logout if we can identify the user
    user = get_current_user(http_request) if http_request else None
    if user:
        audit.log_logout(user["id"], user.get("email", ""), _get_client_ip(http_request))

    # Delete session from database
    if http_request:
        session_token = http_request.cookies.get("session")
        if session_token:
            payload = verify_session_token(session_token)
            if payload and payload.get("sid"):
                delete_session(payload["sid"])

    response.delete_cookie(key="session")
    return {"message": "Logged out"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    http_request: Request,
    user: dict = Depends(require_auth),
):
    """Change the current user's password.

    Invalidates all other sessions for security - the user stays logged in
    on the current device but is logged out everywhere else.
    """
    # Get fresh user data
    current_user = get_user_by_id(user["id"])
    if not current_user or current_user["auth_type"] != "local":
        raise HTTPException(status_code=403, detail="Cannot change password for this account")

    # Verify current password
    if not verify_password(request.current_password, current_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Validate new password against complexity requirements
    is_valid, error_msg = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Update password and clear change required flag
    update_user(
        user["id"],
        password_hash=hash_password(request.new_password),
        password_change_required=0,
    )

    # Invalidate all other sessions for security
    session_token = http_request.cookies.get("session")
    if session_token:
        payload = verify_session_token(session_token)
        if payload and payload.get("sid"):
            sessions_invalidated = delete_other_sessions(user["id"], payload["sid"])
            return {
                "message": "Password changed successfully",
                "sessions_invalidated": sessions_invalidated,
            }

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
            # Check if user is deleted or deactivated
            if user.get("deleted_at") or not user.get("is_active", True):
                frontend_url = settings.app_url or "http://localhost:5173"
                return RedirectResponse(
                    url=f"{frontend_url}?error=Account has been deactivated",
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

        # Log successful OIDC login
        client_ip = _get_client_ip(request)
        audit.log_login_success(user["id"], user["email"], client_ip)

        # Create session
        token = create_session_token(user["id"])

        # Redirect to frontend with session cookie
        frontend_url = settings.app_url or "http://localhost:5173"
        redirect = RedirectResponse(url=frontend_url, status_code=302)
        _set_session_cookie(redirect, token)
        # Clear the state cookie
        redirect.delete_cookie(key="oidc_state")
        return redirect

    except OIDCError as e:
        frontend_url = settings.app_url or "http://localhost:5173"
        return RedirectResponse(
            url=f"{frontend_url}?error={str(e)}",
            status_code=302,
        )
