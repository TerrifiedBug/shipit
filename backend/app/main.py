from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, health, history, keys, upload
from app.services.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    init_db()
    yield


app = FastAPI(
    title="ShipIt",
    description="Self-service file ingestion tool for OpenSearch",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(keys.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
