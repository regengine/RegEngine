"""Compliance Arbitrage Detector for NLP Service."""

from typing import List, Dict, Any, Tuple
import regex as re
import structlog

logger = structlog.get_logger("nlp-api.arbitrage")


class ComplianceArbitrageDetector:
    """
    Identifies arbitrage opportunities by detecting overlapping obligations.
    
    Compliance Arbitrage (n): The strategic selection of a single control or 
    process that satisfies multiple regulatory requirements across different 
    frameworks or jurisdictions.
    """
    
    def __init__(self):
        # Patterns for identifying core obligation themes
        self.THEMES = {
            "DATA_PRIVACY": r"\b(privacy|personal data|pii|data protection|consent)\b",
            "CYBER_SECURITY": r"\b(encryption|access control|vulnerability|firewall|incident)\b",
            "TRACEABILITY": r"\b(lot code|traceability|tracking|kde|cte|source|origin)\b",
            "QUALITY_CONTROL": r"\b(inspection|sampling|testing|quality|specification)\b",
        }

    def detect_arbitrage_themes(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect themes within an obligation text to identify potential arbitrage.
        """
        text_lower = text.lower()
        found_themes = []
        
        for theme, pattern in self.THEMES.items():
            if re.search(pattern, text_lower, re.I):
                found_themes.append({
                    "theme": theme,
                    "confidence": 0.85,
                    "rationale": f"Matched thematic pattern for {theme}"
                })
        
        return found_themes

    def calculate_savings_potential(self, themes: List[Dict]) -> float:
        """
        Estimate the complexity reduction / savings factor.
        """
        if not themes:
            return 0.0
            
        # Basic heuristic: more overlapping themes = higher arbitrage value
        base_factor = 0.2  # 20% baseline for any detected theme
        multi_theme_bonus = (len(themes) - 1) * 0.15
        
        return min(base_factor + multi_theme_bonus, 0.8) # Cap at 80% savings
