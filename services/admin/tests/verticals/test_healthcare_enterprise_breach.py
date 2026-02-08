
import unittest
from datetime import datetime
from services.admin.app.verticals.healthcare_enterprise.breach_calculator import BreachRiskCalculator, AccessLogEntry

class TestBreachRiskCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = BreachRiskCalculator()
        self.base_time = datetime(2026, 1, 24, 12, 0)

    def test_vip_snooping_detection(self):
        """Test detection of multiple staff accessing a VIP record."""
        logs = [
            # 4 distinct users accessing the same VIP patient
            AccessLogEntry(timestamp=self.base_time, user_id="nurse_jackie", role="nurse", patient_id="VIP_001", record_type="clinical_notes", action="view", is_vip=True),
            AccessLogEntry(timestamp=self.base_time, user_id="dr_house", role="doctor", patient_id="VIP_001", record_type="clinical_notes", action="view", is_vip=True),
            AccessLogEntry(timestamp=self.base_time, user_id="admin_bill", role="admin", patient_id="VIP_001", record_type="demographics", action="view", is_vip=True),
            AccessLogEntry(timestamp=self.base_time, user_id="intern_jim", role="intern", patient_id="VIP_001", record_type="clinical_notes", action="view", is_vip=True),
        ]
        
        alerts = self.calculator.analyze_access_pattern(logs)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "HIGH")
        self.assertIn("Potential VIP Snooping", alerts[0].description)

    def test_clinical_mismatch_detection(self):
        """Test detection of non-clinical staff accessing clinical notes."""
        logs = [
            AccessLogEntry(timestamp=self.base_time, user_id="billing_linda", role="billing", patient_id="PAT_100", record_type="clinical_notes", action="view", is_vip=False),
        ]
        
        alerts = self.calculator.analyze_access_pattern(logs)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "MEDIUM")
        self.assertIn("Clinical Mismatch", alerts[0].description)

    def test_normal_access(self):
        """Test that normal authorized access triggers no alerts."""
        logs = [
            AccessLogEntry(timestamp=self.base_time, user_id="nurse_jackie", role="nurse", patient_id="PAT_100", record_type="clinical_notes", action="view", is_vip=False),
            AccessLogEntry(timestamp=self.base_time, user_id="dr_house", role="doctor", patient_id="PAT_100", record_type="xray", action="view", is_vip=False),
        ]
        
        alerts = self.calculator.analyze_access_pattern(logs)
        self.assertEqual(len(alerts), 0)

if __name__ == '__main__':
    unittest.main()
