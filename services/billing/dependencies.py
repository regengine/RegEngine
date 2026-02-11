"""
Billing Service — Dependency Injection

FastAPI Depends() providers for all engine singletons.
Use app.dependency_overrides to swap engines in tests.

Usage in routers:
    from dependencies import get_invoice_engine
    @router.get("/")
    async def list_invoices(engine: InvoiceEngine = Depends(get_invoice_engine)):
        ...

Usage in tests:
    from dependencies import get_invoice_engine
    app.dependency_overrides[get_invoice_engine] = lambda: mock_engine
"""

from __future__ import annotations


def get_invoice_engine():
    from invoice_engine import invoice_engine
    return invoice_engine


def get_credit_engine():
    from credit_engine import credit_engine
    return credit_engine


def get_analytics_engine():
    from analytics_engine import analytics_engine
    return analytics_engine


def get_contract_engine():
    from contract_engine import contract_engine
    return contract_engine


def get_partner_engine():
    from partner_engine import partner_engine
    return partner_engine


def get_dunning_engine():
    from dunning_engine import dunning_engine
    return dunning_engine


def get_tax_engine():
    from tax_engine import tax_engine
    return tax_engine


def get_lifecycle_engine():
    from lifecycle_engine import lifecycle_engine
    return lifecycle_engine


def get_alerts_engine():
    from alerts_engine import alerts_engine
    return alerts_engine


def get_forecasting_engine():
    from forecasting_engine import forecasting_engine
    return forecasting_engine


def get_optimization_engine():
    from optimization_engine import optimization_engine
    return optimization_engine


def get_usage_meter():
    from usage_meter import usage_meter
    return usage_meter
