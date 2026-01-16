from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.auth import require_auth
from app.services import audit
from app.services.auth import generate_api_key
from app.services.database import (
    create_api_key,
    list_api_keys_for_user,
    delete_api_key as db_delete_api_key,
    get_api_key_by_id,
)

router = APIRouter(prefix="/keys", tags=["keys"])


def _get_client_ip(request: Request | None) -> str:
    """Extract client IP from request."""
    if not request:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class CreateKeyRequest(BaseModel):
    name: str
    expires_in_days: int


@router.post("")
def create_key(request: CreateKeyRequest, http_request: Request = None, user: dict = Depends(require_auth)):
    """Create a new API key. The key is only shown once."""
    raw_key, key_hash = generate_api_key()

    api_key = create_api_key(
        user_id=user["id"],
        name=request.name,
        key_hash=key_hash,
        expires_in_days=request.expires_in_days,
    )

    audit.log_api_key_created(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        key_id=api_key["id"],
        key_name=request.name,
        expires_in_days=request.expires_in_days,
        ip_address=_get_client_ip(http_request),
    )

    # Return the raw key (only time it's visible)
    return {
        "id": api_key["id"],
        "name": api_key["name"],
        "key": raw_key,
        "expires_at": api_key["expires_at"],
        "created_at": api_key["created_at"],
    }


@router.get("")
def list_keys(user: dict = Depends(require_auth)):
    """List all API keys for the current user."""
    keys = list_api_keys_for_user(user["id"])
    # Don't expose key_hash
    return [
        {
            "id": k["id"],
            "name": k["name"],
            "expires_at": k["expires_at"],
            "created_at": k["created_at"],
            "last_used": k["last_used"],
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def delete_key(key_id: str, http_request: Request = None, user: dict = Depends(require_auth)):
    """Delete an API key."""
    api_key = get_api_key_by_id(key_id)
    if not api_key or api_key["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="API key not found")

    db_delete_api_key(key_id)

    audit.log_api_key_deleted(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        key_id=key_id,
        key_name=api_key["name"],
        ip_address=_get_client_ip(http_request),
    )

    return {"message": "API key deleted"}
