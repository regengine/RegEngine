"""Neo4j sync helpers for supplier invite/signup onboarding events.

This module keeps invite/signup writes in Postgres as source-of-truth while
mirroring onboarding lineage into Neo4j for traversal and demo flows.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - defensive import guard
    GraphDatabase = None


logger = structlog.get_logger("supplier_graph_sync")


INVITE_CREATED_QUERY = """
MERGE (buyer:BuyerTenant {tenant_id: $tenant_id})
ON CREATE SET buyer.created_at = datetime()
MERGE (invite:PendingSupplierInvite {invite_id: $invite_id})
SET invite.email = $email,
    invite.role_id = $role_id,
    invite.status = 'pending',
    invite.expires_at = datetime($expires_at),
    invite.created_by = $created_by,
    invite.updated_at = datetime()
MERGE (buyer)-[:INVITED]->(invite)
"""


INVITE_ACCEPTED_QUERY = """
MERGE (buyer:BuyerTenant {tenant_id: $tenant_id})
ON CREATE SET buyer.created_at = datetime()
MERGE (supplier:SupplierContact {user_id: $user_id})
SET supplier.email = $email,
    supplier.tenant_id = $tenant_id,
    supplier.role_id = $role_id,
    supplier.updated_at = datetime()
MERGE (buyer)-[:HAS_SUPPLIER_CONTACT]->(supplier)
WITH supplier
OPTIONAL MATCH (invite:PendingSupplierInvite {invite_id: $invite_id})
FOREACH (_ IN CASE WHEN invite IS NULL THEN [] ELSE [1] END |
  SET invite.status = 'accepted',
      invite.accepted_at = datetime($accepted_at),
      invite.accepted_by = $user_id,
      invite.updated_at = datetime()
  MERGE (invite)-[:CONVERTED_TO]->(supplier)
)
"""


FACILITY_FTL_SCOPING_QUERY = """
MERGE (supplier:SupplierContact {user_id: $supplier_user_id})
SET supplier.email = $supplier_email,
    supplier.tenant_id = $tenant_id,
    supplier.updated_at = datetime()
MERGE (facility:SupplierFacility {facility_id: $facility_id})
SET facility.tenant_id = $tenant_id,
    facility.name = $facility_name,
    facility.street = $street,
    facility.city = $city,
    facility.state = $state,
    facility.postal_code = $postal_code,
    facility.fda_registration_number = $fda_registration_number,
    facility.roles = $roles,
    facility.updated_at = datetime()
MERGE (supplier)-[:OPERATES]->(facility)
WITH facility
OPTIONAL MATCH (facility)-[old:HANDLES]->(:FTLCategory)
DELETE old
WITH facility
UNWIND $categories AS category
MERGE (ftl:FTLCategory {category_id: category.id})
SET ftl.name = category.name,
    ftl.required_ctes = category.ctes,
    ftl.updated_at = datetime()
MERGE (facility)-[:HANDLES]->(ftl)
"""


FACILITY_REQUIRED_CTES_QUERY = """
MATCH (facility:SupplierFacility {facility_id: $facility_id})-[:HANDLES]->(ftl:FTLCategory)
RETURN collect(DISTINCT {
  id: ftl.category_id,
  name: ftl.name,
  ctes: coalesce(ftl.required_ctes, [])
}) AS categories
"""


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


class SupplierGraphSync:
    """Best-effort Neo4j mirror for supplier onboarding primitives."""

    def __init__(self, *, enabled: bool, driver: Optional[Any] = None):
        self.enabled = enabled
        self._driver = driver

    @classmethod
    def from_env(cls) -> "SupplierGraphSync":
        uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL")
        password = os.getenv("NEO4J_PASSWORD")
        user = os.getenv("NEO4J_USER", "neo4j")

        if not uri or not password or GraphDatabase is None:
            return cls(enabled=False)

        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            return cls(enabled=True, driver=driver)
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.warning(
                "supplier_graph_sync_disabled",
                reason="neo4j_connection_failed",
                error=str(exc),
            )
            return cls(enabled=False)

    def _run(self, query: str, params: dict[str, Any]) -> None:
        if not self.enabled or self._driver is None:
            return

        try:
            with self._driver.session() as session:
                session.run(query, params)
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.warning(
                "supplier_graph_sync_write_failed",
                error=str(exc),
                operation=params.get("operation", "unknown"),
            )

    def _query_required_ctes(self, facility_id: str) -> Optional[dict[str, Any]]:
        if not self.enabled or self._driver is None:
            return None

        try:
            with self._driver.session() as session:
                record = session.run(
                    FACILITY_REQUIRED_CTES_QUERY,
                    {"facility_id": facility_id},
                ).single()
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.warning(
                "supplier_graph_sync_read_failed",
                error=str(exc),
                operation="facility_required_ctes",
            )
            return None

        if not record:
            return {
                "source": "neo4j",
                "categories": [],
                "required_ctes": [],
            }

        categories = record.get("categories") or []
        required_ctes: list[str] = []
        seen: set[str] = set()

        for category in categories:
            for cte in category.get("ctes") or []:
                if cte in seen:
                    continue
                seen.add(cte)
                required_ctes.append(cte)

        return {
            "source": "neo4j",
            "categories": categories,
            "required_ctes": required_ctes,
        }

    def record_invite_created(
        self,
        *,
        tenant_id: str,
        invite_id: str,
        email: str,
        role_id: str,
        expires_at: datetime,
        created_by: str,
    ) -> None:
        self._run(
            INVITE_CREATED_QUERY,
            {
                "operation": "invite_created",
                "tenant_id": tenant_id,
                "invite_id": invite_id,
                "email": email,
                "role_id": role_id,
                "expires_at": _to_utc_iso(expires_at),
                "created_by": created_by,
            },
        )

    def record_invite_accepted(
        self,
        *,
        tenant_id: str,
        invite_id: str,
        user_id: str,
        email: str,
        role_id: str,
        accepted_at: datetime,
    ) -> None:
        self._run(
            INVITE_ACCEPTED_QUERY,
            {
                "operation": "invite_accepted",
                "tenant_id": tenant_id,
                "invite_id": invite_id,
                "user_id": user_id,
                "email": email,
                "role_id": role_id,
                "accepted_at": _to_utc_iso(accepted_at),
            },
        )

    def record_facility_ftl_scoping(
        self,
        *,
        tenant_id: str,
        facility_id: str,
        facility_name: str,
        supplier_user_id: str,
        supplier_email: str,
        street: str,
        city: str,
        state: str,
        postal_code: str,
        fda_registration_number: Optional[str],
        roles: list[str],
        categories: list[dict[str, Any]],
    ) -> None:
        normalized_categories = [
            {
                "id": str(category["id"]),
                "name": category["name"],
                "ctes": category.get("ctes", []),
            }
            for category in categories
        ]

        self._run(
            FACILITY_FTL_SCOPING_QUERY,
            {
                "operation": "facility_ftl_scoping",
                "tenant_id": tenant_id,
                "facility_id": facility_id,
                "facility_name": facility_name,
                "supplier_user_id": supplier_user_id,
                "supplier_email": supplier_email,
                "street": street,
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "fda_registration_number": fda_registration_number,
                "roles": roles,
                "categories": normalized_categories,
            },
        )

    def get_required_ctes_for_facility(self, facility_id: str) -> Optional[dict[str, Any]]:
        return self._query_required_ctes(facility_id)


supplier_graph_sync = SupplierGraphSync.from_env()
