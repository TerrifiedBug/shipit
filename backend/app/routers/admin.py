from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.routers.auth import require_auth
from app.services import database as db
from app.services.auth import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(request: Request) -> dict:
    """Dependency that requires an authenticated admin user."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Request/Response models
class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    is_admin: bool = False


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    is_admin: Optional[bool] = None
    new_password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_admin: bool
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
                is_active=bool(u.get("is_active", True)),
                auth_type=u["auth_type"],
                created_at=u["created_at"],
                last_login=u["last_login"],
            )
            for u in users
        ]
    }


@router.post("/users")
def create_user(request: CreateUserRequest, admin: dict = Depends(require_admin)):
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

    # Create user with password_change_required flag
    user = db.create_user(
        email=request.email,
        name=request.name,
        auth_type="local",
        password_hash=hash_password(request.password),
        is_admin=request.is_admin,
        password_change_required=True,
    )

    # Audit log
    db.create_audit_log(
        user_id=admin["id"],
        action="create_user",
        target=request.email,
    )

    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        is_admin=bool(user["is_admin"]),
        is_active=bool(user.get("is_active", True)),
        auth_type=user["auth_type"],
        created_at=user["created_at"],
        last_login=user["last_login"],
    )


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    request: UpdateUserRequest,
    admin: dict = Depends(require_admin),
):
    """Update a user's details."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from removing their own admin status
    if user_id == admin["id"] and request.is_admin is False:
        raise HTTPException(
            status_code=400, detail="Cannot remove your own admin status"
        )

    # Check if this would leave no admins
    if request.is_admin is False and user.get("is_admin"):
        admin_count = db.count_admins()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot remove the last admin"
            )

    # Build update fields
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.is_admin is not None:
        updates["is_admin"] = 1 if request.is_admin else 0
    if request.new_password is not None:
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=400, detail="Password must be at least 8 characters"
            )
        updates["password_hash"] = hash_password(request.new_password)
        updates["password_change_required"] = 1

    if updates:
        db.update_user(user_id, **updates)

    # Audit log
    db.create_audit_log(
        user_id=admin["id"],
        action="update_user",
        target=user["email"],
    )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
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
    db.create_audit_log(
        user_id=admin["id"],
        action="delete_user",
        target=user["email"],
    )

    return {"message": f"User {user['email']} deleted"}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: str, admin: dict = Depends(require_admin)):
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
    db.create_audit_log(
        user_id=admin["id"],
        action="deactivate_user",
        target=user["email"],
    )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )


@router.post("/users/{user_id}/activate")
def activate_user(user_id: str, admin: dict = Depends(require_admin)):
    """Reactivate a deactivated user account."""
    user = db.get_user_by_id(user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=404, detail="User not found")

    db.reactivate_user(user_id)

    # Audit log
    db.create_audit_log(
        user_id=admin["id"],
        action="activate_user",
        target=user["email"],
    )

    updated = db.get_user_by_id(user_id)
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        is_admin=bool(updated["is_admin"]),
        is_active=bool(updated.get("is_active", True)),
        auth_type=updated["auth_type"],
        created_at=updated["created_at"],
        last_login=updated["last_login"],
    )
