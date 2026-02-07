import pytest
import json
from unittest.mock import Mock, patch
from services.nlp.app.extractors.llm_extractor import (
    LLMGenerativeExtractor,
    LLMExtraction,
    LLMClientFactory,
    OllamaClient,
)


class TestLLMAgent:
    """Tests for the Agentic LLM Extractor with self-correction loop."""

    @pytest.fixture
    def mock_client(self):
        with patch("services.nlp.app.extractors.llm_extractor.LLMClientFactory.create") as factory:
            mock = Mock()
            mock.model = "test-model"
            factory.return_value = mock
            yield mock

    def test_happy_path(self, mock_client):
        """Ensure valid JSON parses correctly on first try."""
        mock_client.generate.return_value = json.dumps({
            "results": [
                {"provision_text": "Must report data", "obligation_type": "REQUIREMENT", "confidence": 0.9}
            ]
        })

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("Must report data within 24 hours.", "US-NY")

        assert len(results) == 1
        assert results[0].obligation_type == "REQUIREMENT"
        assert results[0].confidence == 0.9
        assert mock_client.generate.call_count == 1

    def test_self_correction_json_error(self, mock_client):
        """Agent should retry if JSON is malformed."""
        # First attempt returns garbage, second returns valid JSON
        mock_client.generate.side_effect = [
            "I am a chat bot not JSON",
            json.dumps({"results": []})
        ]

        extractor = LLMGenerativeExtractor()
        extractor.extract("some text", "US-NY")

        # Should have called twice (initial + retry)
        assert mock_client.generate.call_count == 2
        # Second call should include error feedback
        args, _ = mock_client.generate.call_args_list[1]
        assert "not valid JSON" in args[0]

    def test_self_correction_schema_error(self, mock_client):
        """Agent should retry if Schema validation fails."""
        # Invalid type for 'confidence' - provision_text must be at least 5 chars per schema
        invalid_json = json.dumps({
            "results": [{"provision_text": "Must report data", "obligation_type": "REQUIREMENT", "confidence": "HIGH"}]
        })
        valid_json = json.dumps({
            "results": [{"provision_text": "Must report data", "obligation_type": "REQUIREMENT", "confidence": 0.9}]
        })

        mock_client.generate.side_effect = [invalid_json, valid_json]

        extractor = LLMGenerativeExtractor()
        extractor.extract("Must report data within 24 hours.", "US-NY")

        assert mock_client.generate.call_count == 2
        # Feedback should mention the schema issue
        args, _ = mock_client.generate.call_args_list[1]
        assert "validation failed" in args[0]

    def test_exhausted_retries_returns_empty(self, mock_client):
        """After max retries, should return empty list gracefully."""
        mock_client.generate.side_effect = [
            "not json",
            "still not json",
            "never gonna be json",
            "last try not json",
        ]

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("some text", "US-NY")

        assert results == []
        assert mock_client.generate.call_count == 4  # 1 initial + 3 retries

    def test_hallucination_detection_penalizes_confidence(self, mock_client):
        """Provision text not in source should have confidence penalized."""
        mock_client.generate.return_value = json.dumps({
            "results": [
                {"provision_text": "hallucinated quote", "obligation_type": "REQUIREMENT", "confidence": 0.95}
            ]
        })

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("actual source text with different content", "US-NY")

        assert len(results) == 1
        # Confidence should be capped at 0.5 for hallucinated quotes
        assert results[0].confidence == 0.5

    def test_provision_text_present_keeps_confidence(self, mock_client):
        """Provision text in source should keep original confidence."""
        mock_client.generate.return_value = json.dumps({
            "results": [
                {"provision_text": "must file reports quarterly", "obligation_type": "REPORTING", "confidence": 0.95}
            ]
        })

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("Entities must file reports quarterly as per section 5.", "US-NY")

        assert len(results) == 1
        assert results[0].confidence == 0.95

    def test_empty_results_valid_schema(self, mock_client):
        """Empty results array should be valid."""
        mock_client.generate.return_value = json.dumps({"results": []})

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("no obligations here", "US-NY")

        assert results == []
        assert mock_client.generate.call_count == 1

    def test_multiple_results_extracted(self, mock_client):
        """Should handle multiple extractions."""
        mock_client.generate.return_value = json.dumps({
            "results": [
                {"provision_text": "must report", "obligation_type": "REPORTING", "confidence": 0.9},
                {"provision_text": "shall not disclose", "obligation_type": "PROHIBITION", "confidence": 0.85},
                {"provision_text": "required to maintain", "obligation_type": "REQUIREMENT", "confidence": 0.88},
            ]
        })

        extractor = LLMGenerativeExtractor()
        results = extractor.extract("must report and shall not disclose and required to maintain", "US-NY")

        assert len(results) == 3
        assert results[0].obligation_type == "REPORTING"
        assert results[1].obligation_type == "PROHIBITION"
        assert results[2].obligation_type == "REQUIREMENT"


class TestLLMClientFactory:
    """Tests for the LLMClientFactory provider selection logic."""

    def test_factory_creates_ollama_by_default(self):
        """Without env vars, should default to Ollama."""
        with patch.dict("os.environ", {}, clear=True):
            client = LLMClientFactory.create()
            assert isinstance(client, OllamaClient)
            assert client.model == "llama3:8b"

    def test_factory_creates_openai_with_gpt_model(self):
        """Should create OpenAI client when model contains 'gpt'."""
        import sys
        mock_openai_module = Mock()
        mock_openai_module.OpenAI = Mock()
        with patch.dict("os.environ", {"LLM_MODEL": "gpt-4", "OPENAI_API_KEY": "sk-test"}):
            with patch.dict(sys.modules, {"openai": mock_openai_module}):
                client = LLMClientFactory.create()
                assert client.model == "gpt-4"

    def test_factory_creates_vertex_with_gemini_model(self):
        """Should create Vertex AI client when model contains 'gemini'."""
        import sys
        mock_vertexai = Mock()
        mock_generative_models = Mock()
        mock_generative_models.GenerativeModel = Mock()
        with patch.dict("os.environ", {
            "LLM_MODEL": "gemini-1.5-pro",
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }):
            with patch.dict(sys.modules, {
                "vertexai": mock_vertexai,
                "vertexai.generative_models": mock_generative_models
            }):
                client = LLMClientFactory.create()
                assert client.model == "gemini-1.5-pro"

    def test_factory_respects_timeout_env(self):
        """Timeout should be configurable via env var."""
        with patch.dict("os.environ", {"LLM_TIMEOUT_S": "120"}, clear=True):
            client = LLMClientFactory.create()
            assert client.timeout == 120


class TestLLMExtraction:
    """Tests for the LLMExtraction Pydantic model."""

    def test_valid_extraction(self):
        """Should create valid extraction."""
        extraction = LLMExtraction(
            provision_text="must comply",
            obligation_type="REQUIREMENT",
            confidence=0.9
        )
        assert extraction.provision_text == "must comply"
        assert extraction.obligation_type == "REQUIREMENT"
        assert extraction.confidence == 0.9

    def test_confidence_bounds(self):
        """Confidence must be between 0 and 1."""
        with pytest.raises(ValueError):
            LLMExtraction(
                provision_text="test",
                obligation_type="REQUIREMENT",
                confidence=1.5
            )

    def test_extra_fields_allowed(self):
        """Extra fields should be allowed via model config."""
        extraction = LLMExtraction(
            provision_text="test",
            obligation_type="REQUIREMENT",
            confidence=0.5,
            extra_field="allowed"
        )
        assert extraction.model_dump().get("extra_field") == "allowed"
