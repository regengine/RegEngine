"""
Tests for the Compliance service.

Validates configuration loading, analysis engine behavior, and
notification triggering.
"""

import hashlib
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class TestComplianceConfig:
    """Test configuration loading and defaults."""

    def test_default_settings_load(self):
        """Config class should instantiate with sensible defaults."""
        from app.config import Settings

        settings = Settings()
        assert settings.service_name == "RegEngine Compliance API"
        assert settings.service_version == "1.0.0"
        assert settings.port == 8500
        assert settings.log_level == "INFO"

    def test_cors_origins_default(self):
        """Default CORS origins should include localhost dev ports."""
        from app.config import Settings

        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:8080" in settings.cors_origins

    def test_neo4j_uri_optional(self):
        """Neo4j URI should default to None (optional dependency)."""
        import os
        from unittest.mock import patch as mpatch
        with mpatch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEO4J_URI", None)
            from app.config import Settings
            settings = Settings(_env_file=None)
            assert settings.neo4j_uri is None

    def test_get_settings_cached(self):
        """get_settings should return the same cached instance."""
        from app.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestAnalysisEngine:
    """Test the compliance analysis engine."""

    @pytest.mark.asyncio
    async def test_analysis_returns_summary(self):
        """Analysis should return a complete AnalysisSummary."""
        from app.analysis import AnalysisEngine

        engine = AnalysisEngine()
        with patch("app.analysis.notify_hazard", new_callable=AsyncMock):
            result = await engine.analyze_document("test-doc-001")

        assert result.document_id == "test-doc-001"
        assert result.status == "COMPLETE"
        assert 0 <= result.risk_score <= 100
        assert result.obligations_count >= 5

    @pytest.mark.asyncio
    async def test_deterministic_results(self):
        """Same document ID should produce same results."""
        from app.analysis import AnalysisEngine

        engine = AnalysisEngine()
        with patch("app.analysis.notify_hazard", new_callable=AsyncMock):
            result1 = await engine.analyze_document("deterministic-test")
            result2 = await engine.analyze_document("deterministic-test")

        assert result1.risk_score == result2.risk_score
        assert result1.obligations_count == result2.obligations_count
        assert len(result1.critical_risks) == len(result2.critical_risks)

    @pytest.mark.asyncio
    async def test_different_docs_may_differ(self):
        """Different document IDs should generally produce different scores."""
        from app.analysis import AnalysisEngine

        engine = AnalysisEngine()
        with patch("app.analysis.notify_hazard", new_callable=AsyncMock):
            result_a = await engine.analyze_document("doc-alpha")
            result_b = await engine.analyze_document("doc-beta-999")

        # Not guaranteed to differ, but highly likely with SHA-256
        # We just verify both completed without error
        assert result_a.status == "COMPLETE"
        assert result_b.status == "COMPLETE"

    @pytest.mark.asyncio
    async def test_high_risk_generates_critical_risks(self):
        """Documents with hash > 80 should generate critical risks."""
        from app.analysis import AnalysisEngine

        # Find a document ID that produces a high risk score
        engine = AnalysisEngine()
        for i in range(100):
            doc_id = f"scan-{i}"
            h = int(hashlib.sha256(doc_id.encode()).hexdigest(), 16)
            if (h % 100) > 80:
                with patch("app.analysis.notify_hazard", new_callable=AsyncMock):
                    result = await engine.analyze_document(doc_id)
                assert any(r.severity == "CRITICAL" for r in result.critical_risks)
                return

        pytest.skip("No document ID produced a high-risk score in 100 tries")

    @pytest.mark.asyncio
    async def test_notification_called(self):
        """Analysis should trigger hazard notification."""
        from app.analysis import AnalysisEngine

        engine = AnalysisEngine()
        with patch("app.analysis.notify_hazard", new_callable=AsyncMock) as mock_notify:
            await engine.analyze_document("notify-test")
            mock_notify.assert_called_once()


class TestComplianceDirectoryStructure:
    """Verify the compliance service has the expected layout."""

    def test_app_directory_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "app").is_dir(), "Missing app/ directory"

    def test_requirements_file_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "requirements.txt").is_file(), "Missing requirements.txt"

    def test_analysis_module_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "app" / "analysis.py").is_file(), "Missing app/analysis.py"

    def test_models_module_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "app" / "models.py").is_file(), "Missing app/models.py"
