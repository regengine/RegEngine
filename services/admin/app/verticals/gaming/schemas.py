from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class GamingJurisdiction(str, Enum):
    NEVADA = "nevada"
    NEW_JERSEY = "new_jersey"
    PENNSYLVANIA = "pennsylvania"
    UK_GC = "uk_gc"
    MALTA = "malta"

class LicenseType(str, Enum):
    CASINO = "casino"
    SPORTS_BETTING = "sports_betting"
    POKER = "poker"
    LOTTERY = "lottery"

class GamingProjectMetadata(BaseModel):
    """
    Schema for 'vertical_metadata' in VerticalProjectModel
    when vertical='gaming'.
    """
    jurisdiction: GamingJurisdiction
    license_number: str
    license_type: LicenseType
    
    # Financial thresholds for AML
    aml_reporting_threshold_usd: float = 10000.00
    kyc_trigger_threshold_usd: float = 2000.00
    
    # Responsible Gaming
    self_exclusion_db_integrated: bool = False

    class Config:
        use_enum_values = True
