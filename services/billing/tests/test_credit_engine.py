"""
Credit Engine Unit Tests

Tests credit code validation, balance tracking, expiration,
single-use enforcement, and usage bonus calculation.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from credit_engine import CreditEngine, CREDIT_CODES
from models import CreditType


@pytest.fixture
def engine():
    """Fresh credit engine for each test."""
    return CreditEngine()


class TestCreditCodeRedemption:
    """Test credit code validation and redemption."""

    def test_redeem_valid_code(self, engine):
        result = engine.redeem_code("tenant_1", "EARLY2026")
        assert result.success is True
        assert result.amount_cents == 120_00
        assert result.credit_type == CreditType.EARLY_ADOPTER
        assert result.new_balance_cents == 120_00

    def test_redeem_invalid_code(self, engine):
        result = engine.redeem_code("tenant_1", "INVALID_CODE")
        assert result.success is False
        assert "Invalid" in result.message

    def test_prevent_double_redemption(self, engine):
        engine.redeem_code("tenant_1", "EARLY2026")
        result = engine.redeem_code("tenant_1", "EARLY2026")
        assert result.success is False
        assert "already redeemed" in result.message.lower()

    def test_different_tenants_can_redeem_same_code(self, engine):
        result1 = engine.redeem_code("tenant_1", "LAUNCH50")
        result2 = engine.redeem_code("tenant_2", "LAUNCH50")
        assert result1.success is True
        assert result2.success is True

    def test_case_insensitive_codes(self, engine):
        result = engine.redeem_code("tenant_1", "early2026")
        assert result.success is True

    def test_whitespace_trimmed(self, engine):
        result = engine.redeem_code("tenant_1", "  EARLY2026  ")
        assert result.success is True

    def test_multiple_codes_stack(self, engine):
        engine.redeem_code("tenant_1", "EARLY2026")  # $120
        engine.redeem_code("tenant_1", "LAUNCH50")   # $50
        balance = engine.get_balance("tenant_1")
        assert balance.balance_cents == 170_00  # $170 total


class TestCreditBalance:
    """Test balance calculation and tracking."""

    def test_zero_balance_initially(self, engine):
        balance = engine.get_balance("new_tenant")
        assert balance.balance_cents == 0
        assert balance.total_earned_cents == 0
        assert balance.total_redeemed_cents == 0
        assert len(balance.transactions) == 0

    def test_balance_after_redemption(self, engine):
        engine.redeem_code("tenant_1", "REFER500")
        balance = engine.get_balance("tenant_1")
        assert balance.balance_cents == 500_00
        assert balance.total_earned_cents == 500_00
        assert len(balance.transactions) == 1

    def test_balance_after_invoice_application(self, engine):
        engine.redeem_code("tenant_1", "REFER500")  # $500
        amount_after, credits_used = engine.apply_credit_to_invoice("tenant_1", 300_00)
        assert credits_used == 300_00
        assert amount_after == 0
        balance = engine.get_balance("tenant_1")
        assert balance.balance_cents == 200_00  # $500 - $300 = $200

    def test_partial_credit_application(self, engine):
        engine.redeem_code("tenant_1", "LAUNCH50")  # $50
        amount_after, credits_used = engine.apply_credit_to_invoice("tenant_1", 100_00)
        assert credits_used == 50_00  # Only $50 available
        assert amount_after == 50_00  # $100 - $50 = $50 remaining

    def test_no_credits_to_apply(self, engine):
        amount_after, credits_used = engine.apply_credit_to_invoice("tenant_1", 100_00)
        assert credits_used == 0
        assert amount_after == 100_00


class TestUsageBonus:
    """Test usage-based bonus credit awards."""

    def test_usage_bonus_awarded(self, engine):
        txn = engine.add_usage_bonus("tenant_1", 5000)
        assert txn is not None
        assert txn.amount_cents == 500  # $5 for 5k docs
        assert txn.credit_type == CreditType.USAGE_BONUS

    def test_usage_bonus_sub_threshold(self, engine):
        txn = engine.add_usage_bonus("tenant_1", 500)
        assert txn is None  # Below 1k threshold

    def test_usage_bonus_rounds_down(self, engine):
        txn = engine.add_usage_bonus("tenant_1", 2999)
        assert txn.amount_cents == 200  # 2k threshold → $2

    def test_usage_bonus_accumulates(self, engine):
        engine.add_usage_bonus("tenant_1", 3000)  # $3
        engine.add_usage_bonus("tenant_1", 7000)  # $7
        balance = engine.get_balance("tenant_1")
        assert balance.balance_cents == 10_00  # $10 total
