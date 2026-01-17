"""Index retention service for automatic cleanup of old indices."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.services import audit
from app.services.database import is_index_tracked
from app.services.opensearch import get_client, delete_index

logger = logging.getLogger(__name__)

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


async def run_retention_loop():
    """Background task that runs retention cleanup periodically."""
    logger.info("Starting index retention background task")

    # Run once on startup (after a short delay to let the app initialize)
    await asyncio.sleep(10)
    cleanup_old_indices()

    # Then run every 24 hours
    while True:
        await asyncio.sleep(24 * 60 * 60)  # 24 hours
        cleanup_old_indices()


def start_retention_task():
    """Start the background retention task if retention is enabled."""
    global _retention_task

    if settings.index_retention_days <= 0:
        logger.info("Index retention disabled, not starting background task")
        return

    if _retention_task is not None:
        logger.warning("Retention task already running")
        return

    _retention_task = asyncio.create_task(run_retention_loop())
    logger.info(f"Started retention task (INDEX_RETENTION_DAYS={settings.index_retention_days})")


def stop_retention_task():
    """Stop the background retention task."""
    global _retention_task

    if _retention_task is not None:
        _retention_task.cancel()
        _retention_task = None
        logger.info("Stopped retention task")
