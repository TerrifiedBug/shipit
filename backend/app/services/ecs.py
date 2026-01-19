# backend/app/services/ecs.py
"""Elastic Common Schema (ECS) field mapping service."""
from __future__ import annotations

import json
from pathlib import Path

# Load ECS schema from bundled JSON file
_schema_path = Path(__file__).parent.parent / "data" / "ecs_schema.json"


def _load_ecs_schema() -> dict[str, dict]:
    """Load ECS schema from bundled JSON file."""
    if _schema_path.exists():
        with open(_schema_path) as f:
            return json.load(f)
    return {}


ECS_SCHEMA: dict[str, dict] = _load_ecs_schema()

# Safe ECS mappings - only unambiguous field name mappings
# NOTE: Ambiguous mappings have been intentionally removed:
# - remote_ip: Could be source or destination depending on log perspective
# - server_ip: Could be destination (from client view) or source (from server view)
# - host: Too generic, could mean host.name, host.ip, or hostname field
SAFE_ECS_MAPPINGS: dict[str, str] = {
    # Source IP - unambiguous field names that clearly indicate source/client
    "src_ip": "source.ip",
    "source_ip": "source.ip",
    "client_ip": "source.ip",
    "clientip": "source.ip",
    # Destination IP - unambiguous field names that clearly indicate destination
    "dst_ip": "destination.ip",
    "dest_ip": "destination.ip",
    "destination_ip": "destination.ip",
    "target_ip": "destination.ip",
    # Source port
    "src_port": "source.port",
    "source_port": "source.port",
    "client_port": "source.port",
    # Destination port
    "dst_port": "destination.port",
    "dest_port": "destination.port",
    "destination_port": "destination.port",
    "target_port": "destination.port",
    # User fields
    "user": "user.name",
    "username": "user.name",
    "user_name": "user.name",
    "userid": "user.id",
    "user_id": "user.id",
    "user_email": "user.email",
    "email": "user.email",
    # Event fields
    "action": "event.action",
    "event_action": "event.action",
    "event_type": "event.type",
    "event_category": "event.category",
    "event_id": "event.id",
    "event_outcome": "event.outcome",
    "severity": "event.severity",
    "event_severity": "event.severity",
    # Timestamp variations
    "timestamp": "@timestamp",
    "@timestamp": "@timestamp",
    "time": "@timestamp",
    "datetime": "@timestamp",
    "event_time": "@timestamp",
    "date": "@timestamp",
    # Network fields
    "protocol": "network.protocol",
    "network_protocol": "network.protocol",
    "transport": "network.transport",
    "network_transport": "network.transport",
    "bytes": "network.bytes",
    "network_bytes": "network.bytes",
    "packets": "network.packets",
    # Host fields - specific enough to be unambiguous
    "hostname": "host.name",
    "host_name": "host.name",
    "host_id": "host.id",
    "host_ip": "host.ip",
    "os_name": "host.os.name",
    "os_version": "host.os.version",
    "os_family": "host.os.family",
    # HTTP fields
    "http_method": "http.request.method",
    "method": "http.request.method",
    "request_method": "http.request.method",
    "status_code": "http.response.status_code",
    "http_status": "http.response.status_code",
    "http_status_code": "http.response.status_code",
    "response_code": "http.response.status_code",
    "referrer": "http.request.referrer",
    "http_referrer": "http.request.referrer",
    "referer": "http.request.referrer",
    "http_version": "http.version",
    "request_bytes": "http.request.bytes",
    "response_bytes": "http.response.bytes",
    "content_type": "http.response.mime_type",
    # URL fields
    "url": "url.full",
    "request_url": "url.full",
    "full_url": "url.full",
    "url_path": "url.path",
    "request_path": "url.path",
    "path": "url.path",
    "uri": "url.path",
    "url_query": "url.query",
    "query_string": "url.query",
    "url_domain": "url.domain",
    # Log fields
    "log_level": "log.level",
    "level": "log.level",
    "loglevel": "log.level",
    "logger": "log.logger",
    "log_file": "log.file.path",
    # Process fields
    "pid": "process.pid",
    "process_id": "process.pid",
    "process_pid": "process.pid",
    "ppid": "process.ppid",
    "parent_pid": "process.ppid",
    "process_name": "process.name",
    "command": "process.command_line",
    "command_line": "process.command_line",
    "cmdline": "process.command_line",
    "executable": "process.executable",
    "exe": "process.executable",
    # Message
    "message": "message",
    "msg": "message",
    "log_message": "message",
    # User agent
    "user_agent": "user_agent.original",
    "useragent": "user_agent.original",
    "ua": "user_agent.original",
    # File fields
    "file_path": "file.path",
    "filename": "file.name",
    "file_name": "file.name",
    "file_size": "file.size",
    "file_type": "file.type",
    "file_extension": "file.extension",
    "file_hash": "file.hash.sha256",
    "md5": "file.hash.md5",
    "sha1": "file.hash.sha1",
    "sha256": "file.hash.sha256",
    # Agent fields
    "agent_id": "agent.id",
    "agent_name": "agent.name",
    "agent_type": "agent.type",
    "agent_version": "agent.version",
}

# Keep ECS_FIELD_MAP as alias for backward compatibility
ECS_FIELD_MAP = SAFE_ECS_MAPPINGS


def get_ecs_field_type(ecs_field: str) -> str | None:
    """Get the ECS field type for a given ECS field name.

    Args:
        ecs_field: The ECS field name (e.g., 'source.ip', 'message')

    Returns:
        The field type (e.g., 'ip', 'text', 'keyword') or None if not found.
    """
    field_info = ECS_SCHEMA.get(ecs_field)
    if field_info:
        return field_info.get("type")
    return None


def suggest_ecs_mappings(field_names: list[str]) -> dict[str, str]:
    """Suggest ECS field mappings for a list of field names.

    Only suggests mappings for unambiguous field names. Ambiguous fields
    like 'remote_ip', 'server_ip', 'host' are intentionally not mapped.

    Args:
        field_names: List of field names from the uploaded data

    Returns:
        Dict mapping original field names to suggested ECS field names.
        Only includes fields that have a known unambiguous mapping.
    """
    suggestions = {}

    for field in field_names:
        # Try exact match first (case-insensitive)
        field_lower = field.lower()
        if field_lower in SAFE_ECS_MAPPINGS:
            suggestions[field] = SAFE_ECS_MAPPINGS[field_lower]

    return suggestions


def get_all_ecs_fields() -> dict[str, dict]:
    """Get all available ECS fields from the schema.

    Returns:
        Dict mapping ECS field names to their schema info (type, description).
    """
    return dict(ECS_SCHEMA)


def get_all_ecs_mappings() -> dict[str, str]:
    """Get all available ECS field mappings.

    Returns:
        Dict mapping common field names to ECS field names.
    """
    return dict(SAFE_ECS_MAPPINGS)
