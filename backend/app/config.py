from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenSearch settings
    opensearch_host: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"
    index_prefix: str = "shipit-"
    failure_file_retention_hours: int = 24
    data_dir: str = "/data"
    max_file_size_mb: int = 500

    # Auth settings
    session_secret: str = "change-me-in-production"
    session_duration_hours: int = 8
    oidc_enabled: bool = False
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
