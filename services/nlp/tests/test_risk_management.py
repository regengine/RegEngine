
import unittest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Mock dependencies before import
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic.BaseModel"] = MagicMock()
sys.modules["shared"] = MagicMock()
sys.modules["shared.schemas"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["structlog.contextvars"] = MagicMock()
# Mock potential heavy dependencies from other extractors that init might touch
sys.modules["langchain"] = MagicMock()
sys.modules["langchain.agents"] = MagicMock()
sys.modules["openai"] = MagicMock()
sys.modules["jsonschema"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["tenacity"] = MagicMock()


# Add services root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Mocking sibling files to prevent import
sys.modules["services.nlp.app.extractors.llm_extractor"] = MagicMock()
sys.modules["services.nlp.app.extractors.dora_extractor"] = MagicMock()
sys.modules["services.nlp.app.extractors.nydfs_extractor"] = MagicMock()
sys.modules["services.nlp.app.extractors.sec_sci_extractor"] = MagicMock()

# Import target directly to bypass package __init__ if possible, or letting mocks handle it
from services.nlp.app.extractors.fsma_extractor import FSMAExtractor, ExtractionConfidence, FSMAExtractionResult, DocumentType, CTE

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
        # Create a dummy result manually to check field existence
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
