import logging

from fastapi import APIRouter, HTTPException, Depends, Request

from app.config import settings
from app.services import audit
from app.services.opensearch import delete_index, get_client
from app.services.database import mark_index_deleted, untrack_index
from app.services.request_utils import get_client_ip
from app.routers.auth import require_auth, require_user_or_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexes", tags=["indexes"])


@router.get("/list")
def list_indices(user: dict = Depends(require_auth)):
    """List available indices for dropdown selection.

    Returns indices that match the configured prefix.
    """
    try:
        client = get_client()
        prefix = settings.index_prefix
        # Use cat indices API to get index names
        response = client.cat.indices(index=f"{prefix}*", format="json")
        indices = sorted([idx["index"] for idx in response])
        return {"indices": indices}
    except Exception as e:
        logger.warning(f"Failed to list indices: {e}")
        return {"indices": []}


@router.delete("/{index_name}")
def delete_index_endpoint(
    index_name: str,
    request: Request,
    user: dict = Depends(require_user_or_admin),
):
    """Delete an OpenSearch index.

    Requires user or admin role. Viewers cannot delete indices.
    """
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
        ip_address=get_client_ip(request),
    )

    return {"message": f"Index {index_name} deleted"}
