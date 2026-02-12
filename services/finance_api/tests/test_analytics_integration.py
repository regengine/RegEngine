"""
Test Analytics Integration in Finance API
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.finance_api.service import FinanceDecisionService
from services.finance_api.models import DecisionRequest, DecisionType

class TestAnalyticsIntegration:
    
    @pytest.fixture
    def mock_graph_store(self):
        return Mock()
        
    @pytest.fixture
    def mock_bias_engine(self):
        engine = Mock()
        # Mock check_decision to return a report
        engine.check_decision.return_value = {
            "bias_detected": False,
            "dir_score": 1.2,
            "metrics": {"disparate_impact": 1.2}
        }
        return engine

    @pytest.fixture
    def service(self, mock_graph_store, mock_bias_engine):
        # Patch the entire init to avoid side effects, but set our mocks
        with patch("services.finance_api.service.FinanceGraphStore", return_value=mock_graph_store), \
             patch("services.finance_api.service.BiasEngine", return_value=mock_bias_engine), \
             patch("services.finance_api.service.create_engine"), \
             patch("services.finance_api.service.RegulatoryEngine") as MockRegEngine:
             
            # Configure Regulatory Engine Mock
            mock_reg_instance = MockRegEngine.return_value
            # return a real object or mock with attributes logic
            mock_eval = Mock()
            mock_eval.evaluation_id = "eval_123"
            mock_eval.coverage_percent = 100.0
            mock_eval.risk_level.value = "low"
            mock_eval.met_obligations = 10
            mock_eval.total_applicable_obligations = 10
            
            mock_reg_instance.evaluate_decision.return_value = mock_eval
            
            service = FinanceDecisionService(verticals_dir="./verticals")
            # Override instance attributes just in case init didn't set them (it should have)
            # Actually init uses the class we patched, so service.regulatory_engine IS mock_reg_instance
            service.graph_store = mock_graph_store
            service.bias_engine = mock_bias_engine
            return service

    def test_record_decision_triggers_bias_check(self, service, mock_bias_engine, mock_graph_store):
        """Test that recording a decision triggers bias check and graph persistence."""
        
        request = DecisionRequest(
            decision_id="test_analytics_001",
            decision_type=DecisionType.CREDIT_DENIAL,
            evidence={
                "applicant_id": "app_123",
                "income": 50000,
                "race": "black" # Protected attribute
            },
            metadata={
                "model_id": "credit_model_v1",
                "model_version": "1.0"
            }
        )
        
        # Act
        service.record_decision(request)
        
        # Assert
        # 1. Bias Engine called
        mock_bias_engine.check_decision.assert_called_once_with(request.evidence)
        
        # 2. Graph Store bias report created
        mock_graph_store.create_bias_report.assert_called_once()
        
        call_args = mock_graph_store.create_bias_report.call_args[1]
        assert call_args["model_id"] == "credit_model_v1"
        assert call_args["bias_detected"] is False
        assert call_args["dir_score"] == 1.2

    def test_missing_model_id_skips_bias_check(self, service, mock_bias_engine, mock_graph_store):
        """Test that bias check is skipped if model_id is missing."""
        
        request = DecisionRequest(
            decision_id="test_no_model_001",
            decision_type=DecisionType.CREDIT_APPROVAL,
            evidence={"score": 800},
            metadata={} # No model_id
        )
        
        service.record_decision(request)
        
        mock_bias_engine.check_decision.assert_not_called()
        mock_graph_store.create_bias_report.assert_not_called()
