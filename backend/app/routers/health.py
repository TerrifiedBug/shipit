from fastapi import APIRouter

from app.config import settings
from app.services.opensearch import check_connection

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    opensearch_status = "connected" if check_connection() else "disconnected"
    return {"status": "healthy", "opensearch": opensearch_status}


@router.get("/settings")
async def get_settings():
    """Get public application settings."""
    return {
        "index_retention_days": settings.index_retention_days,
    }
