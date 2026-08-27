"""KDE validation, compliance-alert generation, and the post-ingest
obligation check.

Code moved verbatim from the original ``webhook_router_v2.py``.
Collaborators that lived at module level in the original file are
resolved through the package namespace (``_pkg``) at call time so
monkeypatching ``app.webhook_router_v2.<name>`` keeps working.
"""

from __future__ import annotations

import json
import sys

from sqlalchemy.exc import SQLAlchemyError

from ..webhook_models import IngestEvent

_pkg = sys.modules[__package__]


# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------

def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type."""
    errors: list[str] = []
    required = _pkg.REQUIRED_KDES_BY_CTE.get(event.cte_type, [])

    available: dict[str, object] = {
        "traceability_lot_code": event.traceability_lot_code,
        "product_description": event.product_description,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "location_name": event.location_name,
        "location_gln": event.location_gln,
        **event.kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {event.cte_type.value} CTE")

    return errors


# ---------------------------------------------------------------------------
# Compliance Alerts
# ---------------------------------------------------------------------------

def _generate_alerts(event: IngestEvent) -> list[dict]:
    """Generate compliance alerts for an event."""
    alerts: list[dict] = []

    if event.cte_type.value in ("shipping", "receiving"):
        has_source = event.kdes.get("ship_from_location") or event.kdes.get("ship_from_gln")
        has_dest = event.kdes.get("ship_to_location") or event.kdes.get("ship_to_gln") or event.kdes.get("receiving_location")
        if not has_source or not has_dest:
            alerts.append({
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event missing source or destination identifiers",
            })

    return alerts


# ---------------------------------------------------------------------------
# Post-Ingest Obligation Check
# ---------------------------------------------------------------------------

def _check_obligations(db_session, event: IngestEvent, event_id: str, tenant_id: str) -> list[dict]:
    """
    Check ingested event against obligation-CTE rules from the database.

    For each obligation that applies to this CTE type, verify that the required
    KDE is present in the event. Write pass/fail results to fsma.compliance_alerts.

    Returns list of failed obligation checks (alerts).
    """
    if db_session is None:
        return []

    try:
        from sqlalchemy import text

        # Fetch rules for this CTE type + rules that apply to all CTE types
        # Use savepoint so a UUID cast failure doesn't abort the outer transaction
        nested = db_session.begin_nested()
        try:
            rows = db_session.execute(
                text("""
                    SELECT r.id, r.obligation_id, r.cte_type, r.required_kde_key,
                           r.validation_rule, r.description,
                           o.obligation_text, o.risk_category
                    FROM obligation_cte_rules r
                    JOIN obligations o ON o.id = r.obligation_id
                    WHERE o.tenant_id = CAST(:tid AS uuid)
                      AND r.cte_type IN (:cte_type, 'all')
                    ORDER BY o.risk_category DESC
                """),
                {"tid": tenant_id, "cte_type": event.cte_type.value},
            ).fetchall()
        except (SQLAlchemyError, ValueError, TypeError, RuntimeError) as exc:
            nested.rollback()
            _pkg.logger.debug("obligation_query_rollback: %s", str(exc))
            return []

        if not rows:
            return []

        alerts = []
        # Build available KDE values from event
        available = {
            "traceability_lot_code": event.traceability_lot_code,
            "product_description": event.product_description,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "location_name": event.location_name,
            "location_gln": event.location_gln,
            **event.kdes,
        }

        for row in rows:
            rule_id, obl_id, cte_type, kde_key, validation_rule, desc, obl_text, risk = row

            passed = True
            if validation_rule == "present" and kde_key:
                val = available.get(kde_key)
                passed = val is not None and (not isinstance(val, str) or val.strip() != "")
            elif validation_rule == "tlc_assigned":
                passed = bool(event.traceability_lot_code and len(event.traceability_lot_code) >= 3)
            elif validation_rule == "tlc_not_reassigned":
                # Shipping events should NOT create new TLCs — the TLC must already
                # exist in prior events (harvesting, packing, etc.)
                if event.cte_type.value in ("shipping", "transformation"):
                    prior = db_session.execute(
                        text("""
                            SELECT COUNT(*) FROM fsma.cte_events
                            WHERE tenant_id = :tid
                              AND traceability_lot_code = :tlc
                              AND event_type NOT IN ('shipping', 'transformation')
                        """),
                        {"tid": tenant_id, "tlc": event.traceability_lot_code},
                    ).scalar()
                    passed = (prior or 0) > 0
                else:
                    passed = True
            elif validation_rule == "downstream_transmitted":
                # Receiving events should have upstream source info (ship_from)
                # Shipping events should have downstream destination (ship_to)
                if event.cte_type.value == "receiving":
                    passed = bool(
                        available.get("ship_from_location")
                        or available.get("ship_from_gln")
                        or available.get("immediate_previous_source")
                    )
                elif event.cte_type.value == "shipping":
                    passed = bool(
                        available.get("ship_to_location")
                        or available.get("ship_to_gln")
                    )
                else:
                    passed = True
            elif validation_rule == "record_exists":
                # Verify that records exist in the chain for this TLC
                # (i.e., this isn't an orphan event with no audit trail)
                _chain_count = db_session.execute(
                    text("""
                        SELECT COUNT(*) FROM fsma.hash_chain h
                        JOIN fsma.cte_events e ON e.id = h.cte_event_id
                        WHERE e.tenant_id = :tid
                          AND e.traceability_lot_code = :tlc
                    """),
                    {"tid": tenant_id, "tlc": event.traceability_lot_code},
                ).scalar()
                # For first event of a TLC, chain_count will be 0 (just ingested,
                # chain entry may not exist yet). Allow it.
                # For subsequent events, at least 1 prior chain entry should exist.
                passed = True  # Chain is verified at scoring time; here we just check existence

            if not passed:
                severity = "critical" if risk == "CRITICAL" else "warning"
                alert = {
                    "severity": severity,
                    "alert_type": "chain_break",
                    "message": f"Obligation not met: {obl_text[:100]}",
                    "obligation_id": str(obl_id),
                    "missing_kde": kde_key,
                }
                alerts.append(alert)

                # Write to compliance_alerts table
                # Savepoint per alert (#2901). This function is called from
                # inside the ingest request transaction, so an INSERT that
                # fails — bad uuid cast, RLS denial, schema skew — would abort
                # the whole transaction on Postgres and take the already-stored
                # events down with it at commit time. Catching the exception is
                # not enough without rolling back to a savepoint first. Same
                # guard the rules SELECT above and writes.store_event already
                # use.
                alert_sp = db_session.begin_nested()
                try:
                    db_session.execute(
                        text("""
                            INSERT INTO fsma.compliance_alerts
                            (tenant_id, org_id, event_id, severity, alert_type, message, details)
                            VALUES (CAST(:tid AS uuid), CAST(:tid AS uuid), :eid::uuid, :sev, :atype, :msg, :details::jsonb)
                        """),
                        {
                            "tid": tenant_id,
                            "eid": event_id,
                            "sev": severity,
                            "atype": "chain_break",
                            "msg": f"Missing KDE '{kde_key}' required by obligation",
                            "details": json.dumps({
                                "obligation_id": str(obl_id),
                                "obligation_text": obl_text[:200],
                                "risk_category": risk,
                                "missing_kde": kde_key,
                            }),
                        },
                    )
                    alert_sp.commit()
                except (SQLAlchemyError, ValueError, RuntimeError) as alert_err:
                    alert_sp.rollback()
                    _pkg.logger.warning("obligation_alert_write_failed: %s", str(alert_err))

        return alerts

    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        _pkg.logger.warning("obligation_check_failed: %s", str(exc))
        return []
