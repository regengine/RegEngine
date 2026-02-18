"""
Billing Service — Dunning & Collections Engine

Automated payment recovery workflows with configurable retry schedules,
escalation tiers, and recovery tracking. In-memory store for sandbox mode.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

from utils import format_cents

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class DunningStage(str, Enum):
    REMINDER = "reminder"           # Day 1 — friendly nudge
    FIRST_NOTICE = "first_notice"   # Day 7 — formal notice
    SECOND_NOTICE = "second_notice" # Day 14 — urgent notice
    FINAL_NOTICE = "final_notice"   # Day 21 — last warning
    SUSPENSION = "suspension"       # Day 30 — service suspended
    COLLECTIONS = "collections"     # Day 45 — external collections


class DunningStatus(str, Enum):
    ACTIVE = "active"
    RECOVERED = "recovered"
    SUSPENDED = "suspended"
    WRITTEN_OFF = "written_off"
    ESCALATED = "escalated"


class RetryResult(str, Enum):
    SUCCEEDED = "succeeded"
    DECLINED = "declined"
    INSUFFICIENT = "insufficient"
    EXPIRED_CARD = "expired_card"
    NETWORK_ERROR = "network_error"


# ── Models ─────────────────────────────────────────────────────────

class RetryAttempt(BaseModel):
    id: str = Field(default_factory=lambda: f"retry_{uuid4().hex[:8]}")
    attempt_number: int
    result: RetryResult
    amount_cents: int
    card_last4: str = ""
    error_message: str = ""
    attempted_at: datetime = Field(default_factory=datetime.utcnow)


class DunningCase(BaseModel):
    id: str = Field(default_factory=lambda: f"dun_{uuid4().hex[:12]}")
    tenant_id: str
    tenant_name: str
    invoice_id: str
    invoice_number: str = ""
    amount_due_cents: int
    # Stage tracking
    stage: DunningStage = DunningStage.REMINDER
    status: DunningStatus = DunningStatus.ACTIVE
    # Retry history
    retry_attempts: list[RetryAttempt] = []
    max_retries: int = 4
    next_retry_at: Optional[datetime] = None
    # Communication log
    emails_sent: int = 0
    last_contacted_at: Optional[datetime] = None
    # Recovery
    amount_recovered_cents: int = 0
    # Dates
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    days_outstanding: int = 0


# ── Escalation Schedule ───────────────────────────────────────────

ESCALATION_SCHEDULE = [
    {"stage": DunningStage.REMINDER, "day": 1, "action": "Friendly payment reminder email", "retry": True},
    {"stage": DunningStage.FIRST_NOTICE, "day": 7, "action": "Formal overdue notice", "retry": True},
    {"stage": DunningStage.SECOND_NOTICE, "day": 14, "action": "Urgent payment required", "retry": True},
    {"stage": DunningStage.FINAL_NOTICE, "day": 21, "action": "Final warning before suspension", "retry": True},
    {"stage": DunningStage.SUSPENSION, "day": 30, "action": "Service access suspended", "retry": False},
    {"stage": DunningStage.COLLECTIONS, "day": 45, "action": "Escalated to external collections", "retry": False},
]


# ── Dunning Engine ─────────────────────────────────────────────────

class DunningEngine:
    """Automated payment recovery and collections management."""

    def __init__(self):
        self._cases: dict[str, DunningCase] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Create realistic dunning scenarios."""
        now = datetime.utcnow()

        cases = [
            # MedSecure — overdue, escalated to second notice
            DunningCase(
                id="dun_medsecure_01", tenant_id="medsecure", tenant_name="MedSecure Health",
                invoice_id="inv_seed_0008", invoice_number="INV-2026-1009",
                amount_due_cents=1_204_955, stage=DunningStage.SECOND_NOTICE,
                status=DunningStatus.ACTIVE, emails_sent=3,
                last_contacted_at=now - timedelta(days=2),
                next_retry_at=now + timedelta(days=3),
                retry_attempts=[
                    RetryAttempt(attempt_number=1, result=RetryResult.DECLINED, amount_cents=1_204_955,
                                card_last4="8888", error_message="Card declined", attempted_at=now - timedelta(days=14)),
                    RetryAttempt(attempt_number=2, result=RetryResult.INSUFFICIENT, amount_cents=1_204_955,
                                card_last4="8888", error_message="Insufficient funds", attempted_at=now - timedelta(days=7)),
                ],
                opened_at=now - timedelta(days=16), days_outstanding=16,
            ),
            # SafetyFirst — recent reminder
            DunningCase(
                id="dun_safety_01", tenant_id="safetyfirst", tenant_name="SafetyFirst Manufacturing",
                invoice_id="inv_seed_0010", invoice_number="INV-2026-1011",
                amount_due_cents=328_984, stage=DunningStage.REMINDER,
                status=DunningStatus.ACTIVE, emails_sent=1,
                last_contacted_at=now - timedelta(days=1),
                next_retry_at=now + timedelta(days=5),
                retry_attempts=[
                    RetryAttempt(attempt_number=1, result=RetryResult.EXPIRED_CARD, amount_cents=328_984,
                                card_last4="3782", error_message="Card expired", attempted_at=now - timedelta(days=2)),
                ],
                opened_at=now - timedelta(days=3), days_outstanding=3,
            ),
            # Recovered case — FreshLeaf
            DunningCase(
                id="dun_freshleaf_01", tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                invoice_id="inv_seed_rev01", invoice_number="INV-2026-0998",
                amount_due_cents=486_250, stage=DunningStage.FIRST_NOTICE,
                status=DunningStatus.RECOVERED, emails_sent=2,
                amount_recovered_cents=486_250,
                retry_attempts=[
                    RetryAttempt(attempt_number=1, result=RetryResult.NETWORK_ERROR, amount_cents=486_250,
                                card_last4="4242", attempted_at=now - timedelta(days=12)),
                    RetryAttempt(attempt_number=2, result=RetryResult.SUCCEEDED, amount_cents=486_250,
                                card_last4="4242", attempted_at=now - timedelta(days=5)),
                ],
                opened_at=now - timedelta(days=14), resolved_at=now - timedelta(days=5), days_outstanding=9,
            ),
            # Written-off case
            DunningCase(
                id="dun_oldco_01", tenant_id="oldco", tenant_name="OldCo Logistics",
                invoice_id="inv_seed_wo01", invoice_number="INV-2025-0845",
                amount_due_cents=189_000, stage=DunningStage.COLLECTIONS,
                status=DunningStatus.WRITTEN_OFF, emails_sent=6,
                retry_attempts=[
                    RetryAttempt(attempt_number=1, result=RetryResult.DECLINED, amount_cents=189_000,
                                card_last4="1234", attempted_at=now - timedelta(days=55)),
                    RetryAttempt(attempt_number=2, result=RetryResult.DECLINED, amount_cents=189_000,
                                card_last4="1234", attempted_at=now - timedelta(days=48)),
                    RetryAttempt(attempt_number=3, result=RetryResult.DECLINED, amount_cents=189_000,
                                card_last4="1234", attempted_at=now - timedelta(days=35)),
                ],
                opened_at=now - timedelta(days=60), resolved_at=now - timedelta(days=10), days_outstanding=50,
            ),
        ]

        for c in cases:
            self._cases[c.id] = c

    # ── Case Management ───────────────────────────────────────

    def open_case(self, tenant_id: str, tenant_name: str, invoice_id: str,
                  invoice_number: str, amount_due_cents: int) -> DunningCase:
        """Open a new dunning case for a failed payment."""
        case = DunningCase(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            amount_due_cents=amount_due_cents,
            next_retry_at=datetime.utcnow() + timedelta(days=3),
        )
        self._cases[case.id] = case
        logger.info("dunning_case_opened", case_id=case.id, tenant=tenant_name, amount=amount_due_cents)
        return case

    def get_case(self, case_id: str) -> Optional[DunningCase]:
        return self._cases.get(case_id)

    def list_cases(self, status: DunningStatus | None = None,
                   stage: DunningStage | None = None) -> list[DunningCase]:
        cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        if stage:
            cases = [c for c in cases if c.stage == stage]
        return sorted(cases, key=lambda c: c.amount_due_cents, reverse=True)

    # ── Retry Payment ──────────────────────────────────────────

    def retry_payment(self, case_id: str) -> RetryAttempt:
        """Simulate a payment retry."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        if case.status != DunningStatus.ACTIVE:
            raise ValueError(f"Cannot retry a {case.status.value} case")

        attempt_num = len(case.retry_attempts) + 1

        # Simulate: 40% success rate
        import random
        rand = random.random()
        if rand < 0.4:
            result = RetryResult.SUCCEEDED
            error = ""
        elif rand < 0.65:
            result = RetryResult.DECLINED
            error = "Card declined by issuer"
        elif rand < 0.85:
            result = RetryResult.INSUFFICIENT
            error = "Insufficient funds"
        else:
            result = RetryResult.EXPIRED_CARD
            error = "Card has expired"

        attempt = RetryAttempt(
            attempt_number=attempt_num,
            result=result,
            amount_cents=case.amount_due_cents,
            card_last4="4242",
            error_message=error,
        )
        case.retry_attempts.append(attempt)

        if result == RetryResult.SUCCEEDED:
            case.status = DunningStatus.RECOVERED
            case.amount_recovered_cents = case.amount_due_cents
            case.resolved_at = datetime.utcnow()
            logger.info("dunning_recovered", case_id=case_id, amount=case.amount_due_cents)
        else:
            case.next_retry_at = datetime.utcnow() + timedelta(days=7)
            if attempt_num >= case.max_retries:
                self._escalate(case)

        return attempt

    def _escalate(self, case: DunningCase):
        """Advance case to next escalation stage."""
        stages = list(DunningStage)
        current_idx = stages.index(case.stage)
        if current_idx < len(stages) - 1:
            case.stage = stages[current_idx + 1]
            case.emails_sent += 1
            case.last_contacted_at = datetime.utcnow()
            logger.info("dunning_escalated", case_id=case.id, new_stage=case.stage.value)
        if case.stage == DunningStage.SUSPENSION:
            case.status = DunningStatus.SUSPENDED

    def escalate_case(self, case_id: str) -> DunningCase:
        """Manually escalate a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        if case.status != DunningStatus.ACTIVE:
            raise ValueError(f"Cannot escalate a {case.status.value} case")
        self._escalate(case)
        return case

    def write_off(self, case_id: str) -> DunningCase:
        """Write off a case as uncollectible."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        case.status = DunningStatus.WRITTEN_OFF
        case.resolved_at = datetime.utcnow()
        logger.info("dunning_written_off", case_id=case_id, amount=case.amount_due_cents)
        return case

    # ── Dashboard Summary ──────────────────────────────────────

    def get_summary(self) -> dict:
        """Dunning program overview."""
        cases = list(self._cases.values())
        active = [c for c in cases if c.status == DunningStatus.ACTIVE]
        recovered = [c for c in cases if c.status == DunningStatus.RECOVERED]

        total_at_risk = sum(c.amount_due_cents for c in active)
        total_recovered = sum(c.amount_recovered_cents for c in recovered)
        total_written_off = sum(c.amount_due_cents for c in cases if c.status == DunningStatus.WRITTEN_OFF)

        recovery_rate = round(len(recovered) / max(len(cases), 1) * 100, 1)

        stage_breakdown = {}
        for stage in DunningStage:
            stage_cases = [c for c in active if c.stage == stage]
            stage_breakdown[stage.value] = {
                "count": len(stage_cases),
                "amount_cents": sum(c.amount_due_cents for c in stage_cases),
                "amount_display": format_cents(sum(c.amount_due_cents for c in stage_cases)),
            }

        return {
            "total_cases": len(cases),
            "active_cases": len(active),
            "recovered_cases": len(recovered),
            "total_at_risk_cents": total_at_risk,
            "total_at_risk_display": format_cents(total_at_risk),
            "total_recovered_cents": total_recovered,
            "total_recovered_display": format_cents(total_recovered),
            "total_written_off_cents": total_written_off,
            "total_written_off_display": format_cents(total_written_off),
            "recovery_rate_pct": recovery_rate,
            "total_retries": sum(len(c.retry_attempts) for c in cases),
            "stage_breakdown": stage_breakdown,
            "escalation_schedule": [
                {"stage": s["stage"].value, "day": s["day"], "action": s["action"]}
                for s in ESCALATION_SCHEDULE
            ],
        }


# Singleton
dunning_engine = DunningEngine()
