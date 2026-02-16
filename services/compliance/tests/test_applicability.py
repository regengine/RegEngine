import os
import sys
import importlib.util
import pytest
from pathlib import Path

# Identify project root
root = Path(__file__).resolve().parent.parent.parent.parent
# Add root to sys.path first to ensure global 'shared' is picked up
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

# Load fsma_engine from absolute path without adding its parent to sys.path
# This prevents services/compliance/shared from shadowing root/shared
service_dir = Path(__file__).resolve().parent.parent
engine_path = service_dir / "fsma_engine.py"
spec = importlib.util.spec_from_file_location("fsma_engine", str(engine_path))
fsma_engine = importlib.util.module_from_spec(spec)
sys.modules["fsma_engine"] = fsma_engine
spec.loader.exec_module(fsma_engine)

from fsma_engine import FSMAApplicabilityEngine

@pytest.fixture
def engine():
    return FSMAApplicabilityEngine()

def test_get_ftl_categories(engine):
    categories = engine.get_applicability_checklist()
    assert len(categories) > 0
    assert any(c["id"] == "leafy_greens_intact" for c in categories)

def test_evaluate_applicability_covered(engine):
    selection = ["leafy_greens_intact", "eggs"]
    result = engine.evaluate_applicability(selection)
    assert result["is_applicable"] is True
    assert len(result["covered_categories"]) == 2
    assert "Handles items on the FDA Food Traceability List" in result["reason"]

def test_evaluate_applicability_not_covered(engine):
    selection = ["non_existent_category"]
    result = engine.evaluate_applicability(selection)
    assert result["is_applicable"] is False
    assert len(result["covered_categories"]) == 0
    assert "No FTL items handled" in result["reason"]

def test_evaluate_exemption_small_farm(engine):
    profile = {
        "business_type": "farm",
        "annual_food_sales": 20000
    }
    result = engine.evaluate_exemptions(profile)
    assert result["is_fully_exempt"] is True
    assert result["status"] == "EXEMPT"
    assert any(e["id"] == "small_farm" for e in result["active_exemptions"])

def test_evaluate_exemption_large_farm(engine):
    profile = {
        "business_type": "farm",
        "annual_food_sales": 100000
    }
    result = engine.evaluate_exemptions(profile)
    assert result["is_fully_exempt"] is False
    assert result["status"] == "NOT_EXEMPT"
    assert len(result["active_exemptions"]) == 0

def test_evaluate_exemption_restaurant_threshold(engine):
    profile = {
        "business_type": "restaurant",
        "annual_food_sales": 200000
    }
    result = engine.evaluate_exemptions(profile)
    assert result["is_fully_exempt"] is True
    assert result["status"] == "EXEMPT"
    assert any(e["id"] == "small_retail" for e in result["active_exemptions"])

def test_evaluate_exemption_kill_step(engine):
    profile = {
        "business_type": "processor",
        "annual_food_sales": 1000000,
        "kill_step_applied": True
    }
    result = engine.evaluate_exemptions(profile)
    assert result["is_fully_exempt"] is False
    assert result["status"] == "PARTIALLY_EXEMPT"
    assert any(e["id"] == "kill_step" for e in result["active_exemptions"])

def test_evaluate_exemption_rcr(engine):
    profile = {
        "business_type": "farm",
        "annual_food_sales": 1000000,
        "rarely_consumed_raw": True
    }
    result = engine.evaluate_exemptions(profile)
    assert result["is_fully_exempt"] is True
    assert result["status"] == "EXEMPT"
    assert any(e["id"] == "rcr" for e in result["active_exemptions"])
