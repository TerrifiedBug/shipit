"""Settings router for application settings."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.auth import require_auth
from app.services import database as db

router = APIRouter(prefix="/settings", tags=["settings"])


def require_non_viewer(user: dict = Depends(require_auth)) -> dict:
    """Require user to be admin or user role (not viewer)."""
    if user.get("role") == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot manage ECS mappings")
    return user


class CustomEcsMappingCreate(BaseModel):
    """Request body for creating a custom ECS mapping."""
    source_pattern: str
    ecs_field: str


@router.get("/ecs-mappings")
async def list_custom_ecs_mappings(user: dict = Depends(require_non_viewer)):
    """List all custom ECS mappings (admin/user only)."""
    return {"mappings": db.list_custom_ecs_mappings()}


@router.post("/ecs-mappings")
async def create_custom_ecs_mapping(
    data: CustomEcsMappingCreate,
    user: dict = Depends(require_non_viewer),
):
    """Create a custom ECS mapping.

    Custom mappings allow users to define organization-specific field mappings
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
    user: dict = Depends(require_non_viewer),
):
    """Delete a custom ECS mapping."""
    if not db.delete_custom_ecs_mapping(mapping_id):
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"success": True}
