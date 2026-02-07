from __future__ import annotations

import structlog
from typing import Optional, Dict

logger = structlog.get_logger("nlp.resolution")

# Stubbed Master Data (Simulating a MDM System / DUNS Database)
MASTER_DATA = {
    "WALMART": {"id": "duns:007874200", "name": "Walmart Inc.", "type": "RETAILER"},
    "WAL-MART": {"id": "duns:007874200", "name": "Walmart Inc.", "type": "RETAILER"},
    "COSTCO": {"id": "duns:009289230", "name": "Costco Wholesale Corp.", "type": "RETAILER"},
    "COSTCO WHOLESALE": {"id": "duns:009289230", "name": "Costco Wholesale Corp.", "type": "RETAILER"},
    "RALPHS": {"id": "duns:009289555", "name": "Ralphs Grocery Company", "type": "RETAILER"},
    "KROGER": {"id": "duns:006999528", "name": "The Kroger Co.", "type": "RETAILER"},
    
    # Common Suppliers (Stubbed)
    "TYSON FOODS": {"id": "duns:006903702", "name": "Tyson Foods, Inc.", "type": "SUPPLIER"},
    "DOLE": {"id": "duns:006903111", "name": "Dole Food Company", "type": "SUPPLIER"},
    "DRISCOLL'S": {"id": "duns:009212345", "name": "Driscoll's Inc.", "type": "SUPPLIER"},
    "TAYLOR FARMS": {"id": "duns:009255555", "name": "Taylor Fresh Foods, Inc.", "type": "SUPPLIER"},
}

class EntityResolver:
    """
    Resolves raw entity text to canonical Entity IDs (Master Data).
    """

    def resolve_organization(self, raw_name: str) -> Optional[Dict]:
        """
        Resolve an organization name to a canonical entity.
        
        Args:
            raw_name: The extracted text (e.g. "Wal-Mart Stores")
            
        Returns:
            Dict containing canonical ID and Name, or None if no match.
        """
        if not raw_name:
            return None
            
        # 1. Normalization
        normalized = raw_name.upper().strip()
        
        # Remove common suffixes for matching
        clean_name = normalized.replace(" INC.", "").replace(" LLC", "").replace(" CORP.", "").strip()
        
        # 2. Exact Match (against normalized keys)
        if clean_name in MASTER_DATA:
            match = MASTER_DATA[clean_name]
            logger.info("entity_resolved", raw=raw_name, resolved=match["name"], id=match["id"])
            return match
            
        # 3. Fuzzy / Partial Match (Simple containment for this MVP)
        # In prod, use Levenshtein distance
        for key, data in MASTER_DATA.items():
            if key in clean_name or clean_name in key:
                # preventing very short matches
                if len(key) > 3 and len(clean_name) > 3:
                     logger.info("entity_resolved_fuzzy", raw=raw_name, resolved=data["name"], id=data["id"])
                     return data
                     
        return None
