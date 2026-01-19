"""Audit log API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.routers.auth import require_admin_or_viewer
from app.services import database as db

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogEntry(BaseModel):
    id: str
    event_type: str
    actor_id: str | None
    actor_name: str | None
    target_type: str | None
    target_id: str | None
    details: dict | None
    ip_address: str | None
    created_at: str


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    total_pages: int


class EventTypesResponse(BaseModel):
    event_types: list[str]


@router.get("/logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    event_type: str | None = Query(None, description="Filter by event type"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    target_type: str | None = Query(None, description="Filter by target type"),
    user: dict = Depends(require_admin_or_viewer),
):
    """List audit logs with pagination and filtering.

    Accessible by admin and viewer (auditor) roles.
    """
    offset = (page - 1) * page_size

    logs, total = db.list_audit_logs(
        actor_id=actor_id,
        event_type=event_type,
        target_type=target_type,
        limit=page_size,
        offset=offset,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return AuditLogListResponse(
        logs=[
            AuditLogEntry(
                id=log["id"],
                event_type=log.get("event_type", ""),
                actor_id=log.get("actor_id"),
                actor_name=log.get("actor_name"),
                target_type=log.get("target_type"),
                target_id=log.get("target_id"),
                details=log.get("details"),
                ip_address=log.get("ip_address"),
                created_at=log["created_at"],
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/event-types", response_model=EventTypesResponse)
def get_event_types(user: dict = Depends(require_admin_or_viewer)):
    """Get list of distinct event types for filtering.

    Accessible by admin and viewer (auditor) roles.
    """
    event_types = db.get_audit_log_event_types()
    return EventTypesResponse(event_types=event_types)
