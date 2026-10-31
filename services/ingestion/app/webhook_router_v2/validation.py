"""KDE validation, compliance-alert generation, and the post-ingest
obligation check.

Code moved verbatim from the original ``webhook_router_v2.py``.
Collaborators that lived at module level in the original file are
resolved through the package namespace (``_pkg``) at call time so
monkeypatching ``app.webhook_router_v2.<name>`` keeps working.
"""

from __future__ import annotations

import json
import re
import sys

from sqlalchemy.exc import SQLAlchemyError

from ..webhook_models import IngestEvent

_pkg = sys.modules[__package__]


# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------


def _authoritative_kdes(event: IngestEvent) -> dict[str, object]:
    """Merge top-level fields over ``event.kdes`` for presence checks.

    The typed top-level fields are authoritative: a colliding KDE entry
    (for example ``kdes: {"location_name": ""}``) must neither erase a
    real top-level value (false rejection) nor override it with an
    unvalidated one. KDE entries still fill gaps where the top level is
    absent, preserving the historical pass for KDE-carried locations.
    """
    available: dict[str, object] = dict(event.kdes)
    for _key, _val in (
        ("traceability_lot_code", event.traceability_lot_code),
        ("product_description", event.product_description),
        ("quantity", event.quantity),
        ("unit_of_measure", event.unit_of_measure),
        ("location_name", event.location_name),
        ("location_gln", event.location_gln),
    ):
        if _val is None:
            continue
        if isinstance(_val, str) and _val.strip() == "":
            continue
        available[_key] = _val
    # Contract v3 wire name is input_lot_codes; accept Lab's legacy
    # input_traceability_lot_codes (kdes or top-level) as a fill-in.
    def _present(val: object) -> bool:
        if val is None:
            return False
        if isinstance(val, str):
            return val.strip() != ""
        if isinstance(val, (list, tuple, set)):
            return len(val) > 0
        return True

    if not _present(available.get("input_lot_codes")):
        legacy = available.get("input_traceability_lot_codes")
        if not _present(legacy):
            legacy = getattr(event, "input_traceability_lot_codes", None)
        if _present(legacy):
            available["input_lot_codes"] = legacy
    return available


def _kde_present(val: object) -> bool:
    """True when a KDE value is non-empty (string, list, or other scalar)."""
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() != ""
    if isinstance(val, (list, tuple, set)):
        return any(_kde_present(item) for item in val)
    if isinstance(val, dict):
        return any(_kde_present(item) for item in val.values())
    return True


def _event_ftl_payload(event: IngestEvent) -> dict:
    """Build the dict shape ``is_ftl_food`` expects from an IngestEvent."""
    payload: dict = {"kdes": dict(event.kdes or {})}
    # Top-level FTL hints (rare) still count if present on the event object.
    for key in ("ftl_covered", "ftl_category"):
        if hasattr(event, key):
            val = getattr(event, key)
            if val is not None:
                payload[key] = val
    return payload



def _parse_cooled_flag(val: object) -> bool | None:
    """Parse explicit cooled yes/no. None means missing / unparseable."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and val in (0, 1):
        return bool(val)
    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        if normalized == "":
            return None
    return None


def _looks_like_internal_id(val: object) -> bool:
    """True for opaque codes (FIELD-A7, UUID-like) rather than display names."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not s or " " in s:
        return False
    # Hyphenated uppercase/digit tokens or UUID-ish strings are internal ids.
    if re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", s):
        return True
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s):
        return True
    if re.fullmatch(r"[A-Z]{1,12}-?[0-9]{1,8}", s):
        return True
    return False


def _is_human_readable_name(val: object) -> bool:
    """True when a value looks like a human-readable place/field name."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if len(s) < 2:
        return False
    if _looks_like_internal_id(s):
        return False
    # Must contain a letter; prefer spaces / mixed content over pure codes.
    if not any(ch.isalpha() for ch in s):
        return False
    return True


def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type.

    A-2190 / contract v3: Subpart S required-KDE gates apply when the product
    is FTL or FTL status is unknown. Explicit ``ftl_covered=False`` (or a
    non-FTL category) skips the required-KDE list so non-FTL foods are not
    scored as gaps. Keep A-2170 location_incomplete behaviour untouched.
    """
    errors: list[str] = []

    # FTL gate (fix 5). Import locally so monkeypatches on shared.rules.ftl
    # and missing optional deps in unit tests stay isolated.
    try:
        from shared.rules.ftl import is_ftl_food
    except ImportError:  # pragma: no cover - shared always present in service
        is_ftl_food = None  # type: ignore[assignment]

    if is_ftl_food is not None:
        ftl_status = is_ftl_food(_event_ftl_payload(event))
        if ftl_status is False:
            return []

    required = _pkg.REQUIRED_KDES_BY_CTE.get(event.cte_type, [])
    available = _authoritative_kdes(event)

    for kde_name in required:
        val = available.get(kde_name)
        if kde_name == "harvester_business_phone" and not isinstance(val, str):
            errors.append("Harvester business phone must be a non-empty string")
        elif not _kde_present(val):
            errors.append(f"Missing required KDE '{kde_name}' for {event.cte_type.value} CTE")

    # Initial packing conditionals (A-2190 fix 2; Food Safety Lens answers):
    # - farm location description (name + phone + address) separately required
    # - field/growing area must be a human-readable name (internal id alone
    #   only when a readable name is also supplied for export)
    # - explicit cooled yes/no required; cooling_* only when cooled=yes
    #   (do not infer cooled from cooling field presence)
    cte_value = getattr(event.cte_type, "value", event.cte_type)
    if cte_value == "initial_packing":
        for farm_key in (
            "harvest_location_name",
            "harvest_location_phone",
            "harvest_location_address",
        ):
            # harvest_location_name is also in REQUIRED_KDES_BY_CTE; re-check
            # phone/address here so the farm description is complete as a set.
            if farm_key == "harvest_location_name":
                continue
            if not _kde_present(available.get(farm_key)):
                errors.append(
                    f"Missing required KDE '{farm_key}' for initial_packing CTE "
                    "(farm location description: name, phone, and address)"
                )

        growing_name = available.get("growing_area_name")
        field_name = available.get("field_name")
        field_id = available.get("field_id")
        has_readable_name = _is_human_readable_name(growing_name) or _is_human_readable_name(
            field_name
        )
        has_readable_field_id = _is_human_readable_name(field_id) and not _looks_like_internal_id(
            field_id
        )
        # Internal id alone is OK only when a human-readable name is also present
        # (stand-in for "maps to a name in the export" at ingest time).
        has_mapped_internal_id = _kde_present(field_id) and has_readable_name
        if not (has_readable_name or has_readable_field_id or has_mapped_internal_id):
            errors.append(
                "Missing required human-readable growing area or field name for "
                "initial_packing CTE (growing_area_name or field_name; field_id "
                "alone only when paired with a readable name for export)"
            )

        cooled_parsed = _parse_cooled_flag(available.get("cooled"))
        if cooled_parsed is None:
            errors.append(
                "Missing required KDE 'cooled' for initial_packing CTE "
                "(explicit yes/no required; do not infer from cooling fields)"
            )
        elif cooled_parsed is True:
            if not _kde_present(available.get("cooling_location_name")):
                errors.append(
                    "Missing required KDE 'cooling_location_name' for initial_packing CTE "
                    "(required when cooled=yes)"
                )
            if not _kde_present(available.get("cooling_date")):
                errors.append(
                    "Missing required KDE 'cooling_date' for initial_packing CTE "
                    "(required when cooled=yes)"
                )

    return errors


# ---------------------------------------------------------------------------
# Compliance Alerts
# ---------------------------------------------------------------------------


def _generate_alerts(event: IngestEvent) -> list[dict]:
    """Generate compliance alerts for an event."""
    alerts: list[dict] = []

    if event.cte_type.value in ("shipping", "receiving"):
        has_source = event.kdes.get("ship_from_location") or event.kdes.get("ship_from_gln")
        has_dest = (
            event.kdes.get("ship_to_location") or event.kdes.get("ship_to_gln") or event.kdes.get("receiving_location")
        )
        if not has_source or not has_dest:
            alerts.append(
                {
                    "severity": "warning",
                    "alert_type": "incomplete_route",
                    "message": "Shipping/receiving event missing source or destination identifiers",
                }
            )

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

    rules_ok = True
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
            nested.commit()
        except (SQLAlchemyError, ValueError, TypeError, RuntimeError) as exc:
            nested.rollback()
            rules_ok = False
            # M-5: a skipped obligation pass must be loud, not silent.
            _pkg.logger.warning("obligation_query_rollback: %s", str(exc))
            _pkg._record_obligation_skip()
            return []

        if not rows:
            return []

        alerts = []
        # Build available KDE values from event (top-level authoritative,
        # KDE-carried values fill gaps — see _authoritative_kdes).
        available = _authoritative_kdes(event)

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
                    passed = bool(available.get("ship_to_location") or available.get("ship_to_gln"))
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
                          AND h.tenant_id = :tid
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
                            (tenant_id, org_id, cte_event_id, event_id, severity, alert_type, message, details)
                            VALUES (CAST(:tid AS uuid), CAST(:tid AS uuid), CAST(:eid AS uuid), CAST(:eid AS uuid),
                                    :sev, :atype, :msg, CAST(:details AS jsonb))
                        """),
                        {
                            "tid": tenant_id,
                            "eid": event_id,
                            "sev": severity,
                            "atype": "chain_break",
                            "msg": f"Missing KDE '{kde_key}' required by obligation",
                            "details": json.dumps(
                                {
                                    "obligation_id": str(obl_id),
                                    "obligation_text": obl_text[:200],
                                    "risk_category": risk,
                                    "missing_kde": kde_key,
                                }
                            ),
                        },
                    )
                    alert_sp.commit()
                except (SQLAlchemyError, ValueError, RuntimeError) as alert_err:
                    alert_sp.rollback()
                    _pkg.logger.warning("obligation_alert_write_failed: %s", str(alert_err))

        if not alerts and rules_ok and rows:
            # Jev second-judgment (M-5): the rules ran clean, but does the
            # event still look review-worthy? A flag here is observability,
            # not a compliance determination — it is returned to the caller
            # and never written to fsma.compliance_alerts.
            review_flag = _pkg.review_event_for_alert_worthiness(event, rules_evaluated=len(rows))
            if review_flag is not None:
                _pkg._record_jev_review_flag(tenant_id)
                alerts.append(review_flag)

        return alerts

    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        _pkg.logger.warning("obligation_check_failed: %s", str(exc))
        return []
