import time
from typing import Any

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import ConnectionError, TransportError

from app.config import settings


def get_client() -> OpenSearch:
    """Create an OpenSearch client with connection pooling."""
    return OpenSearch(
        hosts=[settings.opensearch_host],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=settings.opensearch_host.startswith("https"),
        verify_certs=False,  # For self-signed certs in dev
        ssl_show_warn=False,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )


def check_connection() -> bool:
    """Check if OpenSearch is reachable."""
    try:
        client = get_client()
        return client.ping()
    except (ConnectionError, TransportError):
        return False


def bulk_index(
    index_name: str,
    records: list[dict[str, Any]],
    max_retries: int = 3,
    initial_backoff: float = 1.0,
) -> dict[str, Any]:
    """
    Bulk index records to OpenSearch with retry logic.

    Returns:
        {
            "success": int,
            "failed": list[dict] - records that failed with error info
        }
    """
    if not records:
        return {"success": 0, "failed": []}

    client = get_client()

    # Prepare bulk actions
    actions = [
        {
            "_index": index_name,
            "_source": record,
        }
        for record in records
    ]

    success_count = 0
    failed_records = []

    for attempt in range(max_retries):
        try:
            # Use streaming_bulk for better memory efficiency
            successes = 0
            errors = []

            for ok, item in helpers.streaming_bulk(
                client,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
            ):
                if ok:
                    successes += 1
                else:
                    errors.append(item)

            success_count = successes

            # Process errors
            for error in errors:
                action_type = "index"
                error_info = error.get(action_type, error)
                failed_records.append({
                    "record": error_info.get("data", {}),
                    "error": error_info.get("error", str(error)),
                })

            # If we got here without exception, we're done
            break

        except TransportError as e:
            if e.status_code == 429:  # Too Many Requests
                if attempt < max_retries - 1:
                    backoff = initial_backoff * (2 ** attempt)
                    time.sleep(backoff)
                    continue
            raise
        except ConnectionError:
            if attempt < max_retries - 1:
                backoff = initial_backoff * (2 ** attempt)
                time.sleep(backoff)
                continue
            raise

    return {
        "success": success_count,
        "failed": failed_records,
    }


def delete_index(index_name: str) -> bool:
    """Delete an index. Returns True if deleted, False if not found."""
    try:
        client = get_client()
        client.indices.delete(index=index_name)
        return True
    except Exception:
        return False


def list_indexes(prefix: str) -> set[str] | None:
    """Get set of all index names matching prefix.

    Returns None if unable to check (permission error, connection issue).
    Returns empty set if no indexes exist.
    """
    try:
        client = get_client()
        response = client.cat.indices(index=f"{prefix}*", format="json")
        return {idx["index"] for idx in response}
    except Exception as e:
        # Return None to indicate "unknown" - could be permission issue
        import logging
        logging.warning(f"Failed to list indexes with prefix '{prefix}': {e}")
        return None


def validate_index_for_ingestion(index_name: str) -> dict[str, Any]:
    """
    Validate that an index can be written to.

    Checks if the index exists in OpenSearch and whether it's tracked by ShipIt.
    In strict mode, raises an error if the index exists but wasn't created by ShipIt.

    Args:
        index_name: Full index name (with prefix)

    Returns:
        dict with keys:
            - exists: bool - whether index exists in OpenSearch
            - tracked: bool - whether index is tracked by ShipIt
            - requires_tracking: bool - whether index needs to be tracked after creation

    Raises:
        ValueError: If index exists but not tracked and strict mode is enabled
    """
    from app.services.database import is_index_tracked

    client = get_client()

    # Check if index exists in OpenSearch
    exists = client.indices.exists(index=index_name)

    if not exists:
        # New index - will need to be tracked after creation
        return {"exists": False, "tracked": False, "requires_tracking": True}

    # Index exists - check if it's tracked by ShipIt
    tracked = is_index_tracked(index_name)

    if tracked:
        # Tracked index - safe to write, no additional tracking needed
        return {"exists": True, "tracked": True, "requires_tracking": False}

    # External index (exists but not tracked)
    if settings.strict_index_mode:
        raise ValueError(
            f"Index '{index_name}' exists but was not created by ShipIt. "
            f"Writing to external indices is blocked in strict mode. "
            f"Set STRICT_INDEX_MODE=false to allow writes to external indices."
        )

    # Strict mode off - allow but flag for tracking
    return {"exists": True, "tracked": False, "requires_tracking": True}


def validate_index_name(index_name: str) -> tuple[bool, str]:
    """
    Validate that an index name is valid and has the required prefix.

    Returns:
        (is_valid, error_message)
    """
    full_name = f"{settings.index_prefix}{index_name}"

    # Check prefix is applied
    if not full_name.startswith(settings.index_prefix):
        return False, f"Index name must start with '{settings.index_prefix}'"

    # OpenSearch index name rules
    if not index_name:
        return False, "Index name cannot be empty"

    if index_name.startswith("-") or index_name.startswith("_"):
        return False, "Index name cannot start with '-' or '_'"

    invalid_chars = ['\\', '/', '*', '?', '"', '<', '>', '|', ' ', ',', '#', ':']
    for char in invalid_chars:
        if char in index_name:
            return False, f"Index name cannot contain '{char}'"

    if index_name != index_name.lower():
        return False, "Index name must be lowercase"

    if len(full_name) > 255:
        return False, "Index name is too long (max 255 characters)"

    return True, ""
