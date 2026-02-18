"""
FDA Live API Client.

Provides specialized access to openFDA and 510(k) premarket notification data.
"""
import os
import requests
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("fda-client")

class FDAClient:
    """
    Client for FDA Open Data.
    
    Target Endpoints:
    - /device/510k.json (Premarket Notifications)
    - /food/enforcement.json (Recalls)
    """
    
    BASE_URL = "https://api.fda.gov"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FDA_API_KEY")
        
    def query_510k(self, medical_specialty: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Queries 510(k) premarket notifications by specialty."""
        url = f"{self.BASE_URL}/device/510k.json"
        params = {
            "search": f'medical_specialty_description:"{medical_specialty}"',
            "limit": limit
        }
        if self.api_key:
            params["api_key"] = self.api_key
            
        try:
            logger.info(f"Querying FDA 510(k) for: {medical_specialty}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            logger.error(f"FDA Query Failed: {e}")
            return []

    def verify_device(self, k_number: str) -> Optional[Dict[str, Any]]:
        """Verifies a specific 510(k) record by K-Number."""
        url = f"{self.BASE_URL}/device/510k.json"
        params = {
            "search": f'k_number:"{k_number}"',
            "limit": 1
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            results = response.json().get("results", [])
            return results[0] if results else None
        except Exception as e:
            logger.error(f"FDA Verification Failed: {e}")
            return None
