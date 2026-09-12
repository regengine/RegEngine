"""Router exposure policy for the consolidated RegEngine API.

Production uses an exact allowlist so deployment drift cannot silently expose
an optional router.  Development and tests retain the historical broad
surface, including the ``DISABLED_ROUTERS`` escape hatch used by focused local
workflows.

This module deliberately owns policy and metadata only.  ``server.main`` owns
the FastAPI wiring, while the route-security manifest owns operation-level
classification and test adapters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

VALID_ROUTER_NAMES = frozenset(
    {
        "scraping",
        "discovery",
        "sources",
        "sandbox",
        "inflow_workbench",
        "fda_export",
        "csv",
        "sensitech",
        "edi",
        "score",
        "portal",
        "inbound_email",
        "audit",
        "sop",
        "export",
        "epcis_ingestion",
        "qr_decoder",
        "label_vision",
        "exchange",
        "billing",
        "alerts",
        "onboarding",
        "recall",
        "recall_simulations",
        "supplier_mgmt",
        "audit_log",
        "product_catalog",
        "notification_prefs",
        "team_mgmt",
        "settings",
        "integration",
        "canonical_records",
        "rules",
        "exceptions",
        "remediation",
        "request_workflow",
        "identity",
        "auditor",
        "compliance_metrics",
        "readiness",
        "incidents",
        "chain_verification",
        "audit_export_log",
        "sla_tracking",
        "export_monitoring",
        "supplier_validation",
        "disaster_recovery",
        "admin",
        "graph",
        "nlp",
        "fsma_compliance",
        "proof_verify",
        "proof_recall",
        "email_ingest",
    }
)

# Release-approved production surface.  Any addition or removal is a security
# decision and must update the route-complete tenant/auth gate before deploy.
PRODUCTION_ENABLED_ROUTERS = frozenset(
    {
        "inflow_workbench",
        "fda_export",
        "csv",
        "edi",
        "epcis_ingestion",
        "score",
        "portal",
        "billing",
        "onboarding",
        "recall",
        "proof_verify",
        "proof_recall",
        "canonical_records",
        "rules",
        "exceptions",
        "request_workflow",
        "auditor",
        "compliance_metrics",
        "readiness",
        "chain_verification",
        "audit_export_log",
        "sla_tracking",
        "export_monitoring",
        "admin",
        "fsma_compliance",
    }
)

EXPERIMENTAL_ROUTERS = frozenset(
    {
        "scraping",
        "discovery",
        "sources",
        "sandbox",
        "sensitech",
        "audit",
        "sop",
        "export",
        "qr_decoder",
        "label_vision",
        "exchange",
        "recall_simulations",
        "graph",
        "nlp",
    }
)

COMPLIANCE_ROUTERS = frozenset(
    {
        "canonical_records",
        "rules",
        "exceptions",
        "remediation",
        "fda_export",
        "chain_verification",
    }
)


def _csv_names(raw: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class RouterPolicy:
    """Resolved router policy plus the routers actually mounted by FastAPI."""

    production: bool
    enabled_routers: frozenset[str]
    configured_disabled: frozenset[str]
    unknown_disabled: frozenset[str]
    experimental_bypass_enabled: bool
    mounted_routers: list[str] = field(default_factory=list)

    @classmethod
    def from_environment(
        cls,
        *,
        production: bool,
        environ: Mapping[str, str] | None = None,
    ) -> "RouterPolicy":
        env = os.environ if environ is None else environ
        configured_disabled = _csv_names(env.get("DISABLED_ROUTERS", ""))
        experimental_bypass = _truthy(env.get("ENABLE_EXPERIMENTAL_ROUTERS"))

        if production:
            if configured_disabled:
                raise RuntimeError(
                    "Production router policy rejects DISABLED_ROUTERS; configure the exact "
                    "release-approved ENABLED_ROUTERS allowlist instead."
                )
            if experimental_bypass:
                raise RuntimeError(
                    "Production router policy rejects ENABLE_EXPERIMENTAL_ROUTERS; optional "
                    "routers require release-gate promotion into ENABLED_ROUTERS."
                )

            raw_enabled = env.get("ENABLED_ROUTERS", "")
            if not raw_enabled.strip():
                raise RuntimeError("ENABLED_ROUTERS is required in production and must match the approved set exactly.")

            enabled = _csv_names(raw_enabled)
            unknown = enabled - VALID_ROUTER_NAMES
            missing = PRODUCTION_ENABLED_ROUTERS - enabled
            extra = enabled - PRODUCTION_ENABLED_ROUTERS
            if unknown or missing or extra:
                details: list[str] = []
                if missing:
                    details.append(f"missing={sorted(missing)}")
                if extra:
                    details.append(f"extra={sorted(extra)}")
                if unknown:
                    details.append(f"unknown={sorted(unknown)}")
                raise RuntimeError(
                    "Production ENABLED_ROUTERS does not match the release-approved set exactly: "
                    + "; ".join(details)
                )

            return cls(
                production=True,
                enabled_routers=enabled,
                configured_disabled=frozenset(),
                unknown_disabled=frozenset(),
                experimental_bypass_enabled=False,
            )

        unknown_disabled = configured_disabled - VALID_ROUTER_NAMES
        disabled_compliance = configured_disabled & COMPLIANCE_ROUTERS
        if disabled_compliance and not _truthy(env.get("ALLOW_DISABLE_COMPLIANCE_ROUTERS")):
            raise RuntimeError(
                "CRITICAL: Compliance-critical routers disabled without "
                f"ALLOW_DISABLE_COMPLIANCE_ROUTERS=true: {sorted(disabled_compliance)}. "
                "This violates FSMA 204 requirements."
            )

        return cls(
            production=False,
            enabled_routers=VALID_ROUTER_NAMES - configured_disabled,
            configured_disabled=configured_disabled,
            unknown_disabled=unknown_disabled,
            experimental_bypass_enabled=experimental_bypass,
        )

    @property
    def disabled_routers(self) -> frozenset[str]:
        return VALID_ROUTER_NAMES - self.enabled_routers

    @property
    def auto_disabled_routers(self) -> frozenset[str]:
        if self.production:
            return self.disabled_routers
        return frozenset()

    def enable(self, name: str) -> bool:
        """Return whether a router is enabled and record an actual mount."""
        router_name = name.lower()
        enabled = router_name in self.enabled_routers
        if enabled and router_name not in self.mounted_routers:
            self.mounted_routers.append(router_name)
        return enabled

    def is_enabled(self, name: str) -> bool:
        """Pure predicate used by readiness checks after app construction."""
        return name.lower() in self.enabled_routers
