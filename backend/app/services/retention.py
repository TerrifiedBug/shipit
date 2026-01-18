"""Retention service for automatic cleanup of old indices and orphaned files."""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.services import audit
from app.services import database as db
from app.services.database import is_index_tracked
from app.services.opensearch import get_client, delete_index

logger = logging.getLogger(__name__)

# Retention period for orphaned uploads (hours)
UPLOAD_RETENTION_HOURS = 24

# Track the background task
_retention_task: asyncio.Task | None = None


def get_indices_with_creation_date(prefix: str) -> list[dict] | None:
    """Get indices with their creation dates.

    Returns a list of dicts with 'index' and 'creation_date' keys,
    or None if unable to fetch.
    """
    try:
        client = get_client()
        # Get index settings which contain creation_date
        response = client.indices.get_settings(index=f"{prefix}*")

        indices = []
        for index_name, index_data in response.items():
            creation_date_ms = index_data.get("settings", {}).get("index", {}).get("creation_date")
            if creation_date_ms:
                creation_date = datetime.fromtimestamp(
                    int(creation_date_ms) / 1000, tz=timezone.utc
                )
                indices.append({
                    "index": index_name,
                    "creation_date": creation_date,
                })
        return indices
    except Exception as e:
        logger.warning(f"Failed to get indices with creation dates: {e}")
        return None


def cleanup_old_indices() -> dict:
    """Delete indices older than retention threshold.

    Returns dict with cleanup results:
        - checked: number of indices checked
        - deleted: list of deleted index names
        - skipped: list of skipped indices (not tracked)
        - errors: list of error messages
    """
    retention_days = settings.index_retention_days
    if retention_days <= 0:
        logger.info("Index retention disabled (INDEX_RETENTION_DAYS=0)")
        return {"checked": 0, "deleted": [], "skipped": [], "errors": []}

    prefix = settings.index_prefix
    indices = get_indices_with_creation_date(prefix)

    if indices is None:
        logger.error("Failed to fetch indices for retention cleanup")
        return {"checked": 0, "deleted": [], "skipped": [], "errors": ["Failed to fetch indices"]}

    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

    result = {
        "checked": len(indices),
        "deleted": [],
        "skipped": [],
        "errors": [],
    }

    for idx in indices:
        index_name = idx["index"]
        creation_date = idx["creation_date"]

        # Only delete if older than retention threshold
        if creation_date >= cutoff_date:
            continue

        # Only delete indices tracked by ShipIt (strict mode safety)
        if settings.strict_index_mode and not is_index_tracked(index_name):
            result["skipped"].append(index_name)
            logger.info(f"Skipping untracked index for retention: {index_name}")
            continue

        # Delete the index
        try:
            if delete_index(index_name):
                result["deleted"].append(index_name)
                logger.info(f"Deleted index due to retention policy: {index_name} (created: {creation_date})")

                # Log to audit
                audit.log_index_deleted(
                    actor_id="system",
                    actor_name="retention-policy",
                    index_name=index_name,
                    ip_address="system",
                )
            else:
                result["errors"].append(f"Failed to delete {index_name}")
        except Exception as e:
            result["errors"].append(f"Error deleting {index_name}: {str(e)}")
            logger.error(f"Error deleting index {index_name}: {e}")

    logger.info(
        f"Retention cleanup complete: checked={result['checked']}, "
        f"deleted={len(result['deleted'])}, skipped={len(result['skipped'])}"
    )
    return result


def cleanup_orphaned_uploads() -> dict:
    """Clean up orphaned upload files that were never ingested.

    Deletes:
    - Upload directories for uploads in 'pending' status older than UPLOAD_RETENTION_HOURS
    - Orphaned directories in uploads/ that don't have a database record

    Returns dict with cleanup results.
    """
    uploads_dir = Path(settings.data_dir) / "uploads"
    chunks_dir = Path(settings.data_dir) / "chunks"

    result = {
        "uploads_deleted": 0,
        "chunks_deleted": 0,
        "errors": [],
    }

    cutoff_time = datetime.now() - timedelta(hours=UPLOAD_RETENTION_HOURS)

    # Clean up orphaned upload directories
    if uploads_dir.exists():
        for upload_dir in uploads_dir.iterdir():
            if not upload_dir.is_dir():
                continue

            upload_id = upload_dir.name
            try:
                # Check directory age first (quick check)
                mtime = datetime.fromtimestamp(upload_dir.stat().st_mtime)
                if mtime > cutoff_time:
                    continue  # Too recent, skip

                # Check database for upload status
                upload = db.get_upload(upload_id)
                chunked_upload = db.get_chunked_upload(upload_id)

                # Delete if:
                # - No database record (orphaned)
                # - Status is 'pending' and older than retention period
                should_delete = False
                if upload is None and chunked_upload is None:
                    should_delete = True
                    logger.info(f"Deleting orphaned upload directory: {upload_id}")
                elif upload and upload.get("status") == "pending":
                    should_delete = True
                    logger.info(f"Deleting stale pending upload: {upload_id}")

                if should_delete:
                    shutil.rmtree(upload_dir, ignore_errors=True)
                    # Also delete from database if exists
                    if upload:
                        db.delete_pending_upload(upload_id)
                    result["uploads_deleted"] += 1

            except Exception as e:
                result["errors"].append(f"Error cleaning {upload_id}: {str(e)}")
                logger.error(f"Error cleaning upload {upload_id}: {e}")

    # Clean up orphaned chunk directories
    if chunks_dir.exists():
        for chunk_dir in chunks_dir.iterdir():
            if not chunk_dir.is_dir():
                continue

            upload_id = chunk_dir.name
            try:
                # Check directory age
                mtime = datetime.fromtimestamp(chunk_dir.stat().st_mtime)
                if mtime > cutoff_time:
                    continue  # Too recent, skip

                # Check if chunked upload exists and is not in progress
                chunked_upload = db.get_chunked_upload(upload_id)
                if chunked_upload is None or chunked_upload.get("status") != "uploading":
                    logger.info(f"Deleting orphaned chunks directory: {upload_id}")
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                    result["chunks_deleted"] += 1

            except Exception as e:
                result["errors"].append(f"Error cleaning chunks {upload_id}: {str(e)}")
                logger.error(f"Error cleaning chunks {upload_id}: {e}")

    if result["uploads_deleted"] > 0 or result["chunks_deleted"] > 0:
        logger.info(
            f"Orphaned file cleanup: uploads={result['uploads_deleted']}, "
            f"chunks={result['chunks_deleted']}"
        )

    return result


async def run_retention_loop():
    """Background task that runs retention cleanup periodically."""
    logger.info("Starting retention background task")

    # Run once on startup (after a short delay to let the app initialize)
    await asyncio.sleep(10)
    cleanup_orphaned_uploads()  # Always run file cleanup
    if settings.index_retention_days > 0:
        cleanup_old_indices()

    # Then run every hour for file cleanup, every 24 hours for index cleanup
    hours_since_index_cleanup = 0
    while True:
        await asyncio.sleep(60 * 60)  # 1 hour
        hours_since_index_cleanup += 1

        # Always clean up orphaned files
        cleanup_orphaned_uploads()

        # Clean up old indices every 24 hours
        if hours_since_index_cleanup >= 24 and settings.index_retention_days > 0:
            cleanup_old_indices()
            hours_since_index_cleanup = 0


def start_retention_task():
    """Start the background retention task."""
    global _retention_task

    if _retention_task is not None:
        logger.warning("Retention task already running")
        return

    _retention_task = asyncio.create_task(run_retention_loop())
    logger.info("Started retention background task")


def stop_retention_task():
    """Stop the background retention task."""
    global _retention_task

    if _retention_task is not None:
        _retention_task.cancel()
        _retention_task = None
        logger.info("Stopped retention task")
