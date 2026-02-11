"""
Billing Service — Credit Program Engine

In-memory credit ledger for dev/sandbox. Supports referral codes,
early adopter discounts, usage bonuses, and partner credits.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from models import (
    CreditBalance,
    CreditTransaction,
    CreditType,
    RedeemCreditResponse,
)

logger = structlog.get_logger(__name__)


# ── Credit Code Registry ──────────────────────────────────────────
# Pre-configured credit codes (would be DB-backed in production)

CREDIT_CODES: dict[str, dict] = {
    "EARLY2026": {
        "type": CreditType.EARLY_ADOPTER,
        "amount_cents": 120_00,  # $120 credit
        "description": "Early adopter credit — 20% off first year",
        "max_uses": 500,
        "uses": 0,
        "expires_at": datetime(2026, 6, 30),
    },
    "REFER500": {
        "type": CreditType.REFERRAL,
        "amount_cents": 500_00,  # $500 credit
        "description": "Referral reward — $500 account credit",
        "max_uses": None,  # Unlimited
        "uses": 0,
        "expires_at": None,
    },
    "PARTNER100": {
        "type": CreditType.PARTNER,
        "amount_cents": 100_00,  # $100 credit
        "description": "Channel partner welcome credit",
        "max_uses": 1000,
        "uses": 0,
        "expires_at": datetime(2026, 12, 31),
    },
    "LAUNCH50": {
        "type": CreditType.PROMO,
        "amount_cents": 50_00,  # $50 credit
        "description": "Launch promotion — $50 off your first month",
        "max_uses": 200,
        "uses": 0,
        "expires_at": datetime(2026, 3, 31),
    },
}


class CreditEngine:
    """In-memory credit program engine.

    Tracks credit balances per tenant, validates and redeems codes,
    and maintains a full transaction ledger.
    """

    def __init__(self):
        # tenant_id → list of CreditTransaction
        self._transactions: dict[str, list[CreditTransaction]] = {}
        # tenant_id → set of redeemed codes (prevent double-use)
        self._redeemed_codes: dict[str, set[str]] = {}

    def get_balance(self, tenant_id: str) -> CreditBalance:
        """Get current credit balance for a tenant."""
        transactions = self._transactions.get(tenant_id, [])

        now = datetime.utcnow()
        active_transactions = [
            t for t in transactions
            if t.expires_at is None or t.expires_at > now
        ]

        total_earned = sum(t.amount_cents for t in active_transactions if t.amount_cents > 0)
        total_redeemed = abs(sum(t.amount_cents for t in active_transactions if t.amount_cents < 0))
        balance = total_earned - total_redeemed

        return CreditBalance(
            tenant_id=tenant_id,
            balance_cents=max(0, balance),
            total_earned_cents=total_earned,
            total_redeemed_cents=total_redeemed,
            transactions=active_transactions,
        )

    def redeem_code(self, tenant_id: str, code: str) -> RedeemCreditResponse:
        """Validate and redeem a credit code."""
        code_upper = code.upper().strip()

        # Check code exists
        code_def = CREDIT_CODES.get(code_upper)
        if code_def is None:
            logger.info("credit_code_invalid", code=code_upper, tenant_id=tenant_id)
            return RedeemCreditResponse(
                success=False,
                message=f"Invalid credit code: {code_upper}",
            )

        # Check expiration
        if code_def["expires_at"] and datetime.utcnow() > code_def["expires_at"]:
            return RedeemCreditResponse(
                success=False,
                message=f"Credit code {code_upper} has expired",
            )

        # Check max uses
        if code_def["max_uses"] is not None and code_def["uses"] >= code_def["max_uses"]:
            return RedeemCreditResponse(
                success=False,
                message=f"Credit code {code_upper} has reached its maximum uses",
            )

        # Check tenant hasn't already redeemed this code
        redeemed = self._redeemed_codes.get(tenant_id, set())
        if code_upper in redeemed:
            return RedeemCreditResponse(
                success=False,
                message=f"You've already redeemed code {code_upper}",
            )

        # Apply the credit
        transaction = CreditTransaction(
            tenant_id=tenant_id,
            credit_type=code_def["type"],
            amount_cents=code_def["amount_cents"],
            code=code_upper,
            description=code_def["description"],
            expires_at=(
                datetime.utcnow() + timedelta(days=365)
                if code_def["expires_at"] is None
                else code_def["expires_at"]
            ),
        )

        if tenant_id not in self._transactions:
            self._transactions[tenant_id] = []
        self._transactions[tenant_id].append(transaction)

        if tenant_id not in self._redeemed_codes:
            self._redeemed_codes[tenant_id] = set()
        self._redeemed_codes[tenant_id].add(code_upper)

        # Increment global usage counter
        code_def["uses"] += 1

        balance = self.get_balance(tenant_id)

        logger.info(
            "credit_redeemed",
            code=code_upper,
            tenant_id=tenant_id,
            amount_cents=code_def["amount_cents"],
            new_balance_cents=balance.balance_cents,
        )

        return RedeemCreditResponse(
            success=True,
            amount_cents=code_def["amount_cents"],
            credit_type=code_def["type"],
            new_balance_cents=balance.balance_cents,
            message=f"Applied {code_upper}: {code_def['description']}",
        )

    def add_usage_bonus(self, tenant_id: str, documents_processed: int) -> Optional[CreditTransaction]:
        """Award usage bonus credits based on document processing volume.

        $1 credit per 1,000 documents processed.
        """
        bonus_cents = (documents_processed // 1000) * 100  # $1 = 100 cents per 1k docs

        if bonus_cents <= 0:
            return None

        transaction = CreditTransaction(
            tenant_id=tenant_id,
            credit_type=CreditType.USAGE_BONUS,
            amount_cents=bonus_cents,
            description=f"Usage bonus: {documents_processed:,} documents processed",
            expires_at=datetime(datetime.utcnow().year, 12, 31),
        )

        if tenant_id not in self._transactions:
            self._transactions[tenant_id] = []
        self._transactions[tenant_id].append(transaction)

        logger.info(
            "usage_bonus_applied",
            tenant_id=tenant_id,
            documents=documents_processed,
            bonus_cents=bonus_cents,
        )
        return transaction

    def apply_credit_to_invoice(self, tenant_id: str, invoice_amount_cents: int) -> tuple[int, int]:
        """Apply available credits to an invoice.

        Returns (amount_after_credits, credits_used).
        """
        balance = self.get_balance(tenant_id)
        credits_to_apply = min(balance.balance_cents, invoice_amount_cents)

        if credits_to_apply > 0:
            # Record the redemption as a negative transaction
            transaction = CreditTransaction(
                tenant_id=tenant_id,
                credit_type=CreditType.PROMO,  # Generic redemption
                amount_cents=-credits_to_apply,
                description=f"Applied to invoice: -${credits_to_apply / 100:.2f}",
            )
            if tenant_id not in self._transactions:
                self._transactions[tenant_id] = []
            self._transactions[tenant_id].append(transaction)

        amount_after = invoice_amount_cents - credits_to_apply
        return amount_after, credits_to_apply


# Singleton instance
credit_engine = CreditEngine()
