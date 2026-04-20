"""Neo4j sync helpers for supplier invite/signup onboarding events.

This module keeps invite/signup writes in Postgres as source-of-truth while
mirroring onboarding lineage into Neo4j for traversal and demo flows.

Driver lifecycle (#1410)
------------------------
The Neo4j driver is created lazily via :meth:`SupplierGraphSync._get_driver`
rather than pinned at import time. On every call we pull the current
credentials from ``shared.secrets_manager.get_secrets_manager()`` and compare
them to the cached driver's config; if any of (uri, user, password) differ we
close and rebuild the driver. This means a rotated ``NEO4J_PASSWORD`` is
picked up on the next write — no process restart needed.

Failure handling (#1410)
------------------------
Driver calls go through the shared :data:`shared.circuit_breaker.neo4j_circuit`
breaker. Exceptions are recorded with the breaker before being swallowed by
the best-effort broad-catch in ``_run`` / ``_query_required_ctes`` — so a down
Neo4j trips the circuit and subsequent calls short-circuit to the read/write
no-op path instead of hammering connection-refused.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from shared.circuit_breaker import CircuitOpenError, neo4j_circuit
from shared.secrets_manager import get_secrets_manager

try:
    from neo4j import GraphDatabase
except (ImportError, AttributeError):  # pragma: no cover - defensive import guard
    GraphDatabase = None


logger = structlog.get_logger("supplier_graph_sync")


INVITE_CREATED_QUERY = """
MERGE (buyer:BuyerTenant {tenant_id: $tenant_id})
ON CREATE SET buyer.created_at = datetime()
MERGE (invite:PendingSupplierInvite {invite_id: $invite_id, tenant_id: $tenant_id})
ON CREATE SET invite.tenant_id = $tenant_id
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
MERGE (supplier:SupplierContact {user_id: $user_id, tenant_id: $tenant_id})
ON CREATE SET supplier.tenant_id = $tenant_id
SET supplier.email = $email,
    supplier.role_id = $role_id,
    supplier.updated_at = datetime()
MERGE (buyer)-[:HAS_SUPPLIER_CONTACT]->(supplier)
WITH supplier
OPTIONAL MATCH (invite:PendingSupplierInvite {invite_id: $invite_id, tenant_id: $tenant_id})
FOREACH (_ IN CASE WHEN invite IS NULL THEN [] ELSE [1] END |
  SET invite.status = 'accepted',
      invite.accepted_at = datetime($accepted_at),
      invite.accepted_by = $user_id,
      invite.updated_at = datetime()
  MERGE (invite)-[:CONVERTED_TO]->(supplier)
)
"""


FACILITY_FTL_SCOPING_QUERY = """
MERGE (supplier:SupplierContact {user_id: $supplier_user_id, tenant_id: $tenant_id})
ON CREATE SET supplier.tenant_id = $tenant_id
SET supplier.email = $supplier_email,
    supplier.updated_at = datetime()
MERGE (facility:SupplierFacility {facility_id: $facility_id, tenant_id: $tenant_id})
ON CREATE SET facility.tenant_id = $tenant_id
SET facility.name = $facility_name,
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
  ON CREATE SET ftl.name = category.name,
                ftl.required_ctes = category.ctes,
                ftl.created_at = datetime()
MERGE (facility)-[:HANDLES]->(ftl)
"""


FACILITY_REQUIRED_CTES_QUERY = """
MATCH (facility:SupplierFacility {facility_id: $facility_id, tenant_id: $tenant_id})-[:HANDLES]->(ftl:FTLCategory)
RETURN collect(DISTINCT {
  id: ftl.category_id,
  name: ftl.name,
  ctes: coalesce(ftl.required_ctes, [])
}) AS categories
"""


CTE_EVENT_QUERY = """
MERGE (facility:SupplierFacility {facility_id: $facility_id, tenant_id: $tenant_id})
ON CREATE SET facility.tenant_id = $tenant_id
SET facility.name = $facility_name,
    facility.updated_at = datetime()
MERGE (lot:TLC {tlc_code: $tlc_code, tenant_id: $tenant_id})
SET lot.product_description = coalesce($product_description, lot.product_description),
    lot.status = coalesce($lot_status, lot.status),
    lot.updated_at = datetime()
MERGE (lot)-[:PRODUCED_AT]->(facility)
CREATE (cte:CTEEvent {
  cte_event_id: $cte_event_id,
  tenant_id: $tenant_id,
  cte_type: $cte_type,
  event_time: datetime($event_time),
  payload_sha256: $payload_sha256,
  merkle_hash: $merkle_hash,
  merkle_prev_hash: $merkle_prev_hash,
  sequence_number: $sequence_number,
  kde_data: $kde_data,
  created_at: datetime()
})
MERGE (cte)-[:FOR_LOT]->(lot)
MERGE (cte)-[:OCCURRED_AT]->(facility)
WITH cte
UNWIND $obligation_ids AS obligation_id
// Obligation is a SHARED regulatory catalog (obligation_ids like
// '21cfr_subpart_s_123' are global, not tenant-specific), so MERGEing on
// obligation_id alone is intentional. The SATISFIES edges that land on this
// node DO cross tenant boundaries (tenant A's CTEs and tenant B's CTEs can
// both point to the same Obligation node). Defense-in-depth: every read that
// traverses SATISFIES MUST filter by ``cte.tenant_id`` — the CREATE above
// stamps tenant_id onto every CTEEvent so this predicate is always available.
// See issue #1395.
MERGE (obligation:Obligation {obligation_id: obligation_id})
MERGE (cte)-[:SATISFIES]->(obligation)
"""


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


class SupplierGraphSync:
    """Best-effort Neo4j mirror for supplier onboarding primitives.

    The instance holds a cached ``(driver, creds)`` pair. Every call that
    needs the driver routes through :meth:`_get_driver`, which re-fetches the
    latest Neo4j credentials and rebuilds the driver if any field changed —
    this is how a rotated password propagates without a process restart.

    Tests can bypass the credentials lookup entirely by passing ``driver=``
    to the constructor (a pinned driver never triggers a rebuild).
    """

    def __init__(
        self,
        *,
        enabled: bool,
        driver: Optional[Any] = None,
    ):
        self.enabled = enabled
        # ``_pinned`` is True when a driver was injected by a caller (tests,
        # callers that have already built a driver). Pinned drivers are
        # returned verbatim by :meth:`_get_driver` and never rebuilt.
        self._pinned = driver is not None
        self._driver = driver
        # Cached credential tuple (uri, user, password) the current driver
        # was built with. ``None`` means no driver has been built yet.
        self._current_creds: Optional[tuple[str, str, str]] = None

    @classmethod
    def from_env(cls) -> "SupplierGraphSync":
        """Construct a sync instance wired to :mod:`shared.secrets_manager`.

        Returns a disabled sync if credentials are missing or the ``neo4j``
        driver package is unavailable. Enabled syncs build their driver
        lazily on first use so a transient Neo4j outage at admin-service
        boot no longer pins the service into a permanently-disabled state.

        Reads raw env directly (not via ``secrets_manager``) for the
        enabled/disabled decision because ``get_neo4j_credentials`` defaults
        an unset ``NEO4J_URI`` to ``bolt://localhost:7687`` which would
        falsely enable the sync in environments that genuinely have no
        Neo4j. The ``NEO4J_URL`` legacy alias is honored for parity with
        admin's historical env contract.
        """
        if GraphDatabase is None:
            return cls(enabled=False)

        uri = (os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL") or "").strip()
        password = (os.getenv("NEO4J_PASSWORD") or "").strip()

        if not uri or not password:
            return cls(enabled=False)

        # Enabled — but driver is NOT built here. The first real call routes
        # through :meth:`_get_driver` which builds it on demand using the
        # credentials in effect at that moment.
        return cls(enabled=True, driver=None)

    def _get_driver(self) -> Optional[Any]:
        """Return a driver built against the currently-configured credentials.

        Re-reads ``get_secrets_manager().get_neo4j_credentials()`` on every
        call. If the credentials differ from the cached driver's config, the
        old driver is closed and a new one is built. A pinned driver (one
        supplied via the constructor) is returned verbatim.

        Returns ``None`` when:
        * the ``neo4j`` package is not installed, or
        * credentials are missing (uri/password empty), or
        * driver construction raises.
        """
        if not self.enabled:
            return None

        if self._pinned:
            return self._driver

        if GraphDatabase is None:
            return None

        creds = get_secrets_manager().get_neo4j_credentials()
        uri = (creds.get("uri") or "").strip()
        user = creds.get("username") or "neo4j"
        password = (creds.get("password") or "").strip()

        if not uri or not password:
            # Credentials disappeared (e.g. env var unset mid-flight). Drop
            # the stale driver if any and return None so the call no-ops.
            self._close_driver()
            return None

        creds_tuple = (uri, user, password)
        if self._driver is not None and self._current_creds == creds_tuple:
            return self._driver

        # Credentials changed (or first use). Rebuild.
        self._close_driver()
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception as exc:  # pragma: no cover - driver init failure
            logger.warning(
                "supplier_graph_sync_driver_rebuild_failed",
                error=str(exc),
            )
            return None

        if self._current_creds is not None:
            logger.info(
                "supplier_graph_sync_driver_rotated",
                reason="neo4j_credentials_changed",
            )
        self._driver = driver
        self._current_creds = creds_tuple
        return self._driver

    def _close_driver(self) -> None:
        """Close the cached driver if present; swallow close errors."""
        if self._driver is None or self._pinned:
            return
        try:
            self._driver.close()
        except Exception:  # pragma: no cover - best-effort close
            pass
        self._driver = None
        self._current_creds = None

    def _run(self, query: str, params: dict[str, Any]) -> None:
        if not self.enabled:
            return

        driver = self._get_driver()
        if driver is None:
            return

        operation = params.get("operation", "unknown")
        try:
            # Participate in the shared neo4j_circuit so a down Neo4j trips
            # the breaker after ``failure_threshold`` failures and subsequent
            # calls short-circuit at ``_check_state`` below.
            neo4j_circuit._check_state()
            with driver.session() as session:
                session.run(query, params)
            neo4j_circuit._record_success()
        except CircuitOpenError:
            # Breaker is open — drop the write silently. This is the point of
            # the breaker: stop hammering a known-bad Neo4j. The drop is
            # expected and matches the pre-existing best-effort contract.
            logger.warning(
                "supplier_graph_sync_circuit_open",
                operation=operation,
            )
        except Exception as exc:
            # Record raw failure on the breaker BEFORE swallowing so repeated
            # failures can trip the circuit.
            neo4j_circuit._record_failure(exc)
            logger.warning(
                "supplier_graph_sync_write_failed",
                error=str(exc),
                operation=operation,
            )

    def _query_required_ctes(
        self, facility_id: str, tenant_id: str
    ) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None

        driver = self._get_driver()
        if driver is None:
            return None

        try:
            neo4j_circuit._check_state()
            with driver.session() as session:
                record = session.run(
                    FACILITY_REQUIRED_CTES_QUERY,
                    {"facility_id": facility_id, "tenant_id": tenant_id},
                ).single()
            neo4j_circuit._record_success()
        except CircuitOpenError:
            logger.warning(
                "supplier_graph_sync_circuit_open",
                operation="facility_required_ctes",
            )
            return None
        except Exception as exc:
            neo4j_circuit._record_failure(exc)
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

    def current_driver(self) -> Optional[Any]:
        """Public accessor for the hot-reloaded driver.

        Use this from callers that need to hold the driver handle directly
        (e.g. the outbox drainer wiring a tenant-scoped session factory).
        Returns ``None`` when the sync is disabled or credentials are not
        usable — callers must handle that case.
        """
        return self._get_driver()

    def get_required_ctes_for_facility(
        self, facility_id: str, tenant_id: str
    ) -> Optional[dict[str, Any]]:
        """Read-side tenant-scoped lookup of a facility's FTL/CTE mapping.

        ``tenant_id`` MUST be passed — omitting it would make the Neo4j read
        trust facility_id alone, which would leak another tenant's categories
        if the MERGE-key invariant (#1352) were ever violated. The predicate
        here is defense-in-depth behind the Postgres tenant check.
        """
        return self._query_required_ctes(facility_id, tenant_id)

    def purge_tenant(self, tenant_id: str) -> int:
        """GDPR Art. 17 erasure: delete all Neo4j nodes for *tenant_id*.

        Runs ``DETACH DELETE`` on every node whose ``tenant_id`` property
        matches the supplied value. Returns the number of nodes deleted.
        Returns 0 (and does not raise) when disabled, when the circuit is
        open, or when Neo4j is unavailable — callers treat this as
        best-effort and must log failures independently.

        Idempotency: a second call with the same *tenant_id* returns 0
        because no matching nodes remain.

        Note: ``FTLCategory`` and ``Obligation`` nodes are shared
        regulatory catalog entries (no ``tenant_id`` property) and are
        therefore NOT touched by this query — only tenant-owned nodes
        (BuyerTenant, SupplierContact, PendingSupplierInvite,
        SupplierFacility, TLC, CTEEvent) are removed.
        """
        if not self.enabled:
            return 0

        driver = self._get_driver()
        if driver is None:
            return 0

        query = (
            "MATCH (n) WHERE n.tenant_id = $tenant_id "
            "DETACH DELETE n "
            "RETURN count(*) AS deleted"
        )
        try:
            neo4j_circuit._check_state()
            with driver.session() as session:
                record = session.run(query, {"tenant_id": tenant_id}).single()
            neo4j_circuit._record_success()
        except CircuitOpenError:
            logger.warning(
                "supplier_graph_sync_circuit_open",
                operation="purge_tenant",
                tenant_id=tenant_id,
            )
            return 0
        except Exception as exc:
            neo4j_circuit._record_failure(exc)
            logger.warning(
                "neo4j_purge_failed",
                tenant_id=tenant_id,
                error=str(exc),
            )
            return 0

        deleted: int = record["deleted"] if record else 0
        logger.info(
            "supplier_graph_sync_tenant_purged",
            tenant_id=tenant_id,
            deleted=deleted,
        )
        return deleted

    def record_cte_event(
        self,
        *,
        tenant_id: str,
        facility_id: str,
        facility_name: str,
        cte_event_id: str,
        cte_type: str,
        event_time: str,
        tlc_code: str,
        product_description: Optional[str],
        lot_status: Optional[str],
        kde_data: dict[str, Any],
        payload_sha256: str,
        merkle_prev_hash: Optional[str],
        merkle_hash: str,
        sequence_number: int,
        obligation_ids: list[str],
    ) -> None:
        self._run(
            CTE_EVENT_QUERY,
            {
                "operation": "cte_event_recorded",
                "tenant_id": tenant_id,
                "facility_id": facility_id,
                "facility_name": facility_name,
                "cte_event_id": cte_event_id,
                "cte_type": cte_type,
                "event_time": event_time,
                "tlc_code": tlc_code,
                "product_description": product_description,
                "lot_status": lot_status,
                "kde_data": kde_data,
                "payload_sha256": payload_sha256,
                "merkle_prev_hash": merkle_prev_hash,
                "merkle_hash": merkle_hash,
                "sequence_number": sequence_number,
                "obligation_ids": obligation_ids,
            },
        )


supplier_graph_sync = SupplierGraphSync.from_env()
