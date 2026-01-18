from __future__ import annotations

import asyncio
import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.routers.auth import require_auth
from app.models import FieldInfo, IngestRequest, PreviewResponse, UploadResponse
from app.services import database as db
from app.services.ingestion import count_records, ingest_file
from app.services.opensearch import validate_index_name, validate_index_for_ingestion
from app.services.parser import detect_format, infer_fields, parse_preview, validate_field_count, parse_with_pattern
from app.services.rate_limit import check_upload_rate_limit

router = APIRouter()

# In-memory store for upload file paths and preview data
# (Database stores persistent metadata, this stores transient data)
_upload_cache: dict[str, dict] = {}

# Progress tracking for active ingestions
_ingestion_progress: dict[str, dict] = {}

# Cancellation flags for active ingestions
_cancellation_flags: dict[str, bool] = {}


def _get_upload_dir() -> Path:
    """Get the upload directory, creating it if needed."""
    upload_dir = Path(settings.data_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _get_failures_dir() -> Path:
    """Get the failures directory, creating it if needed."""
    failures_dir = Path(settings.data_dir) / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    return failures_dir


def _sanitize_filename(filename: str | None) -> str:
    """Sanitize filename to prevent path traversal attacks.

    Strips any directory components (e.g., '../', '/etc/') and returns
    only the base filename.
    """
    if not filename:
        return ""
    # Path.name extracts just the filename, stripping any directory components
    return Path(filename).name


def _validate_upload_id(upload_id: str) -> str:
    """Validate upload_id is a valid UUID to prevent path traversal attacks.

    Returns the canonical UUID string representation.
    Raises HTTPException if invalid.
    """
    try:
        # Parse and re-serialize to get canonical form
        return str(uuid.UUID(upload_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid upload ID format")


def _get_client_ip(request: Request | None) -> str:
    """Extract client IP from request, checking X-Forwarded-For for proxies."""
    if not request:
        return "unknown"
    # Check X-Forwarded-For header (set by reverse proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()
    # Fall back to direct client IP
    return request.client.host if request.client else "unknown"


@router.post("/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...), request: Request = None):
    """Upload one or more files and return preview data."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Check rate limit
    user = getattr(request.state, "user", None) if request else None
    user_id = user["id"] if user else None
    client_ip = _get_client_ip(request)

    is_allowed, retry_after = check_upload_rate_limit(user_id, client_ip)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait before uploading more files.",
            headers={"Retry-After": str(retry_after)},
        )

    # Sanitize and validate all filenames
    valid_extensions = ('.json', '.csv', '.tsv', '.ltsv', '.log', '.txt', '.ndjson', '.jsonl')
    sanitized_filenames: list[str] = []

    for file in files:
        # Sanitize filename to prevent path traversal
        safe_name = _sanitize_filename(file.filename)
        if not safe_name:
            raise HTTPException(status_code=400, detail="No filename provided")
        if not safe_name.lower().endswith(valid_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {safe_name}. Supported: JSON, NDJSON, CSV, TSV, LTSV, TXT, LOG"
            )
        sanitized_filenames.append(safe_name)

    # Check for duplicate filenames
    seen_filenames = set()
    for safe_name in sanitized_filenames:
        if safe_name in seen_filenames:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate filename: {safe_name}"
            )
        seen_filenames.add(safe_name)

    upload_id = str(uuid.uuid4())
    upload_dir = _get_upload_dir() / upload_id  # Create subdirectory for this upload
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[Path] = []
    file_sizes: list[int] = []
    total_size = 0

    try:
        for file, safe_name in zip(files, sanitized_filenames):
            file_path = upload_dir / safe_name
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            await file.close()

            size = file_path.stat().st_size
            saved_files.append(file_path)
            file_sizes.append(size)
            total_size += size

        # Check total size limit
        max_size_bytes = settings.max_file_size_mb * 1024 * 1024
        if total_size > max_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Total file size exceeds maximum of {settings.max_file_size_mb} MB"
            )

        # Detect format from first file
        file_format = detect_format(saved_files[0])

        # Verify all files have same format
        for fp in saved_files[1:]:
            if detect_format(fp) != file_format:
                raise HTTPException(
                    status_code=400,
                    detail="All files must be the same format"
                )

        # Get preview from each file (5 records each for multi-file, 100 for single)
        preview_limit = 5 if len(saved_files) > 1 else 100
        preview_records: list[dict] = []

        for fp in saved_files:
            records = parse_preview(fp, file_format, limit=preview_limit)
            preview_records.extend(records)

        # Validate field count per document
        if settings.max_fields_per_document > 0:
            is_valid, max_found = validate_field_count(preview_records, settings.max_fields_per_document)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document contains {max_found} fields, which exceeds the maximum of {settings.max_fields_per_document}. "
                           f"Please reduce the number of fields or contact an administrator."
                )

        fields = infer_fields(preview_records)

        # Create database record (use sanitized filenames)
        user = getattr(request.state, "user", None) if request else None
        db.create_upload(
            upload_id=upload_id,
            filenames=sanitized_filenames,
            file_sizes=file_sizes,
            file_format=file_format,
            user_id=user["id"] if user else None,
        )

        # Cache file paths (all of them)
        _upload_cache[upload_id] = {
            "file_paths": [str(fp) for fp in saved_files],
            "preview": preview_records,
            "fields": fields,
        }
    except HTTPException:
        # Clean up on error
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to process files: {str(e)}")

    return UploadResponse(
        upload_id=upload_id,
        filename=", ".join(sanitized_filenames) if len(sanitized_filenames) > 1 else sanitized_filenames[0],
        filenames=sanitized_filenames,
        file_size=total_size,
        file_format=file_format,
        preview=preview_records[:100],  # Limit preview in response
        fields=[FieldInfo(**f) for f in fields],
    )


@router.get("/upload/{upload_id}/preview", response_model=PreviewResponse)
async def get_preview(upload_id: str):
    """Get preview data for previously uploaded file(s)."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Get from cache or re-parse
    cache = _upload_cache.get(safe_id)
    if cache:
        preview = cache["preview"]
        fields = cache["fields"]
    else:
        # Re-parse if not in cache (e.g., after server restart)
        # Files are stored in a subdirectory named by upload_id
        upload_dir = _get_upload_dir() / safe_id
        filenames = upload.get("filenames", [upload["filename"]])

        if not upload_dir.exists():
            raise HTTPException(status_code=404, detail="Uploaded files no longer exist")

        # Parse preview from all files
        preview_limit = 5 if len(filenames) > 1 else 100
        preview = []
        file_paths = []

        for filename in filenames:
            file_path = upload_dir / filename
            if file_path.exists():
                records = parse_preview(file_path, upload["file_format"], limit=preview_limit)
                preview.extend(records)
                file_paths.append(str(file_path))

        if not file_paths:
            raise HTTPException(status_code=404, detail="Uploaded files no longer exist")

        # Validate field count per document
        if settings.max_fields_per_document > 0:
            is_valid, max_found = validate_field_count(preview, settings.max_fields_per_document)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document contains {max_found} fields, which exceeds the maximum of {settings.max_fields_per_document}. "
                           f"Please reduce the number of fields or contact an administrator."
                )

        fields = infer_fields(preview)
        _upload_cache[safe_id] = {
            "file_paths": file_paths,
            "preview": preview,
            "fields": fields,
        }

    return PreviewResponse(
        upload_id=safe_id,
        filename=upload["filename"],
        file_format=upload["file_format"],
        preview=preview[:100],
        fields=[FieldInfo(**f) for f in fields],
    )


@router.post("/upload/{upload_id}/reparse")
async def reparse_upload(
    upload_id: str,
    format: str = Form(...),
    pattern_id: str | None = Form(None),
    user: dict = Depends(require_auth),
):
    """Re-parse uploaded file with a different format."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Get file paths from cache or reconstruct from database
    cache = _upload_cache.get(safe_id)
    if cache and "file_paths" in cache:
        file_paths = [Path(fp) for fp in cache["file_paths"]]
    else:
        # Fallback: reconstruct from database
        upload_dir = _get_upload_dir() / safe_id
        filenames = upload.get("filenames", [upload["filename"]])
        file_paths = [upload_dir / fn for fn in filenames]

    # Verify files exist
    existing_paths = [fp for fp in file_paths if fp.exists()]
    if not existing_paths:
        raise HTTPException(status_code=404, detail="Uploaded files no longer exist")

    # Validate format
    valid_formats = ["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog", "logfmt", "raw", "custom"]
    if format not in valid_formats:
        raise HTTPException(status_code=400, detail=f"Invalid format: {format}")

    # Parse with new format
    try:
        combined_preview = []
        if format == "custom":
            if not pattern_id:
                raise HTTPException(status_code=400, detail="pattern_id required for custom format")

            pattern = db.get_pattern(pattern_id)
            if not pattern:
                raise HTTPException(status_code=404, detail="Pattern not found")

            for file_path in existing_paths:
                records = parse_with_pattern(file_path, pattern, limit=100)
                combined_preview.extend(records)
                if len(combined_preview) >= 100:
                    combined_preview = combined_preview[:100]
                    break
        else:
            # Existing standard format parsing
            for file_path in existing_paths:
                preview_records = parse_preview(file_path, format, limit=100)
                combined_preview.extend(preview_records)
                if len(combined_preview) >= 100:
                    combined_preview = combined_preview[:100]
                    break

        # Validate field count
        if settings.max_fields_per_document > 0 and combined_preview:
            is_valid, max_found = validate_field_count(
                combined_preview, settings.max_fields_per_document
            )
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document contains {max_found} fields, which exceeds the maximum of {settings.max_fields_per_document}."
                )

        fields = infer_fields(combined_preview)

        # Update upload record with new format
        db.update_upload(safe_id, file_format=format, pattern_id=pattern_id)

        # Update cache
        _upload_cache[safe_id] = {
            "file_paths": [str(fp) for fp in existing_paths],
            "preview": combined_preview,
            "fields": fields,
        }

        return {
            "upload_id": safe_id,
            "file_format": format,
            "pattern_id": pattern_id,
            "preview": combined_preview[:100],
            "fields": [{"name": f["name"], "type": f["type"]} for f in fields],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse as {format}: {str(e)}")


def _run_ingestion_task(
    upload_id: str,
    file_paths: list[Path],
    file_format: str,
    index_name: str,
    field_mappings: dict,
    excluded_fields: list,
    timestamp_field: str | None,
    field_types: dict | None = None,
    track_index: bool = False,
    user_id: str | None = None,
    include_filename: bool = False,
    filename_field: str = "source_file",
):
    """Run ingestion in a background thread."""
    start_time = time.time()
    total_processed = 0
    total_success = 0
    total_failed = 0
    all_failed_records = []

    def progress_callback(processed: int, success: int, failed: int):
        """
        Progress callback receives cumulative values for the CURRENT file.
        We add these to totals from previously completed files.
        """
        # Check for cancellation
        if _cancellation_flags.get(upload_id, False):
            raise Exception("Ingestion cancelled by user")

        # Calculate current progress: completed files + current file progress
        current_processed = total_processed + processed
        current_success = total_success + success
        current_failed = total_failed + failed

        elapsed = time.time() - start_time
        rps = current_processed / elapsed if elapsed > 0 else 0
        total = _ingestion_progress[upload_id]["total"]
        remaining = (total - current_processed) / rps if rps > 0 else 0

        _ingestion_progress[upload_id].update({
            "processed": current_processed,
            "success": current_success,
            "failed": current_failed,
            "elapsed_seconds": elapsed,
            "records_per_second": rps,
            "estimated_remaining_seconds": remaining,
        })
        db.update_progress(upload_id, current_success, current_failed)

    try:
        # Process each file
        for file_path in file_paths:
            result = ingest_file(
                file_path=file_path,
                file_format=file_format,
                index_name=index_name,
                field_mappings=field_mappings,
                excluded_fields=excluded_fields,
                timestamp_field=timestamp_field,
                field_types=field_types,
                progress_callback=progress_callback,
                include_filename=include_filename,
                filename_field=filename_field,
            )

            # Accumulate totals after each file
            total_processed += result.processed
            total_success += result.success
            total_failed += result.failed

            if result.failed_records:
                all_failed_records.extend(result.failed_records)

        # Save failed records to file if any
        if all_failed_records:
            failures_file = _get_failures_dir() / f"{upload_id}.json"
            with open(failures_file, "w") as f:
                json.dump(all_failed_records, f, indent=2)

        # Complete ingestion
        db.complete_ingestion(
            upload_id=upload_id,
            success_count=total_success,
            failure_count=total_failed,
        )

        # Track index if needed (new index or external index in non-strict mode)
        if track_index:
            db.track_index(index_name, user_id=user_id)

        elapsed = time.time() - start_time
        _ingestion_progress[upload_id].update({
            "processed": total_processed,
            "success": total_success,
            "failed": total_failed,
            "elapsed_seconds": elapsed,
            "completed": True,
        })

    except Exception as e:
        error_msg = str(e)
        is_cancelled = "cancelled" in error_msg.lower()
        db.complete_ingestion(
            upload_id=upload_id,
            success_count=_ingestion_progress[upload_id]["success"],
            failure_count=_ingestion_progress[upload_id]["failed"],
            error_message=None if is_cancelled else error_msg,
        )
        if is_cancelled:
            db.update_upload(upload_id, status="cancelled")
        _ingestion_progress[upload_id]["error"] = error_msg if not is_cancelled else None
        _ingestion_progress[upload_id]["cancelled"] = is_cancelled

    finally:
        # Clean up uploaded files (remove entire upload directory)
        if file_paths:
            upload_dir = file_paths[0].parent
            shutil.rmtree(upload_dir, ignore_errors=True)
        _upload_cache.pop(upload_id, None)
        _cancellation_flags.pop(upload_id, None)


@router.post("/upload/{upload_id}/ingest")
async def start_ingest(upload_id: str, request: IngestRequest, http_request: Request = None):
    """Start ingestion of uploaded file(s) into OpenSearch (async)."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["status"] == "in_progress":
        raise HTTPException(status_code=400, detail="Ingestion already in progress")

    # Validate index name
    is_valid, error_msg = validate_index_name(request.index_name)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Get file paths (multi-file upload)
    cache = _upload_cache.get(safe_id)
    if cache and "file_paths" in cache:
        file_paths = [Path(fp) for fp in cache["file_paths"]]
    else:
        # Fallback: reconstruct from database
        upload_dir = _get_upload_dir() / safe_id
        filenames = upload.get("filenames", [upload["filename"]])
        file_paths = [upload_dir / fn for fn in filenames]

    # Verify files exist
    existing_paths = [fp for fp in file_paths if fp.exists()]
    if not existing_paths:
        raise HTTPException(status_code=404, detail="Uploaded files no longer exist")

    # Build full index name with prefix
    full_index_name = f"{settings.index_prefix}{request.index_name}"

    # Validate index can be written to (checks if external index in strict mode)
    try:
        index_meta = validate_index_for_ingestion(full_index_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Count total records across all files for progress tracking
    total_records = sum(count_records(fp, upload["file_format"]) for fp in existing_paths)

    # Update database with ingestion config
    db.start_ingestion(
        upload_id=safe_id,
        index_name=full_index_name,
        timestamp_field=request.timestamp_field,
        field_mappings=request.field_mappings,
        excluded_fields=request.excluded_fields,
        total_records=total_records,
    )

    # Initialize progress tracking
    _ingestion_progress[safe_id] = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "total": total_records,
        "error": None,
        "completed": False,
        "elapsed_seconds": 0,
        "records_per_second": 0,
        "estimated_remaining_seconds": 0,
    }

    # Get user for index tracking
    user = getattr(http_request.state, "user", None) if http_request else None
    user_id = user["id"] if user else None

    # Start background thread for ingestion
    thread = threading.Thread(
        target=_run_ingestion_task,
        args=(
            safe_id,
            existing_paths,
            upload["file_format"],
            full_index_name,
            request.field_mappings,
            request.excluded_fields,
            request.timestamp_field,
            request.field_types,
            index_meta["requires_tracking"],
            user_id,
            request.include_filename,
            request.filename_field,
        ),
        daemon=True,
    )
    thread.start()

    # Return immediately with status
    return {
        "upload_id": safe_id,
        "index_name": full_index_name,
        "status": "in_progress",
        "total_records": total_records,
    }


@router.post("/upload/{upload_id}/cancel")
async def cancel_ingest(upload_id: str, delete_index: bool = False):
    """Cancel an in-progress ingestion."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Ingestion is not in progress")

    # Set cancellation flag
    _cancellation_flags[safe_id] = True

    # Wait briefly for ingestion thread to notice cancellation
    for _ in range(10):
        await asyncio.sleep(0.1)
        progress = _ingestion_progress.get(safe_id)
        if progress and progress.get("cancelled"):
            break

    # Optionally delete the partial index
    index_deleted = False
    if delete_index and upload.get("index_name"):
        from app.services.opensearch import delete_index as os_delete_index
        index_deleted = os_delete_index(upload["index_name"])
        if index_deleted:
            # Mark in database that index was deleted
            db.update_upload(safe_id, index_deleted=1)

    return {
        "status": "cancelled",
        "upload_id": safe_id,
        "index_deleted": index_deleted if delete_index else None,
    }


@router.get("/upload/{upload_id}/status")
async def get_status(upload_id: str):
    """SSE endpoint for live ingestion progress."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        last_processed = -1

        while True:
            # Get current progress
            progress = _ingestion_progress.get(safe_id)

            if progress:
                if progress["processed"] != last_processed or progress.get("error") or progress.get("completed"):
                    last_processed = progress["processed"]

                    event_data = {
                        "processed": progress["processed"],
                        "total": progress["total"],
                        "success": progress["success"],
                        "failed": progress["failed"],
                        "records_per_second": round(progress.get("records_per_second", 0), 1),
                        "elapsed_seconds": round(progress.get("elapsed_seconds", 0), 1),
                        "estimated_remaining_seconds": round(progress.get("estimated_remaining_seconds", 0), 1),
                    }

                    yield f"event: progress\ndata: {json.dumps(event_data)}\n\n"

                    if progress.get("error"):
                        yield f"event: error\ndata: {json.dumps({'error': progress['error']})}\n\n"
                        break

                    if progress.get("completed"):
                        yield f"event: complete\ndata: {json.dumps(event_data)}\n\n"
                        break

            # Check database for status if no active progress
            else:
                current = db.get_upload(safe_id)
                if current and current["status"] in ("completed", "failed"):
                    event_data = {
                        "processed": current["total_records"] or 0,
                        "total": current["total_records"] or 0,
                        "success": current["success_count"] or 0,
                        "failed": current["failure_count"] or 0,
                    }

                    if current["status"] == "failed":
                        yield f"event: error\ndata: {json.dumps({'error': current['error_message']})}\n\n"
                    else:
                        yield f"event: complete\ndata: {json.dumps(event_data)}\n\n"
                    break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/upload/{upload_id}/abandon")
async def abandon_upload(upload_id: str):
    """Abandon a pending upload (used by sendBeacon on page unload)."""
    return await delete_upload(upload_id)


@router.delete("/upload/{upload_id}")
async def delete_upload(upload_id: str):
    """Delete a pending upload that was abandoned before ingestion started."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail="Can only delete pending uploads"
        )

    # Clean up uploaded files
    upload_dir = _get_upload_dir() / safe_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Remove from cache
    _upload_cache.pop(safe_id, None)

    # Delete from database
    deleted = db.delete_pending_upload(safe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Upload not found or already processed")

    return {"status": "deleted", "upload_id": safe_id}
