from fastapi import APIRouter, HTTPException, Depends, Request

from app.config import settings
from app.services.opensearch import delete_index
from app.services.database import create_audit_log, mark_index_deleted, untrack_index
from app.routers.auth import require_auth

router = APIRouter(prefix="/indexes", tags=["indexes"])


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
    create_audit_log(
        user_id=user["id"],
        action="delete_index",
        target=index_name,
    )

    return {"message": f"Index {index_name} deleted"}
