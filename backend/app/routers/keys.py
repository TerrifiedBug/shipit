from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import require_auth
from app.services.auth import generate_api_key
from app.services.database import (
    create_api_key,
    list_api_keys_for_user,
    delete_api_key as db_delete_api_key,
    get_api_key_by_id,
    create_audit_log,
)

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyRequest(BaseModel):
    name: str
    expires_in_days: int


@router.post("")
def create_key(request: CreateKeyRequest, user: dict = Depends(require_auth)):
    """Create a new API key. The key is only shown once."""
    raw_key, key_hash = generate_api_key()

    api_key = create_api_key(
        user_id=user["id"],
        name=request.name,
        key_hash=key_hash,
        expires_in_days=request.expires_in_days,
    )

    create_audit_log(
        user_id=user["id"],
        action="create_api_key",
        target=request.name,
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
def delete_key(key_id: str, user: dict = Depends(require_auth)):
    """Delete an API key."""
    api_key = get_api_key_by_id(key_id)
    if not api_key or api_key["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="API key not found")

    db_delete_api_key(key_id)

    create_audit_log(
        user_id=user["id"],
        action="revoke_api_key",
        target=api_key["name"],
    )

    return {"message": "API key deleted"}
