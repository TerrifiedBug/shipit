from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.auth import require_auth, require_user_or_admin
from app.services import audit
from app.services.auth import generate_api_key
from app.services.request_utils import get_client_ip
from app.services.database import (
    create_api_key,
    list_api_keys_for_user,
    delete_api_key as db_delete_api_key,
    get_api_key_by_id,
)

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyRequest(BaseModel):
    name: str
    expires_in_days: int
    allowed_ips: str | None = None  # Comma-separated IPs/CIDRs


@router.post("")
def create_key(request: CreateKeyRequest, http_request: Request = None, user: dict = Depends(require_user_or_admin)):
    """Create a new API key. The key is only shown once.

    Requires user or admin role. Viewers cannot create API keys.

    Args:
        name: Human-readable name for the key
        expires_in_days: Number of days until expiration
        allowed_ips: Optional comma-separated IPs/CIDRs (e.g., "10.0.0.0/24, 192.168.1.5")
    """
    raw_key, key_hash = generate_api_key()

    # Normalize allowed_ips: strip whitespace, convert empty string to None
    allowed_ips = request.allowed_ips.strip() if request.allowed_ips else None
    if allowed_ips == "":
        allowed_ips = None

    api_key = create_api_key(
        user_id=user["id"],
        name=request.name,
        key_hash=key_hash,
        expires_in_days=request.expires_in_days,
        allowed_ips=allowed_ips,
    )

    audit.log_api_key_created(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        key_id=api_key["id"],
        key_name=request.name,
        expires_in_days=request.expires_in_days,
        ip_address=get_client_ip(http_request),
    )

    # Return the raw key (only time it's visible)
    return {
        "id": api_key["id"],
        "name": api_key["name"],
        "key": raw_key,
        "expires_at": api_key["expires_at"],
        "created_at": api_key["created_at"],
        "allowed_ips": api_key.get("allowed_ips"),
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
            "allowed_ips": k.get("allowed_ips"),
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def delete_key(key_id: str, http_request: Request = None, user: dict = Depends(require_user_or_admin)):
    """Delete an API key.

    Requires user or admin role. Viewers cannot manage API keys.
    """
    api_key = get_api_key_by_id(key_id)
    if not api_key or api_key["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="API key not found")

    db_delete_api_key(key_id)

    audit.log_api_key_deleted(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        key_id=key_id,
        key_name=api_key["name"],
        ip_address=get_client_ip(http_request),
    )

    return {"message": "API key deleted"}
