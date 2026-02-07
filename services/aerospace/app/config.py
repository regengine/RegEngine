"""
Configuration for Aerospace service.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Aerospace service configuration."""
    
    # Pydantic v2 config - ignore extra env vars
    model_config = {"extra": "ignore"}
    
    # Database
    DATABASE_URL: str = os.getenv(
        "AEROSPACE_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/regengine_aerospace"
    )
    
    # API Security
    API_KEY_HEADER: str = "X-RegEngine-API-Key"
    VALID_API_KEYS: list[str] = []
    
    # Service
    SERVICE_NAME: str = "aerospace"
    SERVICE_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("AEROSPACE_PORT", "8009"))
    
    # Compliance
    DEFAULT_RETENTION_YEARS: int = 30  # Aerospace lifecycle requirement
    BASELINE_HASH_ALGORITHM: str = "sha256"


settings = Settings()
