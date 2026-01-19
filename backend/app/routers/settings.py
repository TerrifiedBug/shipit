"""Settings router for admin-configurable application settings."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.admin import require_admin
from app.services import database as db

router = APIRouter(prefix="/settings", tags=["settings"])


class CustomEcsMappingCreate(BaseModel):
    """Request body for creating a custom ECS mapping."""
    source_pattern: str
    ecs_field: str


@router.get("/ecs-mappings")
async def list_custom_ecs_mappings(user: dict = Depends(require_admin)):
    """List all custom ECS mappings (admin only)."""
    return {"mappings": db.list_custom_ecs_mappings()}


@router.post("/ecs-mappings")
async def create_custom_ecs_mapping(
    data: CustomEcsMappingCreate,
    user: dict = Depends(require_admin),
):
    """Create a custom ECS mapping (admin only).

    Custom mappings allow admins to define organization-specific field mappings
    that will be used when suggesting ECS mappings for uploaded data.
    """
    try:
        mapping = db.create_custom_ecs_mapping(
            source_pattern=data.source_pattern,
            ecs_field=data.ecs_field,
            created_by=user["id"],
        )
        return mapping
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/ecs-mappings/{mapping_id}")
async def delete_custom_ecs_mapping(
    mapping_id: str,
    user: dict = Depends(require_admin),
):
    """Delete a custom ECS mapping (admin only)."""
    if not db.delete_custom_ecs_mapping(mapping_id):
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"success": True}
