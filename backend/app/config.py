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
    max_fields_per_document: int = 1000  # 0 to disable

    # Rate limiting
    upload_rate_limit_per_minute: int = 10

    # Index retention
    index_retention_days: int = 0  # 0 to disable auto-deletion

    # Hardcoded data directory (Docker volume mount point)
    data_dir: str = "/data"

    # Ingestion settings
    bulk_batch_size: int = 1000

    # Chunked upload settings
    max_file_size_mb: int = 5000  # 5GB
    chunk_size_mb: int = 10  # 10MB chunks
    chunk_retention_hours: int = 24

    # App URL (used for CORS and OIDC callback)
    app_url: Optional[str] = None

    # Environment
    shipit_env: str = "development"

    # Auth settings
    session_secret: str = "change-me-in-production"
    session_duration_hours: int = 8

    # Security hardening
    login_rate_limit_per_minute: int = 5  # Max login attempts per IP per minute
    account_lockout_attempts: int = 5  # Lock account after N failed attempts
    account_lockout_minutes: int = 15  # Lockout duration in minutes
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = False  # Optional by default

    # Trusted proxy configuration
    trusted_proxies: list[str] = []  # CIDR ranges, e.g., ["10.0.0.0/8", "172.16.0.0/12"]

    # OIDC settings
    oidc_enabled: bool = False
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_allowed_domain: Optional[str] = None
    oidc_admin_group: Optional[str] = None
    oidc_user_groups: list[str] = []  # Groups that map to user role (if empty, all authenticated users get user role)
    oidc_viewer_groups: list[str] = []  # Groups that map to viewer role

    # GeoIP settings
    maxmind_license_key: str | None = None
    geoip_auto_update_days: int = 7  # Auto-update interval (0 to disable, MaxMind updates weekly)

    # Logging
    log_level: str = "info"  # debug, info, warning, error

    # Audit log shipping
    audit_log_to_opensearch: bool = False  # Ship audit logs to OpenSearch
    audit_log_endpoint: str | None = None  # HTTP endpoint URL (e.g., https://siem.company.com/api/logs)
    audit_log_endpoint_token: str | None = None  # Bearer token for HTTP endpoint
    audit_log_endpoint_headers: str | None = None  # Additional headers (format: Header1:value1,Header2:value2)

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

    def is_secure_cookies(self) -> bool:
        """Determine if secure cookies should be used (HTTPS environment)."""
        if self.app_url:
            return self.app_url.startswith("https://")
        return False


settings = Settings()
