from enum import Enum
from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field

class AuditStandard(str, Enum):
    PCI_DSS_4_0 = "pci_dss_4_0"
    SOX = "sox"
    GLBA = "glba"
    ISO_27001 = "iso_27001"

class MerchantLevel(str, Enum):
    LEVEL_1 = "level_1" # > 6M txns
    LEVEL_2 = "level_2" # 1M - 6M txns
    LEVEL_3 = "level_3" # 20k - 1M txns (e-comm)
    LEVEL_4 = "level_4" # < 20k txns

class CDEComponent(BaseModel):
    name: str
    type: str # 'firewall', 'database', 'app_server', 'pos_terminal'
    ip_range: Optional[str] = None
    is_encrypted: bool = True

class FinanceProjectMetadata(BaseModel):
    """
    Schema for 'vertical_metadata' in VerticalProjectModel
    when vertical='finance'.
    """
    audit_standard: AuditStandard
    
    # Financial Reporting
    fiscal_year_end: date
    auditor_firm: Optional[str] = None
    
    # PCI Specific
    merchant_level: Optional[MerchantLevel] = None
    cde_environment_scope: List[CDEComponent] = Field(default_factory=list)
    
    # SOX Specific
    internal_controls_framework: str = "COSO"

    class Config:
        use_enum_values = True
