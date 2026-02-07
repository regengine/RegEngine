
import unittest
from datetime import datetime
from services.admin.app.verticals.technology.evidence_collector import EvidenceCollector, EvidenceRequest

class TestEvidenceCollector(unittest.TestCase):
    def setUp(self):
        self.collector = EvidenceCollector()
        self.base_time = datetime(2026, 1, 24, 12, 0)

    def test_passing_score(self):
        """Test healthy status when all evidence is collected."""
        requests = [
            EvidenceRequest(control_id="C1", evidence_type="log", status="collected", last_collected=self.base_time),
            EvidenceRequest(control_id="C2", evidence_type="log", status="collected", last_collected=self.base_time),
        ]
        
        status = self.collector.check_readiness(requests)
        
        self.assertEqual(status.overall_health, 100)
        self.assertEqual(status.public_status, "Operational")

    def test_degraded_status(self):
        """Test degraded status when evidence is missing."""
        requests = [
            EvidenceRequest(control_id="C1", evidence_type="log", status="collected", last_collected=self.base_time),
            EvidenceRequest(control_id="C2", evidence_type="log", status="missing", last_collected=self.base_time), # Fail
            EvidenceRequest(control_id="C3", evidence_type="log", status="expired", last_collected=self.base_time), # Fail
        ]
        
        status = self.collector.check_readiness(requests)
        
        self.assertEqual(status.passing_controls, 1)
        self.assertEqual(status.failing_controls, 2)
        # 33% score -> Degraded (<70)
        self.assertEqual(status.public_status, "Degraded")

if __name__ == '__main__':
    unittest.main()
