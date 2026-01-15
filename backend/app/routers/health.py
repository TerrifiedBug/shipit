from fastapi import APIRouter

from app.services.opensearch import check_connection

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    opensearch_status = "connected" if check_connection() else "disconnected"
    return {"status": "healthy", "opensearch": opensearch_status}
