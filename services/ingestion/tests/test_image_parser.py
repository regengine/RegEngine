
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from regengine_ingestion.parsers.image_parser import ImageParser

class TestImageParser:
    def test_can_parse_images(self):
        parser = ImageParser()
        assert parser.can_parse("image/jpeg", b"")
        assert parser.can_parse("image/png", b"")
        assert parser.can_parse("image/webp", b"")
        assert not parser.can_parse("application/pdf", b"")
        assert not parser.can_parse("text/plain", b"")

    @patch("regengine_ingestion.parsers.image_parser.LLMClient")
    def test_parse_returns_llm_data(self, MockLLMClient):
        # Setup Mock
        mock_client = MockLLMClient.return_value
        mock_client.analyze_image_structured = AsyncMock(return_value={
            "summary": "A damaged box",
            "condition": "DAMAGED",
            "shipping_labels": ["123456"]
        })

        parser = ImageParser()
        content = b"fake_image_bytes"
        metadata = {"captured_at": "2023-01-01", "user_id": "user_123"}
        
        result_json = parser.parse(content, metadata)
        
        assert "DAMAGED" in result_json
        assert "123456" in result_json
        assert "user_123" in result_json # Metadata check
        
        # Verify LLM was called
        mock_client.analyze_image_structured.assert_called_once()
