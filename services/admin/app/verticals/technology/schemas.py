from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

class HostingProvider(str, Enum):
    CLOUD = "cloud"
    GCP = "gcp"
    AZURE = "azure"
    ON_PREM = "on_prem"

class TechProjectMetadata(BaseModel):
    """
    Schema for 'vertical_metadata' in VerticalProjectModel
    when vertical='technology'.
    """
    hosting_provider: HostingProvider
    data_classification: List[DataClassification]
    
    # SOC 2 Scope
    include_security: bool = True
    include_availability: bool = False
    include_confidentiality: bool = False
    include_processing_integrity: bool = False
    include_privacy: bool = False

    class Config:
        use_enum_values = True
