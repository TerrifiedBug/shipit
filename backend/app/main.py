from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.routers import admin, api_upload, audit, auth, health, history, indexes, keys, patterns, upload
from app.routers.auth import get_current_user
from app.services.database import init_db
from app.services.retention import start_retention_task, stop_retention_task


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect API endpoints with authentication."""

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/api/health",
        "/api/auth/setup",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/config",
        "/api/auth/oidc/login",
        "/api/auth/callback",
    }

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require authentication)."""
        if path in self.PUBLIC_PATHS:
            return True
        # Allow abandon endpoint for page unload cleanup
        # (UUID is unguessable, only deletes pending uploads)
        if path.startswith("/api/upload/") and path.endswith("/abandon"):
            return True
        return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if self._is_public_path(path) or not path.startswith("/api/"):
            return await call_next(request)

        # Check authentication
        user = get_current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        # Store user in request state for use in endpoints
        request.state.user = user
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    init_db()
    start_retention_task()
    yield
    stop_retention_task()


app = FastAPI(
    title="ShipIt",
    description="Self-service file ingestion tool for OpenSearch",
    version="1.0.0",
    lifespan=lifespan,
)

# Add auth middleware before CORS middleware
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, prefix="/api")
app.include_router(api_upload.router)  # Has its own /api/v1 prefix
app.include_router(audit.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(indexes.router, prefix="/api")
app.include_router(keys.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(patterns.router)  # Has its own /api/patterns prefix
