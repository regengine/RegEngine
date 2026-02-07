"""
Configuration for Construction service.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Construction service configuration."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "CONSTRUCTION_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/regengine_construction"
    )
    
    # API Security
    API_KEY_HEADER: str = "X-RegEngine-API-Key"
    
    # Service
    SERVICE_NAME: str = "construction"
    SERVICE_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("CONSTRUCTION_PORT", "8011"))
    
    # Compliance
    DEFAULT_RETENTION_YEARS: int = 7
    OSHA_INSPECTION_FREQUENCY_DAYS: int = 7  # Weekly inspections
    
    class Config:
        env_file = ".env"


settings = Settings()
