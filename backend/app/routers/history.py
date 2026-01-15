import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.services.database import get_upload, list_uploads
from app.services.opensearch import list_indexes

router = APIRouter(tags=["history"])


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    """List past uploads with optional filtering."""
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


def _sanitize_upload_id(upload_id: str) -> str:
    """Sanitize upload_id to prevent path traversal attacks."""
    return Path(upload_id).name


@router.get("/upload/{upload_id}/failures")
async def download_failures(upload_id: str):
    """Download failed records for an upload as JSON."""
    safe_id = _sanitize_upload_id(upload_id)
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
