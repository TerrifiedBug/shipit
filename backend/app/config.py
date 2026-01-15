from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    opensearch_host: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"
    index_prefix: str = "shipit-"
    failure_file_retention_hours: int = 24
    data_dir: str = "/data"
    max_file_size_mb: int = 500

    class Config:
        env_file = ".env"


settings = Settings()
