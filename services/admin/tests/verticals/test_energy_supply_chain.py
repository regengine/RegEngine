
import unittest
from services.admin.app.verticals.energy.supply_chain import SupplyChainValidator, SoftwareAsset, VendorPatch

class TestSupplyChainValidator(unittest.TestCase):
    def setUp(self):
        self.validator = SupplyChainValidator()
        self.patches = [
            VendorPatch(patch_id="P1", asset_name="Siemens PLC", target_version="v2.0", official_hash="hash_123_correct"),
        ]

    def test_integrity_verification(self):
        """Test detection of hash mismatch (Integrity Violation)."""
        assets = [
            # Compromised asset
            SoftwareAsset(name="Siemens PLC", version="v2.0", vendor="Siemens", file_hash="hash_999_malware", is_critical=True),
        ]
        
        alerts = self.validator.validate_hashes(assets, self.patches)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "CRITICAL")
        self.assertIn("Hash Mismatch", alerts[0].description)

    def test_unknown_baseline(self):
        """Test detection of critical asset with no vendor baseline."""
        assets = [
            SoftwareAsset(name="Mystery Box", version="v1.0", vendor="Unknown", file_hash="abc", is_critical=True),
        ]
        
        alerts = self.validator.validate_hashes(assets, self.patches)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "MEDIUM")
        self.assertIn("baseline not found", alerts[0].description)

if __name__ == '__main__':
    unittest.main()
