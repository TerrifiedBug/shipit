# backend/app/services/ecs.py
"""Elastic Common Schema (ECS) field mapping service."""
from __future__ import annotations

# Mapping from common field name patterns to ECS fields
ECS_FIELD_MAP = {
    # Source IP variations
    "src_ip": "source.ip",
    "source_ip": "source.ip",
    "client_ip": "source.ip",
    "clientip": "source.ip",
    "remote_ip": "source.ip",
    "remote_addr": "source.ip",

    # Destination IP variations
    "dst_ip": "destination.ip",
    "dest_ip": "destination.ip",
    "destination_ip": "destination.ip",
    "server_ip": "destination.ip",
    "target_ip": "destination.ip",

    # User variations
    "user": "user.name",
    "username": "user.name",
    "user_name": "user.name",
    "userid": "user.id",
    "user_id": "user.id",

    # Event variations
    "action": "event.action",
    "event_action": "event.action",
    "event_type": "event.type",
    "event_category": "event.category",

    # Timestamp variations
    "timestamp": "@timestamp",
    "@timestamp": "@timestamp",
    "time": "@timestamp",
    "datetime": "@timestamp",
    "event_time": "@timestamp",

    # Network
    "port": "source.port",
    "src_port": "source.port",
    "source_port": "source.port",
    "dst_port": "destination.port",
    "dest_port": "destination.port",
    "destination_port": "destination.port",
    "protocol": "network.protocol",

    # Host
    "hostname": "host.name",
    "host": "host.name",
    "server": "host.name",

    # Message
    "message": "message",
    "msg": "message",
    "log_message": "message",
}


def suggest_ecs_mappings(field_names: list[str]) -> dict[str, str]:
    """Suggest ECS field mappings for a list of field names.

    Args:
        field_names: List of field names from the uploaded data

    Returns:
        Dict mapping original field names to suggested ECS field names.
        Only includes fields that have a known mapping.
    """
    suggestions = {}

    for field in field_names:
        # Try exact match first (case-insensitive)
        field_lower = field.lower()
        if field_lower in ECS_FIELD_MAP:
            suggestions[field] = ECS_FIELD_MAP[field_lower]

    return suggestions


def get_all_ecs_mappings() -> dict[str, str]:
    """Get all available ECS field mappings."""
    return dict(ECS_FIELD_MAP)
