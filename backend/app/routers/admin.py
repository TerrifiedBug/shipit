from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.routers.auth import require_auth
from app.services import audit, database as db
from app.services.auth import hash_password
from app.services.request_utils import get_client_ip

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(request: Request) -> dict:
    """Dependency that requires an authenticated admin user."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Check both role and legacy is_admin field for backward compatibility
    is_admin = user.get("role") == "admin" or user.get("is_admin")
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Valid roles for the application
VALID_ROLES = ("admin", "user", "viewer")


def _get_role_from_user(user: dict) -> str:
    """Get role from user dict, with backward compatibility for is_admin."""
    if user.get("role"):
        return user["role"]
    return "admin" if user.get("is_admin") else "user"


# Request/Response models
class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    is_admin: bool = False  # Deprecated, use role instead
    role: Optional[str] = None  # New role field (admin, user, viewer)


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    is_admin: Optional[bool] = None  # Deprecated, use role instead
    role: Optional[str] = None  # New role field
    new_password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_admin: bool  # Kept for backward compatibility
    role: str  # New field: admin, user, or viewer
    is_active: bool
    auth_type: str
    created_at: str
    last_login: Optional[str]


@router.get("/users")
def list_users(admin: dict = Depends(require_admin)):
    """List all active users."""
    users = db.list_users(include_deleted=False)
    return {
        "users": [
            UserResponse(
                id=u["id"],
                email=u["email"],
                name=u["name"],
                is_admin=bool(u["is_admin"]),
                role=_get_role_from_user(u),
                is_active=bool(u.get("is_active", True)),
                auth_type=u["auth_type"],
                created_at=u["created_at"],
                last_login=u["last_login"],
            )
            for u in users
        ]
    }


@router.post("/users")
def create_user(request: CreateUserRequest, http_request: Request = None, admin: dict = Depends(require_admin)):
    """Create a new local user."""
    # Check email uniqueness
    existing = db.get_user_by_email(request.email)
    if existing:
        if existing.get("deleted_at"):
            raise HTTPException(
                status_code=400,
                detail="A deleted user exists with this email. Cannot reuse.",
            )
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate password
    if len(request.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    # Determine role: explicit role takes precedence, then is_admin, then default 'user'
    role = request.role
    if role:
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
            )
    elif request.is_admin:
        role = "admin"
    else:
        role = "user"

    # Create user with password_change_required flag
    user = db.create_user(
        email=request.email,
        name=request.name,
        auth_type="local",
        password_hash=hash_password(request.password),
        role=role,
        password_change_required=True,
    )

    # Audit log
    audit.log_user_created(
        actor_id=admin["id"],
        actor_name=admin.get("email", ""),
        target_user_id=user["id"],
        target_email=request.email,
        is_admin=(role == "admin"),
        ip_address=get_client_ip(http_request) if http_request else None,
    )

    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        is_admin=bool(user["is_admin"]),
        role=_get_role_from_user(user),
        is_active=bool(user.get("is_active", True)),
        auth_type=user["auth_type"],
        created_at=user["created_at"],
        last_login=user["last_login"],
    )


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    request: UpdateUserRequest,
    http_request: Request = None,
    admin: dict = Depends(require_admin),
):
    """Update a user's details."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    # Determine target role (explicit role takes precedence, then is_admin)
    target_role = request.role
    if target_role:
        if target_role not in VALID_ROLES:
            raise HTTPException(
                status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
            )
    elif request.is_admin is not None:
        target_role = "admin" if request.is_admin else "user"

    current_role = _get_role_from_user(user)

    # Prevent admin from removing their own admin status
    if user_id == admin["id"] and target_role and target_role != "admin":
        raise HTTPException(
            status_code=400, detail="Cannot remove your own admin status"
        )

    # Check if this would leave no admins
    if target_role and target_role != "admin" and current_role == "admin":
        admin_count = db.count_admins()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot remove the last admin"
            )

    # Build update fields and track changes for audit
    updates = {}
    changes = {}
    if request.name is not None:
        updates["name"] = request.name
        if user.get("name") != request.name:
            changes["name"] = {"from": user.get("name"), "to": request.name}

    if target_role and target_role != current_role:
        updates["role"] = target_role
        updates["is_admin"] = 1 if target_role == "admin" else 0
        changes["role"] = {"from": current_role, "to": target_role}

    if request.new_password is not None:
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=400, detail="Password must be at least 8 characters"
            )
        updates["password_hash"] = hash_password(request.new_password)
        updates["password_change_required"] = 1
        changes["password"] = "reset"

    if updates:
        db.update_user(user_id, **updates)

    # Audit log
    if changes:
        audit.log_user_modified(
            actor_id=admin["id"],
            actor_name=admin.get("email", ""),
            target_user_id=user_id,
            target_email=user["email"],
            changes=changes,
            ip_address=get_client_ip(http_request) if http_request else None,
        )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        role=_get_role_from_user(updated),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )


@router.delete("/users/{user_id}")
def delete_user(user_id: str, http_request: Request = None, admin: dict = Depends(require_admin)):
    """Soft delete a user."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deleting themselves
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    # Check if this would leave no admins
    if user.get("is_admin"):
        admin_count = db.count_admins()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot delete the last admin"
            )

    # Soft delete
    db.update_user(user_id, deleted_at=datetime.utcnow().isoformat())

    # Audit log
    audit.log_user_deleted(
        actor_id=admin["id"],
        actor_name=admin.get("email", ""),
        target_user_id=user_id,
        target_email=user["email"],
        ip_address=get_client_ip(http_request) if http_request else None,
    )

    return {"message": f"User {user['email']} deleted"}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: str, http_request: Request = None, admin: dict = Depends(require_admin)):
    """Deactivate a user account (prevent login without deleting)."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deactivating themselves
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    # Check if this would leave no active admins
    if user.get("is_admin") and user.get("is_active", True):
        active_admin_count = sum(
            1 for u in db.list_users(include_deleted=False)
            if u.get("is_admin") and u.get("is_active", True)
        )
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot deactivate the last active admin"
            )

    db.deactivate_user(user_id)

    # Audit log
    audit.log_user_modified(
        actor_id=admin["id"],
        actor_name=admin.get("email", ""),
        target_user_id=user_id,
        target_email=user["email"],
        changes={"is_active": {"from": True, "to": False}},
        ip_address=get_client_ip(http_request) if http_request else None,
    )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        role=_get_role_from_user(updated),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )


@router.post("/users/{user_id}/activate")
def activate_user(user_id: str, http_request: Request = None, admin: dict = Depends(require_admin)):
    """Reactivate a deactivated user account."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    db.reactivate_user(user_id)

    # Audit log
    audit.log_user_modified(
        actor_id=admin["id"],
        actor_name=admin.get("email", ""),
        target_user_id=user_id,
        target_email=user["email"],
        changes={"is_active": {"from": False, "to": True}},
        ip_address=get_client_ip(http_request) if http_request else None,
    )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        role=_get_role_from_user(updated),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )


@router.get("/audit-shipping/status")
def get_audit_shipping_status(admin: dict = Depends(require_admin)):
    """Get audit log shipping configuration status (admin only).

    Returns the current configuration for audit log shipping to help
    diagnose connectivity or configuration issues.
    """
    from app.services.audit_shipping import AUDIT_INDEX_NAME, is_shipping_enabled

    status = {
        "enabled": is_shipping_enabled(),
        "opensearch": {
            "enabled": settings.audit_log_to_opensearch,
            "index_name": AUDIT_INDEX_NAME,
        },
        "http_endpoint": {
            "enabled": bool(settings.audit_log_endpoint),
            "url": settings.audit_log_endpoint[:50] + "..." if settings.audit_log_endpoint and len(settings.audit_log_endpoint) > 50 else settings.audit_log_endpoint,
            "has_token": bool(settings.audit_log_endpoint_token),
            "has_headers": bool(settings.audit_log_endpoint_headers),
        },
    }

    # If OpenSearch shipping is enabled, try to check index existence
    if settings.audit_log_to_opensearch:
        try:
            from app.services.audit_shipping import _get_opensearch_client

            client = _get_opensearch_client()
            index_exists = client.indices.exists(index=AUDIT_INDEX_NAME)
            status["opensearch"]["index_exists"] = index_exists

            if index_exists:
                # Get document count
                count_result = client.count(index=AUDIT_INDEX_NAME)
                status["opensearch"]["document_count"] = count_result.get("count", 0)
        except Exception as e:
            status["opensearch"]["error"] = str(e)

    return status


@router.post("/audit-shipping/test")
def test_audit_shipping(http_request: Request, admin: dict = Depends(require_admin)):
    """Send a test audit log to verify shipping is working (admin only).

    Creates a test audit event and ships it to configured destinations.
    Returns the result of the shipping attempt.
    """
    from app.services.audit_shipping import is_shipping_enabled

    if not is_shipping_enabled():
        raise HTTPException(
            status_code=400,
            detail="No audit log shipping destinations configured. Set AUDIT_LOG_TO_OPENSEARCH=true or configure AUDIT_LOG_ENDPOINT.",
        )

    # Create a test audit log entry
    test_log = db.create_audit_log(
        event_type="audit_shipping_test",
        actor_id=admin["id"],
        actor_name=admin.get("email", ""),
        target_type="system",
        target_id="audit-shipping",
        details={"test": True, "message": "Audit shipping test triggered by admin"},
        ip_address=get_client_ip(http_request),
    )

    return {
        "success": True,
        "message": "Test audit log created and shipped",
        "audit_log_id": test_log.get("id"),
    }
