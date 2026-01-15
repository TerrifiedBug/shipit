import asyncio
import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models import FieldInfo, IngestRequest, PreviewResponse, UploadResponse
from app.services import database as db
from app.services.ingestion import count_records, ingest_file
from app.services.opensearch import validate_index_name
from app.services.parser import detect_format, infer_fields, parse_preview

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


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile, request: Request):
    """Upload a file and return preview data."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".json") or filename_lower.endswith(".csv")):
        raise HTTPException(
            status_code=400, detail="Unsupported file type. Only .json and .csv files are supported."
        )

    upload_id = str(uuid.uuid4())
    upload_dir = _get_upload_dir()
    file_path = upload_dir / f"{upload_id}_{file.filename}"

    # Stream file to disk
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    # Get file size
    file_size = file_path.stat().st_size

    # Check file size limit
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB"
        )

    # Detect format and parse preview
    try:
        file_format = detect_format(file_path)
        preview = parse_preview(file_path, file_format, limit=100)
        fields = infer_fields(preview)
    except Exception as e:
        # Clean up file on parse error
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    # Create database record
    user = getattr(request.state, "user", None)
    db.create_upload(
        upload_id=upload_id,
        filenames=[file.filename],
        file_sizes=[file_size],
        file_format=file_format,
        user_id=user["id"] if user else None,
    )

    # Cache file path and preview data
    _upload_cache[upload_id] = {
        "file_path": str(file_path),
        "preview": preview,
        "fields": fields,
    }

    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename,
        file_size=file_size,
        file_format=file_format,
        preview=preview,
        fields=[FieldInfo(**f) for f in fields],
    )


@router.get("/upload/{upload_id}/preview", response_model=PreviewResponse)
async def get_preview(upload_id: str):
    """Get preview data for a previously uploaded file."""
    upload = db.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Get from cache or re-parse
    cache = _upload_cache.get(upload_id)
    if cache:
        preview = cache["preview"]
        fields = cache["fields"]
    else:
        # Re-parse if not in cache (e.g., after server restart)
        file_path = Path(_get_upload_dir() / f"{upload_id}_{upload['filename']}")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Uploaded file no longer exists")

        preview = parse_preview(file_path, upload["file_format"], limit=100)
        fields = infer_fields(preview)
        _upload_cache[upload_id] = {
            "file_path": str(file_path),
            "preview": preview,
            "fields": fields,
        }

    return PreviewResponse(
        upload_id=upload_id,
        filename=upload["filename"],
        file_format=upload["file_format"],
        preview=preview,
        fields=[FieldInfo(**f) for f in fields],
    )


def _run_ingestion_task(
    upload_id: str,
    file_path: Path,
    file_format: str,
    index_name: str,
    field_mappings: dict,
    excluded_fields: list,
    timestamp_field: str | None,
):
    """Run ingestion in a background thread."""
    start_time = time.time()

    def progress_callback(processed: int, success: int, failed: int):
        # Check for cancellation
        if _cancellation_flags.get(upload_id, False):
            raise Exception("Ingestion cancelled by user")

        elapsed = time.time() - start_time
        rps = processed / elapsed if elapsed > 0 else 0
        total = _ingestion_progress[upload_id]["total"]
        remaining = (total - processed) / rps if rps > 0 else 0

        _ingestion_progress[upload_id].update({
            "processed": processed,
            "success": success,
            "failed": failed,
            "elapsed_seconds": elapsed,
            "records_per_second": rps,
            "estimated_remaining_seconds": remaining,
        })
        db.update_progress(upload_id, success, failed)

    try:
        result = ingest_file(
            file_path=file_path,
            file_format=file_format,
            index_name=index_name,
            field_mappings=field_mappings,
            excluded_fields=excluded_fields,
            timestamp_field=timestamp_field,
            progress_callback=progress_callback,
        )

        # Save failed records to file if any
        if result.failed_records:
            failures_file = _get_failures_dir() / f"{upload_id}.json"
            with open(failures_file, "w") as f:
                json.dump(result.failed_records, f, indent=2)

        # Complete ingestion
        db.complete_ingestion(
            upload_id=upload_id,
            success_count=result.success,
            failure_count=result.failed,
        )

        elapsed = time.time() - start_time
        _ingestion_progress[upload_id].update({
            "processed": result.processed,
            "success": result.success,
            "failed": result.failed,
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
        # Clean up uploaded file
        file_path.unlink(missing_ok=True)
        _upload_cache.pop(upload_id, None)
        _cancellation_flags.pop(upload_id, None)


@router.post("/upload/{upload_id}/ingest")
async def start_ingest(upload_id: str, request: IngestRequest):
    """Start ingestion of an uploaded file into OpenSearch (async)."""
    upload = db.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["status"] == "in_progress":
        raise HTTPException(status_code=400, detail="Ingestion already in progress")

    # Validate index name
    is_valid, error_msg = validate_index_name(request.index_name)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Get file path
    cache = _upload_cache.get(upload_id)
    if cache:
        file_path = Path(cache["file_path"])
    else:
        file_path = _get_upload_dir() / f"{upload_id}_{upload['filename']}"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file no longer exists")

    # Build full index name with prefix
    full_index_name = f"{settings.index_prefix}{request.index_name}"

    # Count total records for progress tracking
    total_records = count_records(file_path, upload["file_format"])

    # Update database with ingestion config
    db.start_ingestion(
        upload_id=upload_id,
        index_name=full_index_name,
        timestamp_field=request.timestamp_field,
        field_mappings=request.field_mappings,
        excluded_fields=request.excluded_fields,
        total_records=total_records,
    )

    # Initialize progress tracking
    _ingestion_progress[upload_id] = {
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

    # Start background thread for ingestion
    thread = threading.Thread(
        target=_run_ingestion_task,
        args=(
            upload_id,
            file_path,
            upload["file_format"],
            full_index_name,
            request.field_mappings,
            request.excluded_fields,
            request.timestamp_field,
        ),
        daemon=True,
    )
    thread.start()

    # Return immediately with status
    return {
        "upload_id": upload_id,
        "index_name": full_index_name,
        "status": "in_progress",
        "total_records": total_records,
    }


@router.post("/upload/{upload_id}/cancel")
async def cancel_ingest(upload_id: str, delete_index: bool = False):
    """Cancel an in-progress ingestion."""
    upload = db.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if upload["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Ingestion is not in progress")

    # Set cancellation flag
    _cancellation_flags[upload_id] = True

    # Wait briefly for ingestion thread to notice cancellation
    for _ in range(10):
        await asyncio.sleep(0.1)
        progress = _ingestion_progress.get(upload_id)
        if progress and progress.get("cancelled"):
            break

    # Optionally delete the partial index
    index_deleted = False
    if delete_index and upload.get("index_name"):
        from app.services.opensearch import delete_index as os_delete_index
        index_deleted = os_delete_index(upload["index_name"])
        if index_deleted:
            # Mark in database that index was deleted
            db.update_upload(upload_id, index_deleted=1)

    return {
        "status": "cancelled",
        "upload_id": upload_id,
        "index_deleted": index_deleted if delete_index else None,
    }


@router.get("/upload/{upload_id}/status")
async def get_status(upload_id: str):
    """SSE endpoint for live ingestion progress."""
    upload = db.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        last_processed = -1

        while True:
            # Get current progress
            progress = _ingestion_progress.get(upload_id)

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
                current = db.get_upload(upload_id)
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
