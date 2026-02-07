import logging
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SoftwareAsset(BaseModel):
    name: str 
    version: str
    vendor: str
    file_hash: str # SHA-256
    is_critical: bool = False

class VendorPatch(BaseModel):
    patch_id: str
    asset_name: str
    target_version: str
    official_hash: str # From vendor website

class ComplianceAlert(BaseModel):
    severity: str
    rule_id: str
    description: str
    asset_name: str

class SupplyChainValidator:
    """
    Validates software integrity for NERC CIP-013 (Supply Chain Risk Management).
    Simulates checking installed firmware hashes against vendor baselines.
    """

    def validate_hashes(self, assets: List[SoftwareAsset], trusted_patches: List[VendorPatch]) -> List[ComplianceAlert]:
        alerts = []
        
        # Create lookup for trusted patches
        trusted_db = {p.asset_name: p for p in trusted_patches}
        
        for asset in assets:
            if asset.is_critical:
                if asset.name not in trusted_db:
                    alerts.append(ComplianceAlert(
                        severity="MEDIUM",
                        rule_id="CIP-013-UNKNOWN",
                        description=f"Standard baseline not found for critical asset: {asset.name}.",
                        asset_name=asset.name
                    ))
                    continue
                
                trusted = trusted_db[asset.name]
                if asset.file_hash != trusted.official_hash:
                    alerts.append(ComplianceAlert(
                        severity="CRITICAL",
                        rule_id="CIP-010-INTEGRITY",
                        description=f"Hash Mismatch! Installed firmware hash {asset.file_hash[:8]}... does not match vendor official hash {trusted.official_hash[:8]}...",
                        asset_name=asset.name
                    ))
                    
        return alerts
