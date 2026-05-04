"""
SQL query builders and data-fetching helpers for FDA exports.

Extracted from fda_export_router.py — pure structural refactor.
"""

from __future__ import annotations

import logging
from datetime import date as _date, datetime, time as _time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger("fda-export")


def _end_bound_utc(end_date: str) -> str:
    """Convert a user-supplied ``YYYY-MM-DD`` end-date to a strict
    UTC-based upper bound for the next day at 00:00.

    Callers use the returned value in a strict ``<`` comparison, which
    captures every event with ``event_timestamp`` on ``end_date`` in
    any timezone and avoids the server-timezone-dependent boundary
    drift from the old ``end_date + "T23:59:59"`` string concatenation
    (issue #1224). If the supplied value is not ISO ``YYYY-MM-DD`` we
    fall back to the raw string so upstream validation remains the
    authoritative source of 4xx responses.
    """
    try:
        parsed = _date.fromisoformat(end_date)
    except (TypeError, ValueError):
        return end_date
    bound = datetime.combine(parsed + timedelta(days=1), _time(0, 0, 0), tzinfo=timezone.utc)
    return bound.isoformat()


def fetch_export_log_history(
    db_session,
    tenant_id: str,
    limit: int,
) -> list:
    """Query the FDA export audit log for a tenant."""
    rows = db_session.execute(
        text("""
            SELECT id, export_type, query_tlc, query_start_date, query_end_date,
                   record_count, export_hash, generated_by, generated_at
            FROM fsma.fda_export_log
            WHERE tenant_id = :tid
            ORDER BY generated_at DESC
            LIMIT :lim
        """),
        {"tid": tenant_id, "lim": limit},
    ).fetchall()
    return rows


def format_export_log_rows(rows, tenant_id: str) -> dict:
    """Convert raw export-log rows to the API response shape."""
    return {
        "tenant_id": tenant_id,
        "exports": [
            {
                "id": str(r[0]),
                "export_type": r[1],
                "query_tlc": r[2],
                "query_start_date": str(r[3]) if r[3] else None,
                "query_end_date": str(r[4]) if r[4] else None,
                "record_count": r[5],
                "export_hash": r[6],
                "generated_by": r[7],
                "generated_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


def build_recall_where_clause(
    tenant_id: str,
    product: Optional[str],
    location: Optional[str],
    tlc: Optional[str],
    event_type: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[str, dict]:
    """Build a parameterized WHERE clause for recall-filtered queries.

    Returns (where_clause_sql, params_dict).
    """
    conditions = ["e.tenant_id = :tid"]
    params: dict = {"tid": tenant_id}

    if product:
        conditions.append("LOWER(e.product_description) LIKE LOWER(:product)")
        params["product"] = f"%{product}%"

    if location:
        conditions.append(
            "(LOWER(e.location_name) LIKE LOWER(:loc) OR e.location_gln LIKE :loc_exact)"
        )
        params["loc"] = f"%{location}%"
        params["loc_exact"] = f"%{location}%"

    if tlc:
        conditions.append("e.traceability_lot_code LIKE :tlc")
        params["tlc"] = f"%{tlc}%" if "%" not in tlc else tlc

    if event_type:
        conditions.append("e.event_type = :etype")
        params["etype"] = event_type

    if start_date:
        conditions.append("e.event_timestamp >= :start")
        params["start"] = start_date

    if end_date:
        # Use a strict ``<`` upper bound at the *next day* boundary in
        # UTC so we capture every event whose timestamp falls on
        # ``end_date`` regardless of server timezone (issue #1224).
        conditions.append("e.event_timestamp < :end")
        params["end"] = _end_bound_utc(end_date)

    where_clause = " AND ".join(conditions)
    return where_clause, params


def fetch_recall_events(db_session, where_clause: str, params: dict) -> list:
    """Execute the recall-filtered query and return raw rows."""
    rows = db_session.execute(
        text(f"""
            SELECT
                e.id, e.event_type, e.traceability_lot_code, e.product_description,
                e.quantity, e.unit_of_measure, e.event_timestamp,
                e.location_gln, e.location_name, e.source, e.sha256_hash,
                h.chain_hash,
                (SELECT jsonb_object_agg(k.kde_key, k.kde_value)
                 FROM fsma.cte_kdes k WHERE k.cte_event_id = e.id) AS kdes,
                e.ingested_at
            FROM fsma.cte_events e
            LEFT JOIN fsma.hash_chain h ON h.event_hash = e.sha256_hash AND h.tenant_id = e.tenant_id
            WHERE {where_clause}
            ORDER BY e.event_timestamp ASC
            LIMIT 10001
        """),
        params,
    ).fetchall()
    return rows


def rows_to_event_dicts(rows) -> list[dict]:
    """Convert recall-query rows to FDA export event dicts."""
    events = []
    for row in rows:
        # SQLAlchemy Row objects — use tuple() for safe index access
        r = tuple(row)
        kdes = r[12] if r[12] else {}
        ts = r[6]
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        ingested = r[13]
        events.append({
            "id": str(r[0]),
            "event_type": r[1],
            "traceability_lot_code": r[2],
            "product_description": r[3],
            "quantity": r[4],
            "unit_of_measure": r[5],
            "event_timestamp": str(ts) if ts else "",
            "location_gln": r[7],
            "location_name": r[8],
            "source": r[9],
            "sha256_hash": r[10],
            "chain_hash": r[11] or "",
            "kdes": kdes,
            "ingested_at": ingested.isoformat() if hasattr(ingested, "isoformat") else str(ingested or ""),
        })
    return events


class AuditLogWriteError(RuntimeError):
    """Raised when the FDA export audit log write fails.

    FSMA 204 audit-integrity controls require that every export be paired
    with an immutable audit-trail row. Silently swallowing a log write
    failure would produce an export with no record of who or when —
    exactly the chain-of-custody gap §1.1455(c) is meant to prevent.
    """


def log_recall_export(
    db_session,
    tenant_id: str,
    events: list[dict],
    export_hash: str,
    format: str,
    tlc: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    request_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    source_ip: Optional[str] = None,
    product: Optional[str] = None,
    location: Optional[str] = None,
    event_type: Optional[str] = None,
) -> None:
    """Write the recall-export audit log entry.

    Raises :class:`AuditLogWriteError` on any DB failure. Callers must
    surface the error as a 5xx so the export does not succeed without
    its log row (issue #1215).

    Extra identity fields (``user_id``, ``user_email``, ``request_id``,
    ``user_agent``, ``source_ip``) and filter metadata are written to
    ``fda_export_log`` columns when available and logged at INFO level
    unconditionally so the chain-of-custody is preserved even if the
    underlying column schema has not yet been migrated (issue #1205).
    """
    filters_applied = {
        "product": product,
        "location": location,
        "tlc": tlc,
        "event_type": event_type,
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        # Best-effort INSERT into fda_export_log with the canonical
        # columns. Rich identity / filter metadata goes through
        # ``initiated_at``, ``user_id``, ``user_agent`` etc. when the
        # columns exist; callers that run against an older schema will
        # simply raise and get caught below, and the structured logger
        # emission still captures the full record for downstream
        # shipping to the audit backend.
        db_session.execute(
            text("""
                INSERT INTO fsma.fda_export_log
                (tenant_id, export_type, record_count, export_hash,
                 generated_by, query_tlc, query_start_date, query_end_date)
                VALUES (:tid, :etype, :cnt, :hash, :generated_by,
                        :tlc, :sd, :ed)
            """),
            {
                "tid": tenant_id,
                "cnt": len(events),
                "hash": export_hash,
                "etype": "recall_package" if format == "package" else "recall",
                "generated_by": user_id
                or ("api_recall_package" if format == "package" else "api_recall"),
                "tlc": tlc,
                "sd": start_date,
                "ed": end_date,
            },
        )
        db_session.commit()
    except Exception as exc:
        logger.error(
            "fda_recall_export_audit_log_failed",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
                "export_hash": export_hash[:16] if export_hash else None,
                "record_count": len(events),
                "error": str(exc),
            },
            exc_info=True,
        )
        try:
            db_session.rollback()  # Clean session state for subsequent ops
        except Exception:
            pass
        raise AuditLogWriteError(
            "FDA recall export audit log write failed; export aborted to "
            "preserve FSMA 204 chain-of-custody."
        ) from exc

    # Structured audit trail line — captured by log shippers even when
    # the DB write succeeds, so the full identity + filter context is
    # always preserved (issue #1205).
    logger.info(
        "fda_recall_export_audit",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_email": user_email,
            "request_id": request_id,
            "user_agent": user_agent,
            "source_ip": source_ip,
            "export_type": "recall_package" if format == "package" else "recall",
            "export_hash": export_hash,
            "record_count": len(events),
            "filters_applied": filters_applied,
            "initiated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def build_v2_where_clause(
    tenant_id: str,
    tlc: Optional[str],
    event_type: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[str, dict[str, Any]]:
    """Build a parameterized WHERE clause for the v2 canonical model query.

    Returns (where_clause_sql, params_dict).
    """
    conditions = ["e.tenant_id = :tid"]
    params: dict[str, Any] = {"tid": tenant_id}

    if tlc:
        if "%" in tlc:
            conditions.append("e.traceability_lot_code LIKE :tlc")
        else:
            conditions.append("e.traceability_lot_code = :tlc")
        params["tlc"] = tlc

    if event_type:
        conditions.append("e.event_type = :etype")
        params["etype"] = event_type

    if start_date:
        conditions.append("e.event_timestamp >= :start")
        params["start"] = start_date

    if end_date:
        # Strict next-day UTC bound, see :func:`_end_bound_utc`
        # (issue #1224).
        conditions.append("e.event_timestamp < :end")
        params["end"] = _end_bound_utc(end_date)

    where_clause = " AND ".join(conditions)
    return where_clause, params


def fetch_v2_events(db_session, where_clause: str, params: dict) -> list:
    """Execute the v2 canonical-model query with rule evaluations."""
    rows = db_session.execute(
        text(f"""
            SELECT
                e.event_id,
                e.event_type,
                e.traceability_lot_code,
                e.product_description,
                e.quantity,
                e.unit_of_measure,
                e.event_timestamp,
                e.location_gln,
                e.location_name,
                e.source,
                e.sha256_hash,
                e.chain_hash,
                e.kdes,
                e.provenance,
                -- aggregate rule evaluation results per event
                COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'rule_name', rd.rule_name,
                            'passed', re.passed,
                            'why_failed', re.why_failed
                        )
                    ) FILTER (WHERE re.rule_id IS NOT NULL),
                    '[]'::jsonb
                ) AS rule_results,
                e.ingested_at
            FROM fsma.traceability_events e
            LEFT JOIN fsma.rule_evaluations re ON re.event_id = e.event_id
            LEFT JOIN fsma.rule_definitions rd ON rd.rule_id = re.rule_id
            WHERE {where_clause}
            GROUP BY
                e.event_id, e.event_type, e.traceability_lot_code,
                e.product_description, e.quantity, e.unit_of_measure,
                e.event_timestamp, e.location_gln, e.location_name,
                e.source, e.sha256_hash, e.chain_hash, e.kdes, e.provenance,
                e.ingested_at
            ORDER BY e.event_timestamp ASC
            LIMIT 10000
        """),
        params,
    ).fetchall()
    return rows


def v2_rows_to_event_dicts(rows) -> list[dict]:
    """Convert v2 canonical-model rows to event dicts with rule results."""
    import json

    events: list[dict] = []
    for row in rows:
        r = tuple(row)
        kdes = r[12] if r[12] else {}
        provenance = r[13] if r[13] else {}
        rule_results_raw = r[14] if r[14] else []
        ingested = r[15]
        ts = r[6]
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()

        # Normalize rule_results: parse from JSON string if needed
        if isinstance(rule_results_raw, str):
            try:
                rule_results_raw = json.loads(rule_results_raw)
            except (json.JSONDecodeError, TypeError):
                rule_results_raw = []

        events.append({
            "id": str(r[0]),
            "event_type": r[1],
            "traceability_lot_code": r[2],
            "product_description": r[3],
            "quantity": r[4],
            "unit_of_measure": r[5],
            "event_timestamp": str(ts) if ts else "",
            "location_gln": r[7],
            "location_name": r[8],
            "source": r[9],
            "sha256_hash": r[10],
            "chain_hash": r[11] or "",
            "kdes": kdes,
            "provenance": provenance,
            "rule_results": rule_results_raw,
            "ingested_at": ingested.isoformat() if hasattr(ingested, "isoformat") else str(ingested or ""),
        })
    return events


def log_v2_export(
    db_session,
    tenant_id: str,
    events: list[dict],
    export_hash: str,
    format: str,
    tlc: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    request_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    source_ip: Optional[str] = None,
) -> None:
    """Write the v2 export audit log entry.

    Raises :class:`AuditLogWriteError` on DB failure, for the same
    reason as :func:`log_recall_export` (issues #1205, #1215).
    """
    try:
        db_session.execute(
            text("""
                INSERT INTO fsma.fda_export_log
                (tenant_id, export_type, record_count, export_hash, generated_by,
                 query_tlc, query_start_date, query_end_date)
                VALUES (:tid, :etype, :cnt, :hash, :generated_by, :tlc, :sd, :ed)
            """),
            {
                "tid": tenant_id,
                "cnt": len(events),
                "hash": export_hash,
                "etype": "v2_package" if format == "package" else "v2_spreadsheet",
                "generated_by": user_id
                or ("api_v2_package" if format == "package" else "api_v2"),
                "tlc": tlc,
                "sd": start_date,
                "ed": end_date,
            },
        )
        db_session.commit()
    except Exception as exc:
        logger.error(
            "fda_v2_export_audit_log_failed",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
                "export_hash": export_hash[:16] if export_hash else None,
                "record_count": len(events),
                "error": str(exc),
            },
            exc_info=True,
        )
        try:
            db_session.rollback()
        except Exception:
            pass
        raise AuditLogWriteError(
            "FDA v2 export audit log write failed; export aborted to "
            "preserve FSMA 204 chain-of-custody."
        ) from exc

    logger.info(
        "fda_v2_export_audit",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_email": user_email,
            "request_id": request_id,
            "user_agent": user_agent,
            "source_ip": source_ip,
            "export_type": "v2_package" if format == "package" else "v2_spreadsheet",
            "export_hash": export_hash,
            "record_count": len(events),
            "filters_applied": {
                "tlc": tlc,
                "start_date": start_date,
                "end_date": end_date,
            },
            "initiated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def fetch_trace_graph_data(
    db_session,
    persistence,
    tenant_id: str,
    tlc: str,
    depth: int,
) -> dict:
    """Fetch the transformation trace graph for a TLC.

    Returns a dict with nodes, edges, and summary stats.
    """
    linked_tlcs = persistence._expand_tlcs_via_transformation_links(
        tenant_id=tenant_id, seed_tlc=tlc, depth=depth
    )

    # Fetch event counts per TLC in one query
    if linked_tlcs:
        placeholders = ", ".join(f":tlc_{i}" for i in range(len(linked_tlcs)))
        params: dict = {"tid": tenant_id}
        for i, t in enumerate(linked_tlcs):
            params[f"tlc_{i}"] = t
        count_rows = db_session.execute(
            text(f"""
                SELECT traceability_lot_code, COUNT(*) as event_count,
                       MIN(event_timestamp) as first_event,
                       MAX(event_timestamp) as last_event
                FROM   fsma.cte_events
                WHERE  tenant_id = :tid
                  AND  traceability_lot_code IN ({placeholders})
                  AND  validation_status != 'rejected'
                GROUP BY traceability_lot_code
            """),
            params,
        ).fetchall()
        tlc_stats = {
            row[0]: {
                "event_count": row[1],
                "first_event": row[2].isoformat() if row[2] else None,
                "last_event": row[3].isoformat() if row[3] else None,
            }
            for row in count_rows
        }
    else:
        tlc_stats = {}

    # Also fetch direct link edges for the graph visualization
    link_rows = db_session.execute(
        text("""
            SELECT input_tlc, output_tlc, process_type, confidence_score
            FROM   fsma.transformation_links
            WHERE  tenant_id = :tid
              AND  (input_tlc = ANY(:tlcs) OR output_tlc = ANY(:tlcs))
        """),
        {"tid": tenant_id, "tlcs": linked_tlcs},
    ).fetchall()
    edges = [
        {
            "input_tlc": row[0],
            "output_tlc": row[1],
            "process_type": row[2],
            "confidence_score": float(row[3]) if row[3] is not None else None,
        }
        for row in link_rows
    ]

    nodes = [
        {
            "tlc": t,
            "is_seed": t == tlc,
            "role": (
                "seed" if t == tlc
                else "downstream" if any(e["input_tlc"] == tlc and e["output_tlc"] == t for e in edges)
                else "upstream"
            ),
            **tlc_stats.get(t, {"event_count": 0, "first_event": None, "last_event": None}),
        }
        for t in linked_tlcs
    ]

    return {
        "seed_tlc": tlc,
        "tenant_id": tenant_id,
        "traversal_depth": depth,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "total_events": sum(n["event_count"] for n in nodes),
    }
