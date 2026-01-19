from fastapi import APIRouter

from app.config import settings
from app.services.opensearch import get_client

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check application and OpenSearch connectivity."""
    os_client = get_client()
    connected = False
    cluster_name = None
    version = None

    try:
        if os_client.ping():
            connected = True
            info = os_client.info()
            cluster_name = info.get("cluster_name")
            version = info.get("version", {}).get("number")
    except Exception:
        connected = False

    return {
        "status": "healthy",
        "opensearch": {
            "connected": connected,
            "cluster_name": cluster_name,
            "version": version,
        }
    }


@router.get("/settings")
async def get_settings():
    """Get public application settings."""
    return {
        "index_retention_days": settings.index_retention_days,
    }
