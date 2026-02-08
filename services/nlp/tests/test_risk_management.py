"""Tests for FSMA risk management extraction.

Uses sys.modules mocking ONLY for the duration of the import, then
immediately restores original modules to avoid contaminating other tests.
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ----------- Module-level mock-and-restore for import only -----------
_MOCKED_MODULES = [
    "pydantic", "pydantic.BaseModel",
    "shared", "shared.schemas",
    "structlog", "structlog.contextvars",
    "langchain", "langchain.agents",
    "openai", "jsonschema", "requests", "tenacity",
    "services.nlp.app.extractors.llm_extractor",
    "services.nlp.app.extractors.dora_extractor",
    "services.nlp.app.extractors.nydfs_extractor",
    "services.nlp.app.extractors.sec_sci_extractor",
]

# Save modules that are currently loaded
_saved = {}
for _mod_name in _MOCKED_MODULES:
    _saved[_mod_name] = sys.modules.get(_mod_name)  # None if not loaded

# Install temporary mocks
for _mod_name in _MOCKED_MODULES:
    sys.modules[_mod_name] = MagicMock()

# Add services root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Import our target (this succeeds because heavy deps are mocked)
from services.nlp.app.extractors.fsma_extractor import (
    FSMAExtractor,
    ExtractionConfidence,
    FSMAExtractionResult,
    DocumentType,
    CTE,
)

# IMMEDIATELY restore all original modules so later imports are not affected
for _mod_name in _MOCKED_MODULES:
    original = _saved[_mod_name]
    if original is None:
        sys.modules.pop(_mod_name, None)
    else:
        sys.modules[_mod_name] = original

# Also force-clear the fsma_extractor module cache so it gets re-imported
# cleanly by other tests that may need it with real dependencies
_fsma_key = "services.nlp.app.extractors.fsma_extractor"
# DON'T clear it - we still need it for our tests below. The important
# thing is that pydantic/shared/etc are restored.

del _saved, _MOCKED_MODULES
# ----------- End mock-and-restore -----------


class TestFSMARiskManagement(unittest.TestCase):
    def setUp(self):
        self.extractor = FSMAExtractor()

    def test_risk_levels(self):
        """Verify SR 11-7 confidence mapping."""
        # HIGH risk (>= 0.95)
        self.assertEqual(self.extractor._determine_risk_level(1.0), ExtractionConfidence.HIGH)
        self.assertEqual(self.extractor._determine_risk_level(0.95), ExtractionConfidence.HIGH)
        
        # MEDIUM risk (0.85 - 0.94)
        self.assertEqual(self.extractor._determine_risk_level(0.94), ExtractionConfidence.MEDIUM)
        self.assertEqual(self.extractor._determine_risk_level(0.85), ExtractionConfidence.MEDIUM)
        
        # LOW risk (< 0.85)
        self.assertEqual(self.extractor._determine_risk_level(0.84), ExtractionConfidence.LOW)
        self.assertEqual(self.extractor._determine_risk_level(0.0), ExtractionConfidence.LOW)

    def test_result_structure(self):
        """Verify extract result contains risk assessment fields."""
        result = FSMAExtractionResult(
            document_id="doc1",
            document_type=DocumentType.BILL_OF_LADING,
            ctes=[],
            extraction_timestamp="2024-01-01T00:00:00Z",
            confidence_level=ExtractionConfidence.MEDIUM,
            review_required=True
        )
        
        graph_event = self.extractor.to_graph_event(result)
        self.assertIn("risk_assessment", graph_event)
        self.assertEqual(graph_event["risk_assessment"]["level"], "MEDIUM")
        self.assertTrue(graph_event["risk_assessment"]["review_required"])

if __name__ == '__main__':
    unittest.main()
