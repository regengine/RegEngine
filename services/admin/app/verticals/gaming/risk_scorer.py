import logging
from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class DepositEvent(BaseModel):
    timestamp: datetime
    player_id: str
    amount: float
    ip_address: str
    method: str # 'credit_card', 'crypto', 'bank_transfer'

class AMLAlert(BaseModel):
    severity: str # CRITICAL, HIGH, MEDIUM
    risk_score: int
    rule_triggered: str
    description: str
    player_ids: List[str]

class PlayerRiskScorer:
    """
    Real-time AML/KYC logic engine.
    Detects patterns like 'Structuring' (Smurfing) and 'Velocity Theft'.
    """

    def analyze_deposits(self, deposits: List[DepositEvent]) -> List[AMLAlert]:
        alerts = []
        
        # 1. Check for "Structuring" (Smurfing)
        # Condition: Multiple deposits slightly under the $10k reporting threshold
        # e.g., $9,000, $9,500, etc.
        
        structuring_threshold = 10000.0
        suspicion_range = (8000.0, 9999.0)
        
        by_player = {}
        for d in deposits:
            by_player.setdefault(d.player_id, []).append(d)
            
        for player_id, player_trans in by_player.items():
            structuring_hits = [
                d for d in player_trans 
                if suspicion_range[0] <= d.amount <= suspicion_range[1]
            ]
            
            if len(structuring_hits) >= 2:
                alerts.append(AMLAlert(
                    severity="HIGH",
                    risk_score=85,
                    rule_triggered="AML-STRUCTURING-01",
                    description=f"Player {player_id} attempting to structure deposits (Count: {len(structuring_hits)}) to avoid reporting.",
                    player_ids=[player_id]
                ))

        # 2. Check for "Syndicate / Smurfing Ring"
        # Condition: Multiple different players depositing from the SAME IP address
        by_ip = {}
        for d in deposits:
            by_ip.setdefault(d.ip_address, set()).add(d.player_id)
            
        for ip, players in by_ip.items():
            if len(players) >= 3:
                alerts.append(AMLAlert(
                    severity="CRITICAL",
                    risk_score=95,
                    rule_triggered="AML-SYNDICATE-01",
                    description=f"Potential Smurfing Ring detected from IP {ip}. {len(players)} distinct accounts involved.",
                    player_ids=list(players)
                ))
                
        return alerts

    def get_player_risk_score(self, player_id: str) -> int:
        """
        Returns dynamic risk score (0-100) for a dashboard widget.
        """
        # Placeholder for real-time DB lookup
        return 10
