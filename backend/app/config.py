from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenSearch settings
    opensearch_host: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"
    opensearch_verify_certs: bool = True
    index_prefix: str = "shipit-"
    strict_index_mode: bool = True
    failure_file_retention_hours: int = 24
    max_file_size_mb: int = 500
    max_fields_per_document: int = 1000  # 0 to disable

    # Rate limiting
    upload_rate_limit_per_minute: int = 10

    # Hardcoded data directory (Docker volume mount point)
    data_dir: str = "/data"

    # Ingestion settings
    bulk_batch_size: int = 1000

    # App URL (used for CORS and OIDC callback)
    app_url: Optional[str] = None

    # Auth settings
    session_secret: str = "change-me-in-production"
    session_duration_hours: int = 8

    # OIDC settings
    oidc_enabled: bool = False
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_allowed_domain: Optional[str] = None
    oidc_admin_group: Optional[str] = None

    class Config:
        env_file = ".env"

    def get_cors_origins(self) -> list[str]:
        """Get CORS origins from APP_URL plus localhost for dev."""
        origins = ["http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:5173"]
        if self.app_url:
            origins.append(self.app_url.rstrip("/"))
        return origins

    def get_oidc_redirect_uri(self) -> str:
        """Get OIDC redirect URI derived from APP_URL."""
        base = self.app_url.rstrip("/") if self.app_url else "http://localhost:8080"
        return f"{base}/api/auth/callback"


settings = Settings()
