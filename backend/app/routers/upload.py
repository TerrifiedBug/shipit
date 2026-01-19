from __future__ import annotations

import asyncio
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.routers.auth import require_auth, require_user_or_admin
from app.services.request_utils import get_client_ip
from app.models import FieldInfo, IngestRequest, PreviewResponse, UploadResponse
from app.services import database as db
from app.services.ingestion import count_records, ingest_file
from app.services.opensearch import (
    validate_index_name,
    validate_index_for_ingestion,
    get_index_mapping,
    index_exists,
    build_mapping_from_types,
    check_mapping_conflicts,
)
from app.services.parser import detect_format, infer_fields, parse_preview, validate_field_count, parse_with_pattern, validate_format, FormatValidationError
from app.services.ecs import suggest_ecs_mappings, get_all_ecs_fields
from app.services.geoip import is_geoip_available
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


def _read_raw_lines(file_paths: list[Path], limit: int = 10) -> list[str]:
    """Read raw lines from files for pattern testing.

    Reads up to `limit` lines from the first file.
    """
    if not file_paths:
        return []

    raw_lines: list[str] = []
    # Read from first file only for pattern testing
    try:
        with open(file_paths[0], "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                raw_lines.append(line.rstrip('\n\r'))
                if len(raw_lines) >= limit:
                    break
    except Exception:
        pass
    return raw_lines


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    request: Request = None,
    user: dict = Depends(require_user_or_admin),
):
    """Upload one or more files and return preview data.

    Requires user or admin role. Viewers cannot upload files.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Check rate limit
    user_id = user["id"] if user else None
    client_ip = get_client_ip(request)

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

        # Read raw lines for pattern testing
        raw_preview = _read_raw_lines(saved_files, limit=10)

        # Create database record (use sanitized filenames)
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
            "raw_preview": raw_preview,
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
        raw_preview=raw_preview,
    )


@router.get("/upload/ecs-fields")
async def list_ecs_fields(user: dict = Depends(require_auth)):
    """List all available ECS fields for manual selection."""
    return {"fields": get_all_ecs_fields()}


@router.get("/upload/{upload_id}", response_model=UploadResponse)
async def get_upload(
    upload_id: str,
    request: Request = None,
    user: dict = Depends(require_user_or_admin),
):
    """Get upload metadata for a completed chunked upload.

    This endpoint is called after chunked upload completes to fetch
    the parsed metadata (format, fields, preview) for the assembled file.
    Requires user or admin role. Viewers cannot upload files.
    """
    safe_id = _validate_upload_id(upload_id)

    # Check if this is a completed chunked upload
    chunked_upload = db.get_chunked_upload(safe_id)
    if not chunked_upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if chunked_upload["status"] != "completed":
        raise HTTPException(status_code=400, detail="Upload not yet completed")

    # Get the assembled file path
    filename = chunked_upload["filename"]
    file_path = Path(settings.data_dir) / "uploads" / safe_id / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Assembled file not found")

    try:
        # Detect format and parse preview
        file_format = detect_format(file_path)
        preview_records = parse_preview(file_path, file_format, limit=100)

        # Validate field count
        if settings.max_fields_per_document > 0:
            is_valid, max_found = validate_field_count(preview_records, settings.max_fields_per_document)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document contains {max_found} fields, which exceeds the maximum of {settings.max_fields_per_document}."
                )

        fields = infer_fields(preview_records)
        raw_preview = _read_raw_lines([file_path], limit=10)
        file_size = file_path.stat().st_size

        # Create database record for history/tracking
        db.create_upload(
            upload_id=safe_id,
            filenames=[filename],
            file_sizes=[file_size],
            file_format=file_format,
            user_id=user["id"] if user else None,
        )

        # Cache file paths
        _upload_cache[safe_id] = {
            "file_paths": [str(file_path)],
            "preview": preview_records,
            "fields": fields,
            "raw_preview": raw_preview,
        }

        return UploadResponse(
            upload_id=safe_id,
            filename=filename,
            filenames=[filename],
            file_size=file_size,
            file_format=file_format,
            preview=preview_records[:100],
            fields=[FieldInfo(**f) for f in fields],
            raw_preview=raw_preview,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")


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
        raw_preview = cache.get("raw_preview", [])
        file_paths = [Path(fp) for fp in cache.get("file_paths", [])]
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
                file_paths.append(file_path)

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
        raw_preview = _read_raw_lines(file_paths, limit=10)
        _upload_cache[safe_id] = {
            "file_paths": [str(fp) for fp in file_paths],
            "preview": preview,
            "fields": fields,
            "raw_preview": raw_preview,
        }

    return PreviewResponse(
        upload_id=safe_id,
        filename=upload["filename"],
        file_format=upload["file_format"],
        preview=preview[:100],
        fields=[FieldInfo(**f) for f in fields],
        raw_preview=raw_preview,
    )


@router.post("/upload/{upload_id}/suggest-ecs")
async def suggest_ecs_fields(upload_id: str):
    """Suggest ECS field mappings for the uploaded data."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Get field names from the cache (fields are stored there, not in DB)
    cache = _upload_cache.get(safe_id)
    if not cache or "fields" not in cache:
        raise HTTPException(status_code=404, detail="Upload preview data not found. Please re-upload the file.")

    field_names = [f["name"] for f in cache.get("fields", [])]
    suggestions = suggest_ecs_mappings(field_names)

    return {
        "suggestions": suggestions,
        "geoip_available": is_geoip_available(),
    }


@router.post("/upload/{upload_id}/reparse")
async def reparse_upload(
    upload_id: str,
    format: str = Form(...),
    pattern_id: str | None = Form(None),
    multiline_start: str | None = Form(None),
    user: dict = Depends(require_user_or_admin),
):
    """Re-parse uploaded file with a different format.

    Requires user or admin role. Viewers cannot reparse files.
    """
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

    # Validate multiline pattern if provided
    if multiline_start:
        try:
            re.compile(multiline_start)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid multiline pattern: {e}")

    # Validate format before parsing
    try:
        validate_format(existing_paths[0], format)
    except FormatValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": e.message,
                "suggested_formats": e.suggested_formats
            }
        )

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
                preview_records = parse_preview(
                    file_path, format, limit=100, multiline_start=multiline_start
                )
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

        # Get or read raw_preview
        cache = _upload_cache.get(safe_id)
        raw_preview = cache.get("raw_preview", []) if cache else []
        if not raw_preview:
            raw_preview = _read_raw_lines(existing_paths, limit=10)

        # Update upload record with new format
        db.update_upload(safe_id, file_format=format, pattern_id=pattern_id, multiline_start=multiline_start)

        # Update cache
        _upload_cache[safe_id] = {
            "file_paths": [str(fp) for fp in existing_paths],
            "preview": combined_preview,
            "fields": fields,
            "raw_preview": raw_preview,
        }

        return {
            "upload_id": safe_id,
            "file_format": format,
            "pattern_id": pattern_id,
            "multiline_start": multiline_start,
            "preview": combined_preview[:100],
            "fields": [{"name": f["name"], "type": f["type"]} for f in fields],
            "raw_preview": raw_preview,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse as {format}: {str(e)}")


class ValidationResult(BaseModel):
    """Result of a dry-run validation."""
    valid: bool
    index_exists: bool
    conflicts: list[dict[str, str]] = []
    warnings: list[str] = []
    mapping_preview: dict[str, Any] = {}
    field_count: int = 0


@router.post("/upload/{upload_id}/validate")
async def validate_ingest(
    upload_id: str,
    request: IngestRequest,
    user: dict = Depends(require_auth),
):
    """Validate ingestion configuration without actually ingesting.

    Performs a dry-run that checks:
    - Index name validity
    - Mapping conflicts with existing index
    - Field type compatibility

    Returns validation result with mapping preview.
    """
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Validate index name
    is_valid, error_msg = validate_index_name(request.index_name)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Build full index name with prefix
    full_index_name = f"{settings.index_prefix}{request.index_name}"

    # Get cached field info
    cache = _upload_cache.get(safe_id)
    if not cache or "fields" not in cache:
        raise HTTPException(
            status_code=404,
            detail="Upload preview data not found. Please re-upload the file."
        )

    # Build the expected field types from the request
    # Start with inferred types from the preview data
    inferred_types = {f["name"]: f["type"] for f in cache["fields"]}

    # Apply field mappings (rename fields)
    final_field_types = {}
    for field_name, field_type in inferred_types.items():
        # Skip excluded fields
        if field_name in request.excluded_fields:
            continue

        # Apply field mapping (rename)
        mapped_name = request.field_mappings.get(field_name, field_name)

        # Apply explicit field type override if provided
        if mapped_name in request.field_types:
            field_type = request.field_types[mapped_name]
        elif field_name in request.field_types:
            field_type = request.field_types[field_name]

        final_field_types[mapped_name] = field_type

    # Add timestamp field if specified
    if request.timestamp_field:
        # The timestamp field gets mapped to @timestamp
        final_field_types["@timestamp"] = "date"

    # Build the mapping from types
    mapping_preview = build_mapping_from_types(final_field_types)

    warnings = []
    conflicts = []

    # Check if index exists
    idx_exists = index_exists(full_index_name)

    if idx_exists:
        # Get existing mapping
        existing_mapping = get_index_mapping(full_index_name)
        if existing_mapping:
            # Check for conflicts
            conflicts = check_mapping_conflicts(existing_mapping, final_field_types)

            if conflicts:
                for c in conflicts:
                    warnings.append(
                        f"Field '{c['field']}' type conflict: existing={c['existing_type']}, new={c['new_type']}"
                    )
        else:
            warnings.append("Could not retrieve existing index mapping for conflict check")
    else:
        warnings.append(f"Index '{full_index_name}' does not exist and will be created")

    # Validate index can be written to (strict mode check)
    try:
        validate_index_for_ingestion(full_index_name)
    except ValueError as e:
        return ValidationResult(
            valid=False,
            index_exists=idx_exists,
            conflicts=conflicts,
            warnings=[str(e)],
            mapping_preview=mapping_preview,
            field_count=len(final_field_types),
        )

    return ValidationResult(
        valid=len(conflicts) == 0,
        index_exists=idx_exists,
        conflicts=conflicts,
        warnings=warnings,
        mapping_preview=mapping_preview,
        field_count=len(final_field_types),
    )


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
    pattern: dict | None = None,
    multiline_start: str | None = None,
    multiline_max_lines: int = 100,
    field_transforms: dict | None = None,
    geoip_fields: list[str] | None = None,
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
                pattern=pattern,
                multiline_start=multiline_start,
                multiline_max_lines=multiline_max_lines,
                field_transforms=field_transforms,
                geoip_fields=geoip_fields,
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
async def start_ingest(
    upload_id: str,
    request: IngestRequest,
    http_request: Request = None,
    user: dict = Depends(require_user_or_admin),
):
    """Start ingestion of uploaded file(s) into OpenSearch (async).

    Requires user or admin role. Viewers cannot ingest files.
    """
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

    # Get pattern if using custom format
    pattern = None
    if upload.get("pattern_id"):
        pattern = db.get_pattern(upload["pattern_id"])

    # Count total records across all files for progress tracking
    total_records = sum(
        count_records(
            fp,
            upload["file_format"],
            pattern,
            request.multiline_start,
            request.multiline_max_lines,
        )
        for fp in existing_paths
    )

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

    # Get user_id for index tracking
    user_id = user["id"] if user else None

    # Convert field_transforms from Pydantic models to dicts for the service layer
    field_transforms_dict = None
    if request.field_transforms:
        field_transforms_dict = {
            field: [t.model_dump(exclude_none=True) for t in transforms]
            for field, transforms in request.field_transforms.items()
        }

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
            pattern,
            request.multiline_start,
            request.multiline_max_lines,
            field_transforms_dict,
            request.geoip_fields,
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
async def cancel_ingest(
    upload_id: str,
    delete_index: bool = False,
    user: dict = Depends(require_user_or_admin),
):
    """Cancel an in-progress ingestion.

    Requires user or admin role. Viewers cannot cancel ingestions.
    """
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


# Chunked upload endpoints for large file uploads


def _get_chunks_dir() -> Path:
    """Get the chunks directory, creating it if needed."""
    chunks_dir = Path(settings.data_dir) / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    return chunks_dir


@router.post("/upload/chunked/init")
async def init_chunked_upload(
    filename: str = Form(...),
    file_size: int = Form(...),
    user: dict = Depends(require_user_or_admin),
):
    """Initialize a chunked upload.

    Requires user or admin role. Viewers cannot upload files.
    """
    # Validate file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {settings.max_file_size_mb}MB")

    # Sanitize filename to prevent path traversal
    safe_filename = _sanitize_filename(filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    chunk_size = settings.chunk_size_mb * 1024 * 1024  # Convert MB to bytes
    total_chunks = (file_size + chunk_size - 1) // chunk_size

    upload = db.create_chunked_upload(
        filename=safe_filename,
        file_size=file_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        user_id=user["id"] if user else "anonymous",
        retention_hours=settings.chunk_retention_hours,
    )

    return {
        "upload_id": upload["id"],
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
    }


@router.post("/upload/chunked/{upload_id}/chunk/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    user: dict = Depends(require_user_or_admin),
):
    """Upload a single chunk.

    Requires user or admin role. Viewers cannot upload files.
    """
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_chunked_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if chunk_index < 0 or chunk_index >= upload["total_chunks"]:
        raise HTTPException(status_code=400, detail="Invalid chunk index")

    # Create chunks directory for this upload
    chunks_dir = _get_chunks_dir() / safe_id
    chunks_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = chunks_dir / f"{chunk_index:06d}"

    # Stream directly to disk
    async with aiofiles.open(chunk_path, 'wb') as f:
        async for data in request.stream():
            await f.write(data)

    db.mark_chunk_complete(safe_id, chunk_index)

    return {"received": True, "chunk_index": chunk_index}


@router.get("/upload/chunked/{upload_id}/status")
async def get_chunked_upload_status(upload_id: str):
    """Get the status of a chunked upload."""
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_chunked_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    return {
        "upload_id": safe_id,
        "filename": upload["filename"],
        "total_chunks": upload["total_chunks"],
        "completed_chunks": upload["completed_chunks"],  # Return array for resume support
        "status": upload["status"],
    }


@router.post("/upload/chunked/{upload_id}/complete")
async def complete_chunked_upload(
    upload_id: str,
    user: dict = Depends(require_user_or_admin),
):
    """Complete a chunked upload by reassembling chunks.

    Requires user or admin role. Viewers cannot upload files.
    """
    safe_id = _validate_upload_id(upload_id)
    upload = db.get_chunked_upload(safe_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Check if already completed
    if upload["status"] == "completed":
        raise HTTPException(status_code=400, detail="Upload already completed")

    # Verify all chunks are uploaded
    if len(upload["completed_chunks"]) != upload["total_chunks"]:
        missing = set(range(upload["total_chunks"])) - set(upload["completed_chunks"])
        raise HTTPException(
            status_code=400,
            detail=f"Missing {len(missing)} chunks"
        )

    # Reassemble chunks
    chunks_dir = _get_chunks_dir() / safe_id
    uploads_dir = Path(settings.data_dir) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    final_path = uploads_dir / safe_id / upload["filename"]
    final_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(final_path, 'wb') as outfile:
        for i in range(upload["total_chunks"]):
            chunk_path = chunks_dir / f"{i:06d}"
            async with aiofiles.open(chunk_path, 'rb') as chunk:
                while data := await chunk.read(65536):
                    await outfile.write(data)

    # Cleanup chunks
    shutil.rmtree(chunks_dir, ignore_errors=True)

    # Update status
    db.update_chunked_upload_status(safe_id, "completed")

    return {"upload_id": safe_id, "status": "completed"}
