from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class NercRegion(str, Enum):
    WECC = "wecc"
    TRE = "tre"
    NPCC = "npcc"
    SERC = "serc"
    RF = "rf"
    MRO = "mro"

class AssetImpactRating(str, Enum):
    HIGH = "high"     # Control Centers
    MEDIUM = "medium" # Substations
    LOW = "low"       # Generation

class EnergyProjectMetadata(BaseModel):
    """
    Schema for 'vertical_metadata' in VerticalProjectModel
    when vertical='energy'.
    """
    nerc_region: NercRegion
    asset_impact_rating: AssetImpactRating
    
    # Grid connectivity
    grid_voltage_kv: int = Field(ge=0)
    connected_load_mw: float = Field(ge=0)

    class Config:
        use_enum_values = True
