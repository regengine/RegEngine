"""
Configuration for Gaming service.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gaming service configuration."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "GAMING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/regengine_gaming"
    )
    
    # API Security
    API_KEY_HEADER: str = "X-RegEngine-API-Key"
    VALID_API_KEYS: list[str] = []  # Loaded from env or secrets manager
    
    # Service
    SERVICE_NAME: str = "gaming"
    SERVICE_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("GAMING_PORT", "8007"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Compliance
    DEFAULT_RETENTION_DAYS: int = 1825  # 5 years (typical minimum)
    PROBLEM_GAMBLING_THRESHOLD: int = 70  # Risk score threshold for intervention
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
