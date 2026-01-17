"""Single-shot API upload endpoint for programmatic file ingestion."""

import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.routers.auth import require_auth_with_context
from app.services.database import (
    track_index,
    create_upload,
    start_ingestion,
    complete_ingestion,
)
from app.services.ingestion import ingest_file
from app.services.opensearch import validate_index_for_ingestion
from app.services.parser import detect_format, parse_preview

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.post("/upload")
async def api_upload(
    file: UploadFile = File(...),
    index_name: str = Form(...),
    format: Optional[str] = Form(None),
    timestamp_field: Optional[str] = Form(None),
    include_filename: Optional[bool] = Form(False),
    filename_field: Optional[str] = Form("source_file"),
    auth_context: dict = Depends(require_auth_with_context),
):
    """
    Single-shot API upload for programmatic file ingestion.

    This endpoint combines file upload and ingestion into a single call,
    suitable for automation and API-based workflows. Uploads are tracked
    in the history page for audit purposes.

    Args:
        file: File to upload (JSON array, NDJSON, CSV, TSV, LTSV, or syslog)
        index_name: Target index name (without prefix - will be prefixed with shipit-)
        format: Optional format override (json_array, ndjson, csv, tsv, ltsv, syslog).
                If not specified, format is auto-detected.
        timestamp_field: Optional field to use as @timestamp. Must exist in the data.
        include_filename: If true, add source filename to each record.
        filename_field: Name of the field to store filename (default: source_file).

    Returns:
        {
            "status": "completed" | "completed_with_errors",
            "index_name": "full-index-name-with-prefix",
            "records_ingested": int,
            "records_failed": int,
            "duration_seconds": float,
            "upload_id": str,  # ID for tracking in history
            "errors": [...]  # present if records_failed > 0
        }

    Raises:
        400: Invalid parameters, file parsing error, or blocked by strict index mode
        401: Authentication required
    """
    start_time = time.time()
    user = auth_context["user"]
    upload_id = str(uuid.uuid4())
    filename = file.filename or "uploaded_file"
    file_size = 0

    # Build full index name with prefix
    full_index_name = f"{settings.index_prefix}{index_name}"

    # Validate index (check strict mode protection)
    try:
        index_meta = validate_index_for_ingestion(full_index_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Save uploaded file to temp location (must be under data_dir for path validation)
    suffix = Path(file.filename).suffix if file.filename else ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.data_dir) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        temp_path = Path(tmp.name)
        file_size = len(content)

    try:
        # Detect or use specified format
        if format:
            file_format = format
        else:
            file_format = detect_format(temp_path)

        # Create upload history record (for tracking in History page)
        create_upload(
            upload_id=upload_id,
            filenames=[filename],
            file_sizes=[file_size],
            file_format=file_format,
            user_id=user["id"],
            upload_method="api",
            api_key_name=auth_context.get("api_key_name"),
        )

        # Validate timestamp field if specified
        if timestamp_field:
            preview = parse_preview(temp_path, file_format, limit=10)
            if not preview:
                complete_ingestion(upload_id, 0, 0, "File appears to be empty or unparseable")
                raise HTTPException(
                    status_code=400,
                    detail="File appears to be empty or unparseable",
                    headers={"X-Error-Type": "empty_file"},
                )

            available_fields = list(preview[0].keys())
            if timestamp_field not in available_fields:
                complete_ingestion(upload_id, 0, 0, f"Timestamp field '{timestamp_field}' not found")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "detail": f"Timestamp field '{timestamp_field}' not found in data",
                        "available_fields": available_fields[:20],  # Limit for readability
                    },
                )

        # Build field mappings for filename inclusion
        field_mappings = {}
        if include_filename and filename_field:
            # This is handled by ingest_file via include_filename parameter
            pass

        # Start ingestion tracking
        start_ingestion(
            upload_id=upload_id,
            index_name=full_index_name,
            timestamp_field=timestamp_field,
            field_mappings={},
            excluded_fields=[],
            total_records=0,  # Unknown until ingestion starts
        )

        # Perform ingestion
        result = ingest_file(
            file_path=temp_path,
            file_format=file_format,
            index_name=full_index_name,
            timestamp_field=timestamp_field,
            include_filename=include_filename,
            filename_field=filename_field if include_filename else None,
        )

        # Track index if it's new
        if index_meta.get("requires_tracking"):
            track_index(full_index_name, user_id=user["id"])

        # Complete ingestion tracking
        error_message = None
        if result.failed > 0:
            error_message = f"{result.failed} records failed to ingest"
        complete_ingestion(upload_id, result.success, result.failed, error_message)

        # Build response
        duration = time.time() - start_time

        response = {
            "status": "completed" if result.failed == 0 else "completed_with_errors",
            "index_name": full_index_name,
            "records_ingested": result.success,
            "records_failed": result.failed,
            "duration_seconds": round(duration, 2),
            "upload_id": upload_id,
        }

        if result.failed > 0:
            # Include first 10 errors for debugging
            response["errors"] = result.failed_records[:10]

        return response

    except HTTPException:
        raise
    except Exception as e:
        # Record failure in history
        complete_ingestion(upload_id, 0, 0, str(e))
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process file: {str(e)}",
        )
    finally:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
