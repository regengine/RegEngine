from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class FacilityType(str, Enum):
    FREE_CLINIC = "free_clinic"
    CHARITABLE_CLINIC = "charitable_clinic"
    FQHC_LOOKALIKE = "fqhc_lookalike"
    RURAL_HEALTH_CLINIC = "rural_health_clinic"
    OTHER = "other"

class OperatingState(str, Enum):
    ACTIVE = "active"
    STARTUP = "startup"
    WINDING_DOWN = "winding_down"

class HealthcareProjectMetadata(BaseModel):
    """
    Schema for 'vertical_metadata' in VerticalProjectModel
    when vertical='healthcare'.
    """
    facility_type: FacilityType = Field(..., description="Type of clinic facility")
    operating_state: OperatingState = Field(default=OperatingState.ACTIVE)
    
    # Core Operational Declarations
    dispenses_medication: bool = Field(False, description="Does the clinic dispense medication on-site?")
    has_paid_staff: bool = Field(False, description="Does the clinic have paid staff?")
    annual_patient_volume: Optional[int] = Field(None, description="Approximate annual patient volume")
    
    # Location
    state: str = Field(..., min_length=2, max_length=2, description="Two-letter state code (e.g. CA)")
    county: Optional[str] = Field(None, description="County name")

    class Config:
        use_enum_values = True

class HealthcareRuleStatus(str, Enum):
    GREEN = "green"   # Safe / Compliant
    YELLOW = "yellow" # Warning / Attention Needed
    RED = "red"       # Unsafe / Non-Compliant
    GRAY = "gray"     # Not Applicable / Pending
