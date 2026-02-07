"""
Configuration for Manufacturing service.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Manufacturing service configuration."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "MANUFACTURING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/regengine_manufacturing"
    )
    
    # API Security
    API_KEY_HEADER: str = "X-RegEngine-API-Key"
    VALID_API_KEYS: list[str] = []
    
    # Service
    SERVICE_NAME: str = "manufacturing"
    SERVICE_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("MANUFACTURING_PORT", "8010"))
    
    # Compliance
    DEFAULT_RETENTION_YEARS: int = 7  # ISO audit trail requirement
    CAPA_VERIFICATION_DAYS: int = 90  # Time to verify effectiveness
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
