from fastapi import APIRouter, HTTPException, Depends, Request

from app.config import settings
from app.services import audit
from app.services.opensearch import delete_index
from app.services.database import mark_index_deleted, untrack_index
from app.routers.auth import require_auth

router = APIRouter(prefix="/indexes", tags=["indexes"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.delete("/{index_name}")
def delete_index_endpoint(
    index_name: str,
    request: Request,
    user: dict = Depends(require_auth),
):
    """Delete an OpenSearch index."""
    # Validate index has required prefix
    if not index_name.startswith(settings.index_prefix):
        raise HTTPException(
            status_code=400,
            detail=f"Index must start with prefix '{settings.index_prefix}'",
        )

    # Delete the index
    success = delete_index(index_name)
    if not success:
        raise HTTPException(status_code=404, detail="Index not found")

    # Mark index as deleted in upload records so History reflects the deletion
    mark_index_deleted(index_name)

    # Remove from tracked indices (allows re-creation)
    untrack_index(index_name)

    # Audit log
    audit.log_index_deleted(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        index_name=index_name,
        ip_address=_get_client_ip(request),
    )

    return {"message": f"Index {index_name} deleted"}
