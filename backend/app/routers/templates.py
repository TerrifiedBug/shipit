from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.auth import require_auth, require_user_or_admin
from app.services import audit
from app.services.request_utils import get_client_ip
from app.services.database import (
    create_index_template,
    get_index_template,
    list_index_templates,
    delete_index_template as db_delete_index_template,
)

router = APIRouter(prefix="/templates", tags=["templates"])


class CreateTemplateRequest(BaseModel):
    """Request to create an index template."""

    name: str
    description: str | None = None
    config: dict  # Contains field_mappings, exclude_fields, transforms, timestamp_field, field_types


class TemplateResponse(BaseModel):
    """Response for a template."""

    id: str
    name: str
    description: str | None
    config: dict
    created_by: str
    created_at: str


@router.get("")
def list_templates(user: dict = Depends(require_auth)) -> list[TemplateResponse]:
    """List all index templates."""
    templates = list_index_templates()
    return [
        TemplateResponse(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            config=t["config"],
            created_by=t["created_by"],
            created_at=t["created_at"],
        )
        for t in templates
    ]


@router.get("/{template_id}")
def get_template(template_id: str, user: dict = Depends(require_auth)) -> TemplateResponse:
    """Get a specific template by ID."""
    template = get_index_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateResponse(
        id=template["id"],
        name=template["name"],
        description=template["description"],
        config=template["config"],
        created_by=template["created_by"],
        created_at=template["created_at"],
    )


@router.post("")
def create_template(
    request: CreateTemplateRequest,
    http_request: Request = None,
    user: dict = Depends(require_user_or_admin),
) -> TemplateResponse:
    """Create a new index template.

    Requires user or admin role. Viewers cannot create templates.
    """
    try:
        template = create_index_template(
            name=request.name,
            config=request.config,
            created_by=user["id"],
            description=request.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit.log_template_created(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        template_id=template["id"],
        template_name=request.name,
        ip_address=get_client_ip(http_request),
    )

    return TemplateResponse(
        id=template["id"],
        name=template["name"],
        description=template["description"],
        config=template["config"],
        created_by=template["created_by"],
        created_at=template["created_at"],
    )


@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    http_request: Request = None,
    user: dict = Depends(require_user_or_admin),
):
    """Delete an index template.

    Requires user or admin role. Viewers cannot delete templates.
    """
    template = get_index_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db_delete_index_template(template_id)

    audit.log_template_deleted(
        actor_id=user["id"],
        actor_name=user.get("email", ""),
        template_id=template_id,
        template_name=template["name"],
        ip_address=get_client_ip(http_request),
    )

    return {"message": "Template deleted"}
