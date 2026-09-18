"""Test helpers for ingestion auth dependency overrides."""

from __future__ import annotations

import sys

from services.ingestion.app.authz import get_ingestion_principal


def install_ingestion_principal_override(app, principal) -> None:
    """Override the ingestion-principal dependency across loaded aliases."""

    dependencies = {get_ingestion_principal}
    for module_name in ("services.ingestion.app.authz", "services.ingestion.app.authz"):
        module = sys.modules.get(module_name)
        current = getattr(module, "get_ingestion_principal", None)
        if current is not None:
            dependencies.add(current)

    for dependency in dependencies:
        app.dependency_overrides[dependency] = lambda: principal


def install_active_subscription_override(app) -> None:
    """Bypass the subscription gate across loaded ingestion aliases."""

    dependencies = set()
    for module_name in (
        "services.ingestion.app.subscription_gate",
        "services.ingestion.app.subscription_gate",
        "services.ingestion.app.fda_export.router",
        "services.ingestion.app.fda_export.router",
    ):
        module = sys.modules.get(module_name)
        current = getattr(module, "require_active_subscription", None)
        if current is not None:
            dependencies.add(current)

    if not dependencies:
        from services.ingestion.app.subscription_gate import require_active_subscription

        dependencies.add(require_active_subscription)

    for dependency in dependencies:
        app.dependency_overrides[dependency] = lambda: None
