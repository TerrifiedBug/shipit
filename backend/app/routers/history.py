import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.routers.auth import require_auth, require_viewer_or_above
from app.services.database import get_timestamp_history, get_upload, list_uploads
from app.services.opensearch import list_indexes

router = APIRouter(tags=["history"])


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    user: dict = Depends(require_viewer_or_above),
):
    """List past uploads with optional filtering.

    Accessible by all authenticated roles (admin, user, viewer).
    """
    uploads = list_uploads(limit=limit, offset=offset, status=status)

    # Get all existing indexes in one call (returns None if permission denied)
    existing_indexes = list_indexes(settings.index_prefix)

    # Enrich uploads with index_exists field
    for upload in uploads:
        if upload.get("index_name"):
            # None means we couldn't check (permission issue), so leave as None
            if existing_indexes is None:
                upload["index_exists"] = None
            else:
                upload["index_exists"] = upload["index_name"] in existing_indexes
        else:
            upload["index_exists"] = None

    return {"uploads": uploads, "limit": limit, "offset": offset}


def _validate_upload_id(upload_id: str) -> str:
    """Validate upload_id is a valid UUID to prevent path traversal attacks.

    Returns the canonical UUID string representation.
    Raises HTTPException if invalid.
    """
    try:
        return str(uuid.UUID(upload_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid upload ID format")


@router.get("/upload/{upload_id}/failures")
async def download_failures(
    upload_id: str,
    user: dict = Depends(require_viewer_or_above),
):
    """Download failed records for an upload as JSON.

    Accessible by all authenticated roles (admin, user, viewer).
    """
    safe_id = _validate_upload_id(upload_id)
    upload = get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["failure_count"] == 0:
        raise HTTPException(status_code=404, detail="No failed records")

    # Check for failures file
    failures_file = Path(settings.data_dir) / "failures" / f"{safe_id}.json"
    if not failures_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Failures file not found (may have been cleaned up)",
        )

    return FileResponse(
        failures_file,
        media_type="application/json",
        filename=f"{upload['filename']}_failures.json",
    )


@router.get("/timestamp-history")
async def get_timestamp_history_endpoint(user: dict = Depends(require_auth)):
    """Get user's recent timestamp configurations.

    Returns the last 5 timestamp configurations used by the current user,
    allowing quick reuse of previously successful format strings.
    """
    history = get_timestamp_history(user["id"])
    return {"history": history}
