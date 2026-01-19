"""Audit log shipping service for external SIEM/log collectors and OpenSearch."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.config import settings

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

# OpenSearch client singleton (lazy initialized)
_opensearch_client: "OpenSearch | None" = None

# HTTP client singleton (lazy initialized)
_http_client: httpx.AsyncClient | None = None

AUDIT_INDEX_NAME = f"{settings.index_prefix}audit-logs"


def _get_opensearch_client() -> "OpenSearch":
    """Get or create OpenSearch client for audit logging."""
    global _opensearch_client
    if _opensearch_client is None:
        from opensearchpy import OpenSearch

        _opensearch_client = OpenSearch(
            hosts=[settings.opensearch_host],
            http_auth=(settings.opensearch_user, settings.opensearch_password),
            use_ssl=settings.opensearch_host.startswith("https"),
            verify_certs=settings.opensearch_verify_certs,
            ssl_show_warn=False,
            timeout=30,
        )
    return _opensearch_client


def _get_http_client() -> httpx.AsyncClient:
    """Get or create async HTTP client for audit shipping."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


def _parse_headers() -> dict[str, str]:
    """Parse custom headers from config string."""
    headers = {}
    if settings.audit_log_endpoint_headers:
        for header_pair in settings.audit_log_endpoint_headers.split(","):
            if ":" in header_pair:
                key, value = header_pair.split(":", 1)
                headers[key.strip()] = value.strip()
    return headers


def _ensure_audit_index() -> None:
    """Ensure the audit log index exists with proper mappings."""
    client = _get_opensearch_client()

    if not client.indices.exists(index=AUDIT_INDEX_NAME):
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "event_type": {"type": "keyword"},
                    "actor_id": {"type": "keyword"},
                    "actor_name": {"type": "keyword"},
                    "target_type": {"type": "keyword"},
                    "target_id": {"type": "keyword"},
                    "details": {"type": "object", "enabled": True},
                    "ip_address": {"type": "ip"},
                    "created_at": {"type": "date"},
                    "@timestamp": {"type": "date"},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
        }
        try:
            client.indices.create(index=AUDIT_INDEX_NAME, body=mapping)
            logger.info(f"Created audit log index: {AUDIT_INDEX_NAME}")
        except Exception as e:
            logger.warning(f"Failed to create audit index (may already exist): {e}")


def ship_to_opensearch(audit_log: dict) -> None:
    """Ship audit log to OpenSearch synchronously."""
    if not settings.audit_log_to_opensearch:
        return

    try:
        _ensure_audit_index()
        client = _get_opensearch_client()

        # Add @timestamp for OpenSearch compatibility
        doc = {
            **audit_log,
            "@timestamp": audit_log.get("created_at", datetime.utcnow().isoformat()),
        }

        client.index(
            index=AUDIT_INDEX_NAME,
            body=doc,
            id=audit_log.get("id"),
        )
        logger.debug(f"Shipped audit log to OpenSearch: {audit_log.get('id')}")
    except Exception as e:
        logger.warning(f"Failed to ship audit log to OpenSearch: {e}")


async def ship_to_http_async(audit_log: dict) -> None:
    """Ship audit log to HTTP endpoint asynchronously."""
    if not settings.audit_log_endpoint:
        return

    try:
        client = _get_http_client()
        headers = {
            "Content-Type": "application/json",
        }

        # Add bearer token if configured
        if settings.audit_log_endpoint_token:
            headers["Authorization"] = f"Bearer {settings.audit_log_endpoint_token}"

        # Add custom headers
        headers.update(_parse_headers())

        response = await client.post(
            settings.audit_log_endpoint,
            json=audit_log,
            headers=headers,
        )

        if response.status_code >= 400:
            logger.warning(
                f"Failed to ship audit log to HTTP endpoint: "
                f"status={response.status_code}, body={response.text[:200]}"
            )
        else:
            logger.debug(f"Shipped audit log to HTTP endpoint: {audit_log.get('id')}")
    except Exception as e:
        logger.warning(f"Failed to ship audit log to HTTP endpoint: {e}")


def ship_to_http(audit_log: dict) -> None:
    """Ship audit log to HTTP endpoint (fire-and-forget)."""
    if not settings.audit_log_endpoint:
        return

    try:
        # Run async shipping in background without blocking
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(ship_to_http_async(audit_log))
        else:
            # Fallback for non-async context
            asyncio.run(ship_to_http_async(audit_log))
    except RuntimeError:
        # No event loop running, use sync client
        try:
            headers = {
                "Content-Type": "application/json",
            }
            if settings.audit_log_endpoint_token:
                headers["Authorization"] = f"Bearer {settings.audit_log_endpoint_token}"
            headers.update(_parse_headers())

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    settings.audit_log_endpoint,
                    json=audit_log,
                    headers=headers,
                )
                if response.status_code >= 400:
                    logger.warning(
                        f"Failed to ship audit log to HTTP endpoint: "
                        f"status={response.status_code}"
                    )
        except Exception as e:
            logger.warning(f"Failed to ship audit log to HTTP endpoint: {e}")


def ship_audit_log(audit_log: dict) -> None:
    """Ship audit log to all configured destinations."""
    # Ship to OpenSearch if enabled
    if settings.audit_log_to_opensearch:
        ship_to_opensearch(audit_log)

    # Ship to HTTP endpoint if configured
    if settings.audit_log_endpoint:
        ship_to_http(audit_log)


def is_shipping_enabled() -> bool:
    """Check if any audit log shipping is enabled."""
    return settings.audit_log_to_opensearch or bool(settings.audit_log_endpoint)
