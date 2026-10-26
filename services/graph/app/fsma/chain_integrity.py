"""
FSMA 204 gap analysis and broken chain detection.

Detects missing KDEs, broken chain-of-custody violations,
temporal paradoxes, and cryptographic hash-chain gaps.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence

import structlog
from shared.fsma_rules import TimeArrowRule, TraceEvent as SharedTraceEvent

from ..neo4j_utils import Neo4jClient

logger = structlog.get_logger("fsma-utils")


# Rows fetched per round trip. Results are read page by page with keyset
# pagination on a unique key, so every matching row is reported, nothing is
# silently dropped at a fixed cap, and each round trip stays bounded. Unlike
# SKIP/offset paging, a row deleted (or inserted) between pages cannot shift
# the next page past a row that has not been read yet: each page starts
# strictly after the last key already returned.
_PAGE_SIZE = 2000


def _sort_key(*fields: str) -> Callable[[Any], tuple]:
    """Python sort key for records: ascending, nulls last (Neo4j ASC order)."""

    def key(record: Any) -> tuple:
        return tuple((record[f] is None, "" if record[f] is None else str(record[f])) for f in fields)

    return key


def _after_condition(width: int) -> str:
    """Cypher for ``_page_key > $after_key``, compared element by element."""
    terms = []
    for i in range(width):
        equal = [f"_page_key[{j}] = $after_key[{j}]" for j in range(i)]
        terms.append("(" + " AND ".join(equal + [f"_page_key[{i}] > $after_key[{i}]"]) + ")")
    return " OR ".join(terms)


_PAGE_MARKER = "// @page"


def _hit(record: Any) -> bool:
    """True unless the row carries a ``_hit`` flag that is not true.

    A null flag (Cypher ``null``) is not a hit; queries coalesce it to false.
    """
    try:
        return record["_hit"] is True
    except (KeyError, LookupError):
        return True


async def _run_paged(
    session: Any,
    query: str,
    *,
    anchors: str,
    key: Sequence[str],
    order: Optional[Callable[[Any], Any]] = None,
    **params: Any,
) -> AsyncIterator[Any]:
    """Yield every record of ``query``, fetched ``_PAGE_SIZE`` anchors at a time.

    ``query`` holds a ``// @page`` line right after the MATCH that binds the
    ``anchors`` variables. The keyset filter, ORDER BY and LIMIT are put
    there, so each page reads only its own anchors instead of the whole match.
    ``key`` lists Cypher expressions over the anchors that are unique
    together. The rest of the query must carry ``_page_key`` along and return
    exactly one row per anchor; a row whose ``_hit`` is false is used only to
    advance the cursor and is not yielded. Records are yielded once all pages
    are read, sorted by ``order`` when given.
    """
    if _PAGE_MARKER not in query:
        raise ValueError("paged query needs a // @page marker")
    key_expr = ", ".join(f"coalesce(toString({c}), '')" for c in key)
    page_clause = (
        f"WITH {anchors}, [{key_expr}] AS _page_key\n"
        f"WHERE $after_key IS NULL OR {_after_condition(len(key))}\n"
        f"WITH {anchors}, _page_key\n"
        "ORDER BY _page_key[0]" + "".join(f", _page_key[{i}]" for i in range(1, len(key))) + "\nLIMIT $page_size"
    )
    paged_query = query.replace(_PAGE_MARKER, page_clause, 1)
    records: List[Any] = []
    after_key: Optional[List[str]] = None
    while True:
        result = await session.run(paged_query, after_key=after_key, page_size=_PAGE_SIZE, **params)
        page = [record async for record in result]
        records.extend(r for r in page if _hit(r))
        if len(page) < _PAGE_SIZE:
            break
        after_key = list(page[-1]["_page_key"])
    if order is not None:
        records.sort(key=order)
    for record in records:
        yield record


# Broken-chain rows are (shipping event, lot) pairs: unique together. They
# are reported in event-date order, then event id, then lot.
_CHAIN_ANCHORS = "l, shipping"
_CHAIN_KEY = ("shipping.event_id", "l.tlc")
_CHAIN_ORDER = _sort_key("event_date", "event_id", "lot_tlc")


async def find_gaps(
    client: Neo4jClient,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    """
    Find TraceEvents with missing required KDEs.

    FSMA 204 requires specific KDEs for each CTE type. This query
    identifies events that are missing critical data.

    Returns:
        List of events with gap details

    Raises:
        ValueError: if `tenant_id` is None, empty, or whitespace-only. The
            previous `$tenant_id IS NULL OR ...` shim let null-tenant
            callers read every tenant's events, so callers must pass a tenant.
    """
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("find_gaps requires a non-empty tenant_id; null-tenant queries are no longer supported")

    start_time = time.time()

    # Find events missing key fields.
    # The Lot inside the missing-lot EXISTS check is tenant-scoped: a
    # cross-tenant UNDERWENT edge must not satisfy the existence check and
    # suppress a genuine missing-lot gap.
    query = """
    MATCH (e:TraceEvent)
    WHERE e.tenant_id = $tenant_id
    AND (
        e.event_date IS NULL OR
        e.event_date = '' OR
        NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id } OR
        e.responsible_party_contact IS NULL OR
        e.responsible_party_contact = ''
    )
    // @page
    RETURN
        _page_key,
        e.event_id as event_id,
        e.type as type,
        e.event_date as event_date,
        e.document_id as document_id,
        CASE WHEN e.event_date IS NULL OR e.event_date = '' THEN 'missing_date' ELSE '' END +
        CASE WHEN NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id } THEN ',missing_lot' ELSE '' END +
        CASE WHEN e.responsible_party_contact IS NULL OR e.responsible_party_contact = '' THEN ',missing_responsible_party_contact' ELSE '' END as gaps
    """

    gaps = []
    # Keep the first occurrence of each event so no event is reported twice.
    seen_event_ids: set = set()
    async with client.session() as session:
        async for record in _run_paged(session, query, anchors="e", key=("e.event_id",), tenant_id=tenant_id):
            if record["event_id"] in seen_event_ids:
                continue
            seen_event_ids.add(record["event_id"])
            gaps.append(
                {
                    "event_id": record["event_id"],
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "gaps": [g for g in record["gaps"].split(",") if g],
                    "violation_type": "missing_kde",
                }
            )

    query_time = (time.time() - start_time) * 1000
    logger.info(
        "gap_analysis_completed",
        gap_count=len(gaps),
        query_time_ms=round(query_time, 2),
    )

    return gaps


async def find_broken_chains(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find SHIPPING events that violate chain-of-custody requirements.

    Detects two classes of broken-chain violations:

    1. **Missing Origin** -- A SHIPPING event exists for a Lot that has no
       preceding CREATION, RECEIVING, INITIAL_PACKING, or TRANSFORMATION
       event, meaning the Lot appeared in the supply chain without a
       documented origin.

    2. **Temporal Paradox** -- A SHIPPING event exists for a Lot where the
       earliest origin event (CREATION/RECEIVING/INITIAL_PACKING/TRANSFORMATION) has a date
       *after* the SHIPPING event, violating the Time Arrow constraint.

    FSMA 204 requires full chain of custody -- products cannot be shipped
    without documented receipt or creation, and the origin must precede
    the shipment in time.

    Returns:
        List of violation dicts, each containing event details and
        violation_type ``"broken_chain"``.

    Raises:
        ValueError: if `tenant_id` is None or empty. Previously the queries
            short-circuited with `$tenant_id IS NULL OR ...` which allowed
            null-tenant callers to see every tenant's chain data — the
            exact cross-tenant exposure this function is supposed to
            prevent. #1301 removes that shim; callers must pass a tenant.
    """
    # #1301 — fail-fast on null-tenant calls. The previous
    # `$tenant_id IS NULL OR l.tenant_id = $tenant_id` idiom was a
    # test-time shim that turned into a production info-disclosure the
    # moment a caller forgot to pass tenant_id. Prefer a loud error.
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError(
            "find_broken_chains requires a non-empty tenant_id; null-tenant queries are no longer supported (#1301)"
        )

    start_time = time.time()

    # ------------------------------------------------------------------ #
    # Query 1: SHIPPING with no origin event at all
    # Optimization: single-hop UNDERWENT only (no variable-length path),
    # Results are keyset-paged (_run_paged) instead of capped, so large tenants
    # get every violation.
    # ------------------------------------------------------------------ #
    # #1301: Every event node joined via UNDERWENT must be tenant-scoped,
    # not just the Lot. A cross-tenant UNDERWENT edge (possible because of
    # the MERGE bug tracked in #1284) otherwise surfaces tenant B's shipping
    # events inside tenant A's chain-integrity report. The `origin` node
    # inside the NOT EXISTS sub-query must also carry the predicate — a
    # cross-tenant CREATION/RECEIVING would falsely satisfy the existence
    # check and suppress a genuine broken-chain violation.
    missing_origin_query = """
    MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
    WHERE l.tenant_id = $tenant_id
      AND shipping.tenant_id = $tenant_id
    AND NOT EXISTS {
        MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
        WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING', 'TRANSFORMATION']
          AND origin.tenant_id = $tenant_id
    }
    // @page
    RETURN
        _page_key,
        shipping.event_id    AS event_id,
        shipping.type         AS type,
        shipping.event_date   AS event_date,
        shipping.document_id  AS document_id,
        l.tlc                 AS lot_tlc,
        l.product_description AS product_description
    """

    # ------------------------------------------------------------------ #
    # Query 2: SHIPPING that precedes its own origin (Time Arrow violation)
    # ------------------------------------------------------------------ #
    # #1301: Both shipping and origin event nodes must be tenant-scoped.
    # Missing `origin.tenant_id = $tenant_id` is the riskier gap because a
    # cross-tenant origin event with a later date than tenant A's shipping
    # would create a spurious "temporal paradox" violation — a false
    # positive that wastes compliance-reviewer time and looks like tenant
    # A has broken data.
    temporal_paradox_query = """
    MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
    WHERE l.tenant_id = $tenant_id
      AND shipping.tenant_id = $tenant_id
      AND shipping.event_date IS NOT NULL
    // @page
    // OPTIONAL so every paged (lot, shipping) anchor yields one row.
    OPTIONAL MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
    WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING', 'TRANSFORMATION']
      AND origin.tenant_id = $tenant_id
      AND origin.event_date IS NOT NULL
    // Sort origins per lot before aggregating: collect() preserves the
    // encounter order, so head(collect(...)) is the id of the earliest
    // origin matching min(origin.event_date). Without this the reported
    // origin_event_id can point at a different origin than origin_date.
    WITH l, shipping, _page_key, origin ORDER BY origin.event_date ASC
    WITH l, shipping, _page_key,
         min(origin.event_date) AS earliest_origin_date,
         head(collect(origin.event_id)) AS earliest_origin_id
    RETURN
        _page_key,
        coalesce(earliest_origin_date > shipping.event_date, false) AS _hit,
        shipping.event_id            AS event_id,
        shipping.type                AS type,
        shipping.event_date          AS event_date,
        shipping.document_id         AS document_id,
        l.tlc                        AS lot_tlc,
        l.product_description        AS product_description,
        earliest_origin_id           AS origin_event_id,
        earliest_origin_date         AS origin_date
    """

    violations: List[Dict[str, Any]] = []
    seen_event_ids: set = set()

    async with client.session() as session:
        # --- Missing origin violations --------------------------------
        async for record in _run_paged(
            session,
            missing_origin_query,
            anchors=_CHAIN_ANCHORS,
            key=_CHAIN_KEY,
            order=_CHAIN_ORDER,
            tenant_id=tenant_id,
        ):
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)
            violations.append(
                {
                    "event_id": eid,
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "lot_tlc": record["lot_tlc"],
                    "product_description": record["product_description"],
                    "violation_type": "broken_chain",
                    "violation_reason": ("SHIPPING without CREATION, RECEIVING, INITIAL_PACKING, or TRANSFORMATION"),
                    "gaps": ["missing_origin_event"],
                }
            )

        # --- Temporal paradox violations ------------------------------
        async for record in _run_paged(
            session,
            temporal_paradox_query,
            anchors=_CHAIN_ANCHORS,
            key=_CHAIN_KEY,
            order=_CHAIN_ORDER,
            tenant_id=tenant_id,
        ):
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)

            # Validate via TimeArrowRule for authoritative UTC check
            try:
                origin_evt = SharedTraceEvent(
                    event_id=record["origin_event_id"],
                    tlc=record["lot_tlc"] or "N/A",
                    event_date=str(record["origin_date"]),
                    event_type="ORIGIN",
                )
                shipping_evt = SharedTraceEvent(
                    event_id=eid,
                    tlc=record["lot_tlc"] or "N/A",
                    event_date=str(record["event_date"]),
                    event_type="SHIPPING",
                )
                rule = TimeArrowRule()
                rule_result = rule.validate([origin_evt, shipping_evt])
                if not rule_result.passed:
                    desc = rule_result.violations[0].description
                else:
                    # Cypher flagged it but TimeArrowRule disagrees
                    # (edge case with time precision). Skip false positive.
                    continue
            except (ValueError, TypeError):
                desc = (
                    f"SHIPPING {eid} on {record['event_date']} precedes "
                    f"origin {record['origin_event_id']} on {record['origin_date']}"
                )

            violations.append(
                {
                    "event_id": eid,
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "lot_tlc": record["lot_tlc"],
                    "product_description": record["product_description"],
                    "violation_type": "broken_chain",
                    "violation_reason": desc,
                    "gaps": ["temporal_paradox"],
                    "origin_event_id": record["origin_event_id"],
                    "origin_date": (str(record["origin_date"]) if record["origin_date"] else None),
                }
            )

        # ------------------------------------------------------------------ #
        # Query 3: Cryptographic gap -- SHIPPING events where origin events
        # exist but the merkle_prev_hash chain does not connect the SHIPPING
        # event to any origin event for the same Lot.
        # ------------------------------------------------------------------ #
        # #1301: Scope every event node. The downstream `origin` MATCH
        # (line ~17 of this query) collects merkle_hashes that the
        # shipping.merkle_prev_hash is compared against. A cross-tenant
        # origin whose hash happens to match could mask a genuine
        # cryptographic-chain break, so the `origin.tenant_id` predicate is
        # load-bearing for the integrity guarantee.
        crypto_gap_query = """
        MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
        WHERE l.tenant_id = $tenant_id
          AND shipping.tenant_id = $tenant_id
          AND shipping.merkle_hash IS NOT NULL
        AND EXISTS {
            MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
            WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING']
              AND origin.tenant_id = $tenant_id
        }
        // @page
        MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
        WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING']
          AND origin.tenant_id = $tenant_id
        WITH shipping, l, _page_key,
             collect({
                 event_id: origin.event_id,
                 type: origin.type,
                 event_date: origin.event_date,
                 merkle_hash: origin.merkle_hash
             }) AS origins
        RETURN
            _page_key,
            coalesce(shipping.merkle_prev_hash IS NULL
             OR NOT any(o IN origins WHERE o.merkle_hash = shipping.merkle_prev_hash), false) AS _hit,
            shipping.event_id          AS event_id,
            shipping.type              AS type,
            shipping.event_date        AS event_date,
            shipping.document_id       AS document_id,
            shipping.merkle_hash       AS merkle_hash,
            shipping.merkle_prev_hash  AS merkle_prev_hash,
            l.tlc                      AS lot_tlc,
            l.product_description      AS product_description,
            origins                    AS expected_predecessors
        """

        async for record in _run_paged(
            session, crypto_gap_query, anchors=_CHAIN_ANCHORS, key=_CHAIN_KEY, order=_CHAIN_ORDER, tenant_id=tenant_id
        ):
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)
            violations.append(
                {
                    "event_id": eid,
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "lot_tlc": record["lot_tlc"],
                    "product_description": record["product_description"],
                    "violation_type": "broken_chain",
                    "violation_reason": (
                        "SHIPPING event hash-chain does not link to any CREATION, RECEIVING, or INITIAL_PACKING event"
                    ),
                    "merkle_hash": record["merkle_hash"],
                    "merkle_prev_hash": record["merkle_prev_hash"],
                    "expected_predecessor": record["expected_predecessors"],
                    "gaps": ["missing_cryptographic_link"],
                }
            )

    query_time = (time.time() - start_time) * 1000
    logger.info(
        "broken_chain_analysis_completed",
        violation_count=len(violations),
        missing_origin_count=sum(1 for v in violations if "missing_origin_event" in v["gaps"]),
        temporal_paradox_count=sum(1 for v in violations if "temporal_paradox" in v["gaps"]),
        cryptographic_gap_count=sum(1 for v in violations if "missing_cryptographic_link" in v["gaps"]),
        query_time_ms=round(query_time, 2),
    )

    return violations


async def find_all_gaps(
    client: Neo4jClient,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    """
    Find all gaps and violations including broken chains.

    Combines results from:
    - find_gaps(): Missing KDE violations
    - find_broken_chains(): Broken chain of custody violations

    Returns:
        Combined list of all gaps and violations

    Raises:
        ValueError: if `tenant_id` is None or empty (propagated from
            the underlying gap queries, which require a tenant).
    """
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("find_all_gaps requires a non-empty tenant_id; null-tenant queries are no longer supported")

    gaps = await find_gaps(client, tenant_id)
    broken_chains = await find_broken_chains(client, tenant_id)

    # Combine results
    all_violations = gaps + broken_chains

    logger.info(
        "comprehensive_gap_analysis_completed",
        missing_kde_count=len(gaps),
        broken_chain_count=len(broken_chains),
        total_violations=len(all_violations),
    )

    return all_violations
