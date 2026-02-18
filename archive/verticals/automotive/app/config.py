"""
Configuration for Automotive service.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Automotive service configuration."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "AUTOMOTIVE_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/regengine_automotive"
    )
    
    # API Security
    API_KEY_HEADER: str = "X-RegEngine-API-Key"
    VALID_API_KEYS: list[str] = []
    
    # Service
    SERVICE_NAME: str = "automotive"
    SERVICE_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("AUTOMOTIVE_PORT", "8008"))
    
    # File Storage (S3 or local)
    FILE_STORAGE_BACKEND: str = os.getenv("FILE_STORAGE_BACKEND", "local")
    FILE_STORAGE_PATH: str = os.getenv("FILE_STORAGE_PATH", "/tmp/regengine/automotive")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "regengine-automotive-ppap")
    
    # Compliance
    DEFAULT_RETENTION_YEARS: int = 10  # Part lifetime + 1 year
    MAX_FILE_SIZE_MB: int = 100  # Per element
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
