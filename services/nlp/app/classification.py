from __future__ import annotations

import re
from typing import Dict, List, Tuple

class SignalClassifier:
    """
    Classifies regulatory text into Categories and Risk Levels.
    """

    CATEGORIES = {
        "FOOD_SAFETY": [
            r"\b(listeria|salmonella|e\. coli|pathogen|contamination|adulterated|insanitary|filthy|putrid)\b",
            r"\b(class i recall|hazard|illness|outbreak)\b"
        ],
        "LABELING": [
            r"\b(misbranded|label|font size|nutrition facts|ingredient list|undeclared)\b",
            r"\b(net quantity|statement of identity)\b"
        ],
        "ADMINISTRATIVE": [
            r"\b(registration|filing|late fee|renewal|report|deadline)\b",
            r"\b(inspection refusal|records access)\b"
        ]
    }

    RISK_LEVELS = {
        "FOOD_SAFETY": "HIGH",
        "LABELING": "LOW",
        "ADMINISTRATIVE": "MEDIUM"
    }

    def classify_signal(self, text: str) -> Tuple[str, str, float]:
        """
        Classify text.
        
        Returns:
            Tuple of (Category, Risk_Level, Confidence)
        """
        text_lower = text.lower()
        
        best_category = "UNCATEGORIZED"
        best_score = 0.0
        
        for category, patterns in self.CATEGORIES.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    score += 1
            
            if score > best_score:
                best_score = score
                best_category = category
        
        risk = self.RISK_LEVELS.get(best_category, "LOW")
        confidence = min(0.5 + (best_score * 0.1), 0.99) if best_score > 0 else 0.0
        
        return best_category, risk, confidence
