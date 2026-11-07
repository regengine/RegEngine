"""Snapshot of rule definitions and the rule versions evaluated against events.

Evidence packages (the FDA export ZIP and the request-workflow package)
must say which rules, at which versions, judged the records they carry.
Before this module the request-workflow assembler took a private copy of
the whole ``fsma.rule_definitions`` catalog and the FDA package carried no
rule information at all. Both now call :func:`snapshot_rule_versions`.

The snapshot never raises: a database failure degrades to
``catalog_status`` / ``evaluated_status`` of ``"unavailable"`` so the
export still ships and states what it could not record, instead of
silently omitting the section.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from shared.rules.enforcement import current_mode
from sqlalchemy import text

logger = logging.getLogger("rules-versions")

# ``fsma.rule_definitions`` is a shared catalog with no tenant rows (see
# ``global_sql_tables`` in .semgrep/tenant-scope-allowlist.yml), so the
# catalog read carries no tenant predicate on purpose.
_CATALOG_SQL = text("SELECT rule_id, rule_version, title, severity, category FROM fsma.rule_definitions ORDER BY rule_id")

# Which (rule, version) pairs actually judged the given events. Tenant
# scoped: ``fsma.rule_evaluations`` holds tenant rows.
_EVALUATED_SQL = text(
    """
    SELECT rule_id, rule_version, COUNT(*) AS evaluation_count
    FROM   fsma.rule_evaluations
    WHERE  tenant_id = CAST(:tid AS uuid)
      AND  CAST(event_id AS text) = ANY(:event_ids)
    GROUP  BY rule_id, rule_version
    ORDER  BY rule_id, rule_version
    """
)


def _execute_isolated(db: Any, statement: Any, params: Optional[Dict[str, Any]] = None) -> Any:
    """Run one read on its own SAVEPOINT when the session supports it.

    On PostgreSQL a failed statement aborts the enclosing transaction
    (``InFailedSqlTransaction``), so without a savepoint a missing
    ``fsma.rule_definitions`` would poison the evaluated read below and
    every later query the caller issues on the same session. Sessions
    without ``begin_nested`` (unit-test fakes) run the statement directly.
    """
    begin_nested = getattr(db, "begin_nested", None)
    if callable(begin_nested):
        with begin_nested():
            return db.execute(statement, params) if params is not None else db.execute(statement)
    return db.execute(statement, params) if params is not None else db.execute(statement)


def snapshot_rule_versions(
    db: Any,
    tenant_id: Optional[str] = None,
    event_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Return a serialisable snapshot of rule versions.

    ``catalog`` maps every ``rule_id`` in ``fsma.rule_definitions`` to its
    current ``version``, ``title``, ``severity`` and ``category`` (the
    shape the request-workflow package has always stored).

    ``evaluated`` lists the distinct ``(rule_id, rule_version)`` pairs in
    ``fsma.rule_evaluations`` for ``event_ids`` within ``tenant_id``, with
    an evaluation count each. That is the version that actually judged the
    exported records, which can differ from the catalog's current version
    when a rule has since been bumped. It is only computed when both
    ``tenant_id`` and ``event_ids`` are given.

    ``enforcement_mode`` records ``RULES_ENGINE_ENFORCE`` at snapshot time
    (``off`` means rule failures were advisory and did not block ingest).
    """
    snapshot: Dict[str, Any] = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "enforcement_mode": current_mode(),
        "catalog": {},
        "catalog_status": "unavailable",
        "evaluated": [],
        "evaluated_status": "not_requested",
    }

    try:
        rows = _execute_isolated(db, _CATALOG_SQL).mappings().fetchall()
        for row in rows:
            snapshot["catalog"][str(row["rule_id"])] = {
                "version": row.get("rule_version"),
                "title": row.get("title"),
                "severity": row.get("severity"),
                "category": row.get("category"),
            }
        snapshot["catalog_status"] = "ok"
    except Exception:
        logger.debug("rule_versions_catalog_unavailable", exc_info=True)

    ids = [str(e) for e in (event_ids or []) if e]
    if tenant_id and ids:
        try:
            rows = (
                _execute_isolated(db, _EVALUATED_SQL, {"tid": str(tenant_id), "event_ids": ids}).mappings().fetchall()
            )
            snapshot["evaluated"] = [
                {
                    "rule_id": str(row["rule_id"]),
                    "rule_version": row.get("rule_version"),
                    "evaluation_count": int(row.get("evaluation_count") or 0),
                }
                for row in rows
            ]
            snapshot["evaluated_status"] = "ok"
        except Exception:
            snapshot["evaluated_status"] = "unavailable"
            logger.debug("rule_versions_evaluated_unavailable", exc_info=True)

    return snapshot
