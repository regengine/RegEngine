
import unittest
from datetime import datetime
from services.admin.app.verticals.gaming.risk_scorer import PlayerRiskScorer, DepositEvent

class TestPlayerRiskScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = PlayerRiskScorer()
        self.base_time = datetime(2026, 1, 24, 12, 0)

    def test_structuring_detection(self):
        """Test detection of 'Structuring' (deposits just under reporting threshold)."""
        deposits = [
            DepositEvent(timestamp=self.base_time, player_id="P_SMURF_1", amount=9500.0, ip_address="1.2.3.4", method="cash"),
            DepositEvent(timestamp=self.base_time, player_id="P_SMURF_1", amount=9000.0, ip_address="1.2.3.4", method="cash"),
        ]
        
        alerts = self.scorer.analyze_deposits(deposits)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "HIGH")
        self.assertIn("structuring deposits", alerts[0].description)

    def test_syndicate_detection(self):
        """Test detection of multiple players from same IP (Smurfing Ring)."""
        deposits = [
            DepositEvent(timestamp=self.base_time, player_id="P_1", amount=100.0, ip_address="99.99.99.99", method="mobile"),
            DepositEvent(timestamp=self.base_time, player_id="P_2", amount=100.0, ip_address="99.99.99.99", method="mobile"),
            DepositEvent(timestamp=self.base_time, player_id="P_3", amount=100.0, ip_address="99.99.99.99", method="mobile"),
        ]
        
        alerts = self.scorer.analyze_deposits(deposits)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "CRITICAL")
        self.assertIn("Smurfing Ring", alerts[0].description)

if __name__ == '__main__':
    unittest.main()
