"""Configuration models for the ingestion framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml


class SourceType(str, Enum):
    """Supported document sources."""
    
    FEDERAL_REGISTER = "federal_register"
    ECFR = "ecfr"
    FDA = "fda"
    WEB_CRAWLER = "web_crawler"
    MANUAL_UPLOAD = "manual_upload"


class StorageBackend(str, Enum):
    """Storage backend options."""
    
    FILESYSTEM = "filesystem"
    S3 = "s3"


@dataclass
class VerticalConfig:
    """Configuration for a specific regulatory vertical."""
    
    name: str
    cfr_titles: List[int] = field(default_factory=list)
    agencies: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    
    requests_per_minute: int = 60
    exponential_backoff: bool = True
    max_retries: int = 3
    respect_retry_after: bool = True


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    
    host: str = "localhost"
    port: int = 5432
    database: str = "regengine"
    user: str = "regengine"
    password: str = ""
    schema: str = "ingestion"


@dataclass
class StorageConfig:
    """Storage configuration."""
    
    backend: StorageBackend = StorageBackend.FILESYSTEM
    filesystem_path: Optional[Path] = None
    s3_bucket: Optional[str] = None
    s3_prefix: str = "documents"


@dataclass
class IngestionConfig:
    """Main ingestion configuration."""
    
    source_type: SourceType
    vertical: str
    max_documents: int = 100
    parallel_workers: int = 1
    
    # Source-specific config
    source_config: Dict = field(default_factory=dict)
    
    # Date filtering
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    # Rate limiting
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    # Robots.txt compliance
    respect_robots: bool = True
    
    # User agent
    user_agent: str = "RegEngine Ingestion Bot/1.0"
    
    # Audit trail
    audit_enabled: bool = True
    
    @classmethod
    def from_yaml(cls, path: Path) -> "IngestionConfig":
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        # Convert nested dicts to dataclass instances
        if "rate_limit" in data:
            data["rate_limit"] = RateLimitConfig(**data["rate_limit"])
        
        return cls(**data)


@dataclass
class FrameworkConfig:
    """Complete framework configuration."""
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    verticals: Dict[str, VerticalConfig] = field(default_factory=dict)
    
    # FDA API key (optional but recommended)
    fda_api_key: Optional[str] = None
    
    @classmethod
    def from_yaml(cls, path: Path) -> "FrameworkConfig":
        """Load framework configuration from YAML."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        # Convert nested structures
        if "database" in data:
            data["database"] = DatabaseConfig(**data["database"])
        
        if "storage" in data:
            storage_data = data["storage"]
            if "backend" in storage_data:
                storage_data["backend"] = StorageBackend(storage_data["backend"])
            if "filesystem_path" in storage_data:
                storage_data["filesystem_path"] = Path(storage_data["filesystem_path"])
            data["storage"] = StorageConfig(**storage_data)
        
        if "verticals" in data:
            data["verticals"] = {
                name: VerticalConfig(name=name, **config)
                for name, config in data["verticals"].items()
            }
        
        return cls(**data)
    
    @classmethod
    def default(cls) -> "FrameworkConfig":
        """Create default configuration."""
        return cls(
            verticals={
                "fsma": VerticalConfig(
                    name="fsma",
                    cfr_titles=[21],
                    agencies=["FDA"],
                    keywords=["traceability", "food", "safety", "FSMA"]
                ),
                "energy": VerticalConfig(
                    name="energy",
                    cfr_titles=[10, 18],
                    agencies=["DOE", "FERC"],
                    keywords=["energy", "grid", "compliance"]
                ),
                "nuclear": VerticalConfig(
                    name="nuclear",
                    cfr_titles=[10],
                    agencies=["NRC"],
                    keywords=["nuclear", "reactor", "safety"]
                ),
                "healthcare": VerticalConfig(
                    name="healthcare",
                    cfr_titles=[42, 45],
                    agencies=["HHS", "CMS"],
                    keywords=["healthcare", "HIPAA", "medicare"]
                ),
            }
        )
