from __future__ import annotations

import time
from typing import Any

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import AuthorizationException, ConnectionError, TransportError

from app.config import settings


def get_client() -> OpenSearch:
    """Create an OpenSearch client with connection pooling."""
    return OpenSearch(
        hosts=[settings.opensearch_host],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=settings.opensearch_host.startswith("https"),
        verify_certs=settings.opensearch_verify_certs,
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
    import logging

    # First check if it's tracked by ShipIt (doesn't require OpenSearch call)
    tracked = is_index_tracked(index_name)

    if tracked:
        # Tracked index - safe to write, no additional tracking needed
        return {"exists": True, "tracked": True, "requires_tracking": False}

    # If strict mode is off, skip the existence check entirely - allow all writes
    if not settings.strict_index_mode:
        return {"exists": False, "tracked": False, "requires_tracking": True}

    # Strict mode is on - need to check if index exists in OpenSearch
    # Use stats API instead of exists API - more reliable with security plugins
    try:
        client = get_client()
        # Try to get stats - 404 means index doesn't exist, success means it exists
        client.indices.stats(index=index_name)
        exists = True
    except TransportError as e:
        if e.status_code == 404:
            # Index doesn't exist
            exists = False
        elif e.status_code == 403:
            # Permission denied
            logging.error(f"Permission denied checking if index '{index_name}' exists: {e}")
            raise ValueError(
                f"Cannot verify if index '{index_name}' exists - permission denied. "
                f"The OpenSearch user needs 'indices:monitor/stats' permission on '{index_name}', "
                f"or set STRICT_INDEX_MODE=false to skip this check."
            )
        else:
            # Other transport error
            logging.error(f"Error checking index '{index_name}': {e}")
            raise ValueError(
                f"Cannot verify if index '{index_name}' exists. "
                f"Please check OpenSearch connection settings."
            )
    except AuthorizationException as e:
        # Permission denied
        logging.error(f"Permission denied checking if index '{index_name}' exists: {e}")
        raise ValueError(
            f"Cannot verify if index '{index_name}' exists - permission denied. "
            f"The OpenSearch user needs 'indices:monitor/stats' permission on '{index_name}', "
            f"or set STRICT_INDEX_MODE=false to skip this check."
        )
    except ConnectionError as e:
        # Can't connect - fail with clear error
        logging.error(f"Could not connect to OpenSearch to check index '{index_name}': {e}")
        raise ValueError(
            f"Cannot connect to OpenSearch to verify index '{index_name}'. "
            f"Please check OpenSearch connection settings."
        )

    if not exists:
        # New index - will need to be tracked after creation
        return {"exists": False, "tracked": False, "requires_tracking": True}

    # External index (exists but not tracked) - strict mode blocks this
    raise ValueError(
        f"Index '{index_name}' exists but was not created by ShipIt. "
        f"Writing to external indices is blocked in strict mode. "
        f"Set STRICT_INDEX_MODE=false to allow writes to external indices."
    )


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


def get_index_mapping(index_name: str) -> dict[str, Any] | None:
    """Get the mapping for an existing index.

    Returns None if the index doesn't exist.
    """
    try:
        client = get_client()
        response = client.indices.get_mapping(index=index_name)
        # Response format: {index_name: {mappings: {...}}}
        if index_name in response:
            return response[index_name].get("mappings", {})
        return None
    except TransportError as e:
        if e.status_code == 404:
            return None
        raise


def index_exists(index_name: str) -> bool:
    """Check if an index exists in OpenSearch."""
    try:
        client = get_client()
        return client.indices.exists(index=index_name)
    except Exception:
        return False


def build_mapping_from_types(field_types: dict[str, str]) -> dict[str, Any]:
    """Build an OpenSearch mapping from field type specifications.

    Args:
        field_types: Dict mapping field names to types (text, keyword, long, etc.)

    Returns:
        OpenSearch mapping properties dict
    """
    # Map our type names to OpenSearch types
    type_mapping = {
        "text": {"type": "text"},
        "keyword": {"type": "keyword"},
        "long": {"type": "long"},
        "integer": {"type": "integer"},
        "float": {"type": "float"},
        "double": {"type": "double"},
        "boolean": {"type": "boolean"},
        "date": {"type": "date"},
        "ip": {"type": "ip"},
        "geo_point": {"type": "geo_point"},
    }

    properties = {}
    for field_name, field_type in field_types.items():
        # Handle nested fields (e.g., "source.ip")
        parts = field_name.split(".")
        current = properties

        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {"properties": {}}
            elif "properties" not in current[part]:
                current[part]["properties"] = {}
            current = current[part]["properties"]

        final_field = parts[-1]
        os_type = type_mapping.get(field_type, {"type": "keyword"})
        current[final_field] = os_type

    return {"properties": properties}


def check_mapping_conflicts(
    existing_mapping: dict[str, Any],
    new_field_types: dict[str, str]
) -> list[dict[str, str]]:
    """Check for mapping conflicts between existing index and new field types.

    Returns list of conflicts, each with: field, existing_type, new_type
    """
    conflicts = []

    existing_props = existing_mapping.get("properties", {})

    def get_nested_type(props: dict, path: list[str]) -> str | None:
        """Get the type of a potentially nested field."""
        current = props
        for part in path[:-1]:
            if part not in current:
                return None
            current = current.get(part, {}).get("properties", {})
        final = path[-1]
        if final in current:
            return current[final].get("type")
        return None

    for field_name, new_type in new_field_types.items():
        parts = field_name.split(".")
        existing_type = get_nested_type(existing_props, parts)

        if existing_type and existing_type != new_type:
            # Check for compatible type changes
            compatible_changes = [
                # text and keyword can coexist in some cases
                ({"text", "keyword"}, {"text", "keyword"}),
                # numeric types can be widened
                ({"integer", "long"}, {"long"}),
                ({"float", "double"}, {"double"}),
            ]

            is_compatible = False
            for from_types, to_types in compatible_changes:
                if existing_type in from_types and new_type in to_types:
                    is_compatible = True
                    break

            if not is_compatible:
                conflicts.append({
                    "field": field_name,
                    "existing_type": existing_type,
                    "new_type": new_type,
                })

    return conflicts
