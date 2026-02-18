"""
Billing Service — Credit Program Router

Credit balance, redemption, and transaction history endpoints.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header

from models import RedeemCreditRequest
from credit_engine import CreditEngine, CREDIT_CODES
from dependencies import get_credit_engine
from utils import get_tenant_id, format_cents

router = APIRouter(prefix="/v1/billing/credits", tags=["credits"])


@router.get("/balance")
async def get_credit_balance(
    x_tenant_id: Optional[str] = Header(None),
    engine: CreditEngine = Depends(get_credit_engine),
):
    """Get current credit balance for tenant."""
    tenant_id = get_tenant_id(x_tenant_id)
    balance = engine.get_balance(tenant_id)
    return {
        "balance_cents": balance.balance_cents,
        "balance_display": format_cents(balance.balance_cents),
        "total_earned_cents": balance.total_earned_cents,
        "total_redeemed_cents": balance.total_redeemed_cents,
        "transaction_count": len(balance.transactions),
    }


@router.get("/history")
async def get_credit_history(
    x_tenant_id: Optional[str] = Header(None),
    engine: CreditEngine = Depends(get_credit_engine),
):
    """Get credit transaction history for tenant."""
    tenant_id = get_tenant_id(x_tenant_id)
    balance = engine.get_balance(tenant_id)
    return {
        "transactions": [t.model_dump() for t in balance.transactions],
        "current_balance_cents": balance.balance_cents,
    }


@router.post("/redeem")
async def redeem_credit(
    request: RedeemCreditRequest,
    x_tenant_id: Optional[str] = Header(None),
    engine: CreditEngine = Depends(get_credit_engine),
):
    """Redeem a credit code (referral, promo, partner, early adopter)."""
    tenant_id = get_tenant_id(x_tenant_id)
    result = engine.redeem_code(tenant_id, request.code)
    return result.model_dump()


@router.get("/available-programs")
async def list_available_programs():
    """List currently available credit programs."""
    programs = []
    for code, details in CREDIT_CODES.items():
        programs.append({
            "code": code,
            "type": details["type"].value,
            "description": details["description"],
            "amount_display": f"${details['amount_cents'] / 100:.2f}",
            "expires_at": details["expires_at"].isoformat() if details["expires_at"] else None,
            "available": (
                details["max_uses"] is None
                or details["uses"] < details["max_uses"]
            ),
        })
    return {"programs": programs}
