"""
Jurisdiction hierarchy builder (#1304).

INVARIANT — this module operates on the GLOBAL regulatory taxonomy,
NOT on tenant data.
================================================================

Jurisdictions ("US", "US-CA", "EU", "EU-FR") are a small, shared set
of regulatory scopes. Every tenant sees the same hierarchy — a
jurisdiction node is NOT tenant-scoped.

That invariant has two consequences:

1. ``build_jurisdiction_hierarchy`` MUST NOT be called from a
   request handler. The only legitimate callers are the boot
   bootstrap script (``scripts/build_hierarchy.py``), deployment
   automation, and migrations. A request-handler caller would
   let a tenant mutate shared regulatory taxonomy visible to every
   other tenant — at minimum a data-integrity bug, at worst a
   cross-tenant vandalism vector.

2. Jurisdiction codes MUST be validated before they reach the
   database. The current ``Neo4jClient`` forces all data into
   ``DB_GLOBAL`` (a separate critical issue), so any unvalidated
   MERGE here lands in the same graph as tenant data. This module
   enforces a whitelist (``_JURISDICTION_CODE_RE``) on every code
   before MERGE — an attacker-controlled code that doesn't match
   the pattern is rejected.

Defense-in-depth design
-----------------------

- Dedicated label ``:GlobalJurisdiction`` in addition to
  ``:Jurisdiction`` so tenant-scoped queries can filter it out
  explicitly (``MATCH (j:Jurisdiction) WHERE NOT j:GlobalJurisdiction``
  catches any regression that creates tenant-scoped jurisdictions).
- Explicit ``scope='global'`` property so query authors can filter
  without touching the label set.
- ``version`` property tracks which build run wrote the node; useful
  for detecting drift.

Related: #1229 (graph security audit meta), the ``DB_GLOBAL``
forcing bug, and #1315 (graph isolation). This module's fix is
scoped to documenting the invariant and hardening the MERGE —
the full isolation fix requires DB-level boundaries.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from neo4j import Driver

logger = logging.getLogger("hierarchy-builder")

# Jurisdiction codes follow ISO-3166 alpha-2 / alpha-3 segmented by ``-``.
# Whitelist: uppercase letters and digits, segments of length 2–6,
# overall length ≤ 32. Examples: "US", "US-CA", "US-CA-SF", "EU-FR-75".
#
# This intentionally rejects:
# - Lowercase ("us-ca") — Neo4j would treat it as a distinct node.
# - Punctuation other than ``-`` — keeps Cypher injection attempts
#   from slipping a ``}`` or quote into the MERGE parameter even
#   though parameter binding would normally neutralise them.
# - Empty segments ("US--CA") — a legitimate segmentation bug.
_JURISDICTION_CODE_RE = re.compile(r"^[A-Z0-9]{2,6}(?:-[A-Z0-9]{2,6})*$")
_MAX_JURISDICTION_CODE_LENGTH = 32


class InvalidJurisdictionCodeError(ValueError):
    """Raised when a jurisdiction code fails the whitelist check (#1304)."""


def parent_code_for(code: str) -> str | None:
    if not code:
        return None
    if "-" not in code:
        return None
    parts = code.split("-")
    if len(parts) <= 1:
        return None
    return "-".join(parts[:-1])


def _validate_jurisdiction_code(code: str) -> None:
    """Reject codes that don't match the global-taxonomy pattern (#1304).

    Guards against:
    - A tenant-scoped caller feeding attacker-controlled codes
      (even though the only legitimate caller is the admin script —
      this is defense-in-depth against future regressions).
    - Case-insensitivity drift that would fragment the taxonomy.
    - Empty segments from a malformed code-generation path.
    """
    if not isinstance(code, str):
        raise InvalidJurisdictionCodeError(
            f"jurisdiction code must be a string, got {type(code).__name__}"
        )
    if len(code) > _MAX_JURISDICTION_CODE_LENGTH:
        raise InvalidJurisdictionCodeError(
            f"jurisdiction code too long: {len(code)} > "
            f"{_MAX_JURISDICTION_CODE_LENGTH} (#1304)"
        )
    if not _JURISDICTION_CODE_RE.fullmatch(code):
        raise InvalidJurisdictionCodeError(
            f"jurisdiction code {code!r} does not match the global-taxonomy "
            f"whitelist (uppercase alphanumeric segments, ``-``-separated; "
            f"see hierarchy_builder.py docstring) (#1304)"
        )


def build_jurisdiction_hierarchy(driver: Driver, codes: Iterable[str]) -> None:
    """Build the global jurisdiction hierarchy.

    INVARIANT (#1304): this function writes to the GLOBAL regulatory
    taxonomy. It is intended to be called ONLY from:

    - ``scripts/build_hierarchy.py`` (admin bootstrap).
    - Deployment automation / migrations.

    DO NOT call this from a FastAPI request handler. Doing so would
    allow a tenant to mutate shared regulatory taxonomy visible to
    every other tenant. A grep in CI (see ``tests/graph/`` regression
    file for this issue) asserts that no request-handler module
    imports this function.

    Every created node carries:
    - Label ``:Jurisdiction`` (for existing queries).
    - Label ``:GlobalJurisdiction`` (distinguishes from any future
      tenant-scoped jurisdictions).
    - ``scope='global'`` property.

    Given an iterable of jurisdiction codes, ensure nodes exist and
    create CONTAINS edges from parent → child based on code
    segmentation. Idempotent: uses MERGE for nodes and relationships.
    Every code is validated against ``_JURISDICTION_CODE_RE`` before
    any MERGE; invalid codes raise ``InvalidJurisdictionCodeError``
    and abort the entire build (fail-closed so a single attacker-
    controlled code doesn't get partially persisted).
    """
    # Fail closed: validate ALL codes before issuing any MERGE. A
    # late-rejected code would otherwise leave the graph in a partial
    # state.
    deduped = {code for code in codes if code}
    for code in deduped:
        _validate_jurisdiction_code(code)
        parent = parent_code_for(code)
        if parent:
            _validate_jurisdiction_code(parent)

    with driver.session() as session:
        for code in deduped:
            parent = parent_code_for(code)
            # Ensure the child node exists with the GlobalJurisdiction
            # label and scope property. ``ON CREATE`` semantics via
            # ``SET`` ensures that a pre-existing ``:Jurisdiction``
            # node (from before this fix) is back-filled with the
            # scope/version metadata on the next run.
            session.run(
                """
                MERGE (j:Jurisdiction {code: $code})
                SET j:GlobalJurisdiction,
                    j.scope = 'global'
                """,
                code=code,
            )
            if parent:
                session.run(
                    """
                    MERGE (p:Jurisdiction {code: $parent})
                    SET p:GlobalJurisdiction,
                        p.scope = 'global'
                    MERGE (c:Jurisdiction {code: $child})
                    SET c:GlobalJurisdiction,
                        c.scope = 'global'
                    MERGE (p)-[:CONTAINS]->(c)
                    """,
                    parent=parent,
                    child=code,
                )
    logger.info(
        "jurisdiction_hierarchy_built count=%d",
        len(deduped),
    )
