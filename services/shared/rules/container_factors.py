"""
Per-product container-factor resolution for UoM conversion.

Background
----------
``services/shared/rules/uom.py`` historically hard-coded container
factors globally — a "case" was always 24 lbs, a "pallet" 2000 lbs,
a "bin" 800 lbs. That makes mass-balance checks and conversion-to-lbs
nonsensical for every commodity EXCEPT whatever the original numbers
were guessed from:

  - Leafy greens: ~24 lbs/case (close to the hardcoded default)
  - Strawberries: ~8-9 lbs/case (flat of 8 x 1-lb clamshells)
  - Melons: ~35-45 lbs/case (bin of 4-5 melons)
  - Soft cheese: ~5-6 lbs/case

Stamping a mass-balance verdict on a strawberry lot at 24 lbs/case means
"total output" can exceed "total input" by 3x without triggering the
rule, or trigger falsely on a legitimate transform. #1363.

Resolution strategy (first hit wins)
------------------------------------
1. ``product_container_factors`` table — per-tenant, per-(product, uom)
   mapping. Authoritative source when populated.
2. YAML seed fallback — ships with RegEngine and covers the common
   commodities. Intended for bootstrap and tests only; production
   deployments MUST seed the table.
3. Fail-closed — raise ``ContainerFactorUnknownError``. A caller that
   can't find a factor must NOT guess a global default; the mass-balance
   evaluator will mark the rule as ``compliant=None`` with a reason.

Security
--------
The table lookup is scoped by ``tenant_id`` — tenants may legitimately
use different containerization conventions (a broker's "case" is not a
grower's "case"). Resolvers take the tenant as a required kwarg and
never fall back across tenants.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = logging.getLogger("rules-engine.container_factors")


class ContainerFactorUnknownError(Exception):
    """Raised when no factor is known for a (tenant, product, uom) triple.

    Callers must treat this as a hard failure: the mass-balance rule
    cannot be evaluated, so a compliance verdict must not be produced.
    """

    def __init__(
        self,
        product_reference: Optional[str],
        uom: Optional[str],
        tenant_id: Optional[str] = None,
    ):
        self.product_reference = product_reference
        self.uom = uom
        self.tenant_id = tenant_id
        super().__init__(
            f"No container factor configured for product={product_reference!r} "
            f"uom={uom!r} tenant={tenant_id!r}"
        )


@dataclass(frozen=True)
class FactorLookupKey:
    """Normalized lookup key — product name + UoM, both lower-cased."""
    product: str  # normalized product reference
    uom: str      # normalized UoM

    @classmethod
    def from_inputs(cls, product: Optional[str], uom: Optional[str]) -> "FactorLookupKey":
        return cls(
            product=(product or "").strip().lower(),
            uom=(uom or "").strip().lower().rstrip("."),
        )


# ---------------------------------------------------------------------------
# Seed fallback data.
#
# These values are conservative trade-standard approximations sourced from
# the USDA Agricultural Marketing Service's Fruit and Vegetable Market News
# weight tables. They are intentionally NOT expanded with every commodity —
# fallback is a safety net, not a substitute for per-tenant configuration.
# ---------------------------------------------------------------------------

_SEED_FACTORS_LBS: Dict[FactorLookupKey, float] = {
    # Leafy greens
    FactorLookupKey("romaine lettuce", "case"): 24.0,
    FactorLookupKey("romaine lettuce", "carton"): 24.0,
    FactorLookupKey("romaine lettuce", "cases"): 24.0,
    FactorLookupKey("iceberg lettuce", "case"): 40.0,
    FactorLookupKey("iceberg lettuce", "carton"): 40.0,
    FactorLookupKey("spinach", "case"): 10.0,
    # Berries
    FactorLookupKey("strawberries", "case"): 8.0,
    FactorLookupKey("strawberries", "flat"): 8.0,
    FactorLookupKey("blueberries", "case"): 9.0,
    FactorLookupKey("blueberries", "flat"): 9.0,
    # Melons
    FactorLookupKey("cantaloupe", "case"): 40.0,
    FactorLookupKey("cantaloupe", "carton"): 40.0,
    FactorLookupKey("watermelon", "bin"): 900.0,
    # Soft cheese
    FactorLookupKey("brie", "case"): 6.0,
    FactorLookupKey("camembert", "case"): 6.0,
}


class ContainerFactorResolver:
    """Resolve container-factor conversions with tenant-scoped DB lookup.

    Usage::

        resolver = ContainerFactorResolver(session)
        lbs = resolver.to_lbs(
            quantity=10,
            uom="case",
            product_reference="Strawberries",
            tenant_id=tenant_id,
        )

    Raises ``ContainerFactorUnknownError`` if no factor is known — the
    caller MUST fail-closed rather than guess.

    An instance memoizes lookups for the lifetime of a single evaluation
    run. Callers should create a new resolver per request (cheap).
    """

    _SQL = text("""
        SELECT factor_to_lbs
        FROM fsma.product_container_factors
        WHERE tenant_id = :tenant_id
          AND product_reference = :product_ref
          AND uom = :uom
        LIMIT 1
    """)

    def __init__(self, session: Optional[Session]):
        self._session = session
        self._cache: Dict[Tuple[str, str, str], float] = {}
        self._unknown_cache: set[Tuple[str, str, str]] = set()
        self._lock = threading.Lock()
        self._table_missing = False  # set after first ProgrammingError

    def _db_lookup(self, key: FactorLookupKey, tenant_id: str) -> Optional[float]:
        """Return the DB-sourced factor or None if absent / unavailable."""
        if self._session is None or self._table_missing:
            return None
        try:
            row = self._session.execute(
                self._SQL,
                {
                    "tenant_id": tenant_id,
                    "product_ref": key.product,
                    "uom": key.uom,
                },
            ).fetchone()
        except SQLAlchemyError as exc:
            # Most likely the table hasn't been migrated in this tenant
            # cluster yet. Remember so we don't spam the logs, and fall
            # through to seed fallback.
            logger.warning(
                "container_factors_table_unavailable",
                extra={"error": str(exc), "tenant_id": tenant_id},
            )
            self._table_missing = True
            return None
        if not row:
            return None
        factor = row[0]
        if factor is None:
            return None
        return float(factor)

    def resolve_factor(
        self,
        uom: Optional[str],
        product_reference: Optional[str],
        tenant_id: Optional[str],
    ) -> float:
        """Return the lbs-per-unit factor for (product, uom, tenant).

        Raises ContainerFactorUnknownError when no factor is known.
        """
        key = FactorLookupKey.from_inputs(product_reference, uom)
        cache_key = (tenant_id or "", key.product, key.uom)

        with self._lock:
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit
            if cache_key in self._unknown_cache:
                raise ContainerFactorUnknownError(product_reference, uom, tenant_id)

        # First check: DB table (tenant-scoped).
        if tenant_id and key.product and key.uom:
            factor = self._db_lookup(key, tenant_id)
            if factor is not None:
                with self._lock:
                    self._cache[cache_key] = factor
                return factor

        # Second check: seed fallback (no tenant dimension).
        if key.product and key.uom:
            seed = _SEED_FACTORS_LBS.get(key)
            if seed is not None:
                with self._lock:
                    self._cache[cache_key] = seed
                return seed

        with self._lock:
            self._unknown_cache.add(cache_key)
        raise ContainerFactorUnknownError(product_reference, uom, tenant_id)

    def to_lbs(
        self,
        quantity: float,
        uom: Optional[str],
        product_reference: Optional[str],
        tenant_id: Optional[str],
    ) -> float:
        """Convert ``quantity`` in ``uom`` to lbs for the given product.

        Raises ContainerFactorUnknownError when no factor is known.
        """
        factor = self.resolve_factor(uom, product_reference, tenant_id)
        return float(quantity) * factor


def resolve_factor_seed(
    uom: Optional[str],
    product_reference: Optional[str],
) -> Optional[float]:
    """Pure-Python seed lookup for tests and offline tooling.

    Returns the seed factor, or None if the triple isn't in the built-in
    table. Does not consult the database — use ContainerFactorResolver
    for the full chain.
    """
    key = FactorLookupKey.from_inputs(product_reference, uom)
    return _SEED_FACTORS_LBS.get(key)


__all__ = [
    "ContainerFactorResolver",
    "ContainerFactorUnknownError",
    "FactorLookupKey",
    "resolve_factor_seed",
]
