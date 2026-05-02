"""Inflow Lab operational workbench APIs.

This router turns stateless sandbox evaluations into durable workbench objects:
replayable scenarios, saved test runs, remediation tasks, readiness summaries,
and explicit commit-gate decisions between sandbox/staging/evidence modes.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from .sandbox.models import SandboxResponse


router = APIRouter(prefix="/api/v1/inflow-workbench", tags=["Inflow Workbench"])

FixStatus = Literal["open", "waiting", "corrected", "accepted"]
FixSeverity = Literal["blocked", "warning", "info"]
CommitMode = Literal["simulation", "preflight", "staging", "production_evidence"]

_STORE_LOCK = threading.Lock()

COMPLETE_ROMAINE_CSV = """cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-FEED-001,Romaine Lettuce,120,cases,Valley Fresh Farms,2026-04-26T15:20:00Z,,,HARV-001
cooling,TLC-FEED-001,Romaine Lettuce,120,cases,Salinas Cooling Hub,2026-04-26T18:12:00Z,,,COOL-001
initial_packing,TLC-FEED-001,Romaine Lettuce,118,cases,Salinas Packhouse,2026-04-26T20:12:00Z,,,PACK-001
shipping,TLC-FEED-001,Romaine Lettuce,118,cases,Salinas Packout Dock,2026-04-26T22:41:00Z,Salinas Packhouse,Bay Area DC,BOL-001
receiving,TLC-FEED-001,Romaine Lettuce,118,cases,Bay Area DC,2026-04-27T02:04:00Z,Salinas Packout Dock,Bay Area DC,REC-001"""

MISSING_DESTINATION_CSV = """cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-FEED-002,Romaine Lettuce,104,cases,Valley Fresh Farms,2026-04-26T15:20:00Z,,,HARV-002
cooling,TLC-FEED-002,Romaine Lettuce,104,cases,Salinas Cooling Hub,2026-04-26T18:12:00Z,,,COOL-002
initial_packing,TLC-FEED-002,Romaine Lettuce,103,cases,Salinas Packhouse,2026-04-26T20:12:00Z,,,PACK-002
shipping,TLC-FEED-002,Romaine Lettuce,103,cases,Salinas Packout Dock,2026-04-26T22:41:00Z,Salinas Packhouse,,BOL-002
receiving,TLC-FEED-002,Romaine Lettuce,103,cases,,2026-04-27T02:04:00Z,Salinas Packout Dock,,"""

BROKEN_LINEAGE_CSV = """cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-FEED-003,Spring Mix,220,cases,Desert Bloom Farm,2026-04-26T14:43:00Z,,,HARV-003
cooling,TLC-FEED-003,Spring Mix,220,cases,Imperial Pre-Cool Facility,2026-04-26T17:51:00Z,,,COOL-003
shipping,TLC-FEED-003,Spring Mix,218,cases,Imperial Packout Dock,2026-04-26T23:03:00Z,Imperial Packhouse,Los Angeles DC,"""

BUILT_IN_SCENARIOS = [
    {
        "id": "complete-romaine-flow",
        "tenant_id": "system",
        "name": "Complete romaine lettuce flow",
        "outcome": "Export-ready full chain",
        "records": "5 CTE records",
        "csv": COMPLETE_ROMAINE_CSV,
        "created_at": "2026-04-30T00:00:00+00:00",
        "built_in": True,
    },
    {
        "id": "missing-shipping-destination",
        "tenant_id": "system",
        "name": "Missing shipping destination",
        "outcome": "Blocked shipping KDE",
        "records": "5 CTE records",
        "csv": MISSING_DESTINATION_CSV,
        "created_at": "2026-04-30T00:00:00+00:00",
        "built_in": True,
    },
    {
        "id": "broken-lineage",
        "tenant_id": "system",
        "name": "Transformation-style broken lineage",
        "outcome": "Incomplete lot chain",
        "records": "3 CTE records",
        "csv": BROKEN_LINEAGE_CSV,
        "created_at": "2026-04-30T00:00:00+00:00",
        "built_in": True,
    },
]


class WorkbenchScenario(BaseModel):
    id: str
    tenant_id: str = "system"
    name: str
    outcome: str
    records: str
    csv: str
    created_at: str
    built_in: bool = False


class CreateScenarioRequest(BaseModel):
    tenant_id: str = Field(default="default")
    name: str = Field(..., min_length=3, max_length=120)
    outcome: str = Field(default="Custom scenario")
    csv: str = Field(..., min_length=1)


class FixQueueItem(BaseModel):
    id: str
    run_id: str
    tenant_id: str
    title: str
    owner: str
    status: FixStatus
    severity: FixSeverity
    impact: str
    source: str
    created_at: str
    updated_at: str


class UpdateFixItemRequest(BaseModel):
    status: Optional[FixStatus] = None
    owner: Optional[str] = Field(default=None, min_length=1, max_length=120)


class ReadinessComponent(BaseModel):
    id: str
    label: str
    score: int
    detail: str


class ReadinessSummary(BaseModel):
    score: int
    label: str
    components: list[ReadinessComponent]


class CommitGateRequest(BaseModel):
    mode: CommitMode
    tenant_id: str = "default"
    result: Optional[SandboxResponse] = None
    authenticated: bool = False
    persisted: bool = False
    provenance_attached: bool = False
    unresolved_fix_count: int = 0


class CommitGateDecision(BaseModel):
    mode: CommitMode
    allowed: bool
    export_eligible: bool
    reasons: list[str]
    next_state: str


class SaveRunRequest(BaseModel):
    tenant_id: str = Field(default="default")
    source: str = Field(default="inflow-lab")
    csv: str = Field(default="")
    result: SandboxResponse


class WorkbenchRun(BaseModel):
    run_id: str
    tenant_id: str
    source: str
    csv: str
    result: SandboxResponse
    readiness: ReadinessSummary
    fix_queue: list[FixQueueItem]
    commit_gate: CommitGateDecision
    saved_at: str
    input_hash: Optional[str] = None
    result_hash: Optional[str] = None
    commit_decision_id: Optional[str] = None


class WorkbenchReadinessSnapshot(BaseModel):
    tenant_id: str
    score: Optional[int] = None
    label: Optional[str] = None
    run_id: Optional[str] = None
    saved_at: Optional[str] = None
    unresolved_fix_count: int = 0
    export_eligible: bool = False
    source: str = "none"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _tenant_uuid(tenant_id: str) -> Optional[str]:
    try:
        return str(uuid.UUID(str(tenant_id)))
    except (TypeError, ValueError):
        return None


def _json_model(value: BaseModel) -> str:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _db_session_for_tenant(tenant_id: str):
    if not _tenant_uuid(tenant_id):
        return None
    try:
        from shared.database import SessionLocal

        return SessionLocal()
    except Exception:
        return None


def _set_tenant_context(db: Any, tenant_id: str) -> None:
    db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


def _store_path() -> Path:
    return Path(os.getenv("REGENGINE_INFLOW_WORKBENCH_PATH", "/tmp/regengine_inflow_workbench.json"))


def _empty_store() -> dict[str, Any]:
    return {"scenarios": [], "runs": {}, "fix_queue": {}}


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    return {
        "scenarios": list(payload.get("scenarios") or []),
        "runs": dict(payload.get("runs") or {}),
        "fix_queue": dict(payload.get("fix_queue") or {}),
    }


def _write_store(store: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")


def _db_list_scenarios(tenant_id: str) -> Optional[list[WorkbenchScenario]]:
    db = _db_session_for_tenant(tenant_id)
    if db is None:
        return None
    try:
        _set_tenant_context(db, tenant_id)
        rows = db.execute(
            text(
                """
                SELECT scenario_id, tenant_id::text AS tenant_id, name, outcome,
                       record_count_label, csv_text, created_at, built_in
                FROM fsma.inflow_workbench_scenarios
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                ORDER BY created_at DESC
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings().all()
        return [
            WorkbenchScenario(
                id=row["scenario_id"],
                tenant_id=row["tenant_id"],
                name=row["name"],
                outcome=row["outcome"],
                records=row["record_count_label"],
                csv=row["csv_text"],
                created_at=_iso(row["created_at"]),
                built_in=bool(row["built_in"]),
            )
            for row in rows
        ]
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _db_create_scenario(scenario: WorkbenchScenario) -> bool:
    tenant_id = _tenant_uuid(scenario.tenant_id)
    if not tenant_id:
        return False
    db = _db_session_for_tenant(tenant_id)
    if db is None:
        return False
    try:
        _set_tenant_context(db, tenant_id)
        db.execute(
            text(
                """
                INSERT INTO fsma.inflow_workbench_scenarios
                    (scenario_id, tenant_id, name, outcome, record_count_label, csv_text, built_in, created_at)
                VALUES
                    (:scenario_id, CAST(:tenant_id AS uuid), :name, :outcome, :records, :csv, :built_in, CAST(:created_at AS timestamptz))
                """
            ),
            {
                "scenario_id": scenario.id,
                "tenant_id": tenant_id,
                "name": scenario.name,
                "outcome": scenario.outcome,
                "records": scenario.records,
                "csv": scenario.csv,
                "built_in": scenario.built_in,
                "created_at": scenario.created_at,
            },
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def _run_from_row(row: Any, fix_queue: list[FixQueueItem]) -> WorkbenchRun:
    result_payload = _json_value(row["result_payload"])
    readiness_payload = _json_value(row["readiness_payload"])
    commit_gate_payload = _json_value(row["commit_gate_payload"])
    return WorkbenchRun(
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        source=row["source"],
        csv=row["csv_text"] or "",
        result=SandboxResponse(**result_payload),
        readiness=ReadinessSummary(**readiness_payload),
        fix_queue=fix_queue,
        commit_gate=CommitGateDecision(**commit_gate_payload),
        saved_at=_iso(row["saved_at"]),
        input_hash=row.get("input_hash"),
        result_hash=row.get("result_hash"),
        commit_decision_id=row.get("commit_decision_id"),
    )


def _db_save_run(run: WorkbenchRun) -> bool:
    tenant_id = _tenant_uuid(run.tenant_id)
    if not tenant_id:
        return False
    db = _db_session_for_tenant(tenant_id)
    if db is None:
        return False
    try:
        _set_tenant_context(db, tenant_id)
        db.execute(
            text(
                """
                INSERT INTO fsma.inflow_workbench_runs
                    (run_id, tenant_id, source, csv_text, result_payload, readiness_payload,
                     commit_gate_payload, input_hash, result_hash, saved_at)
                VALUES
                    (:run_id, CAST(:tenant_id AS uuid), :source, :csv, CAST(:result AS jsonb),
                     CAST(:readiness AS jsonb), CAST(:commit_gate AS jsonb),
                     :input_hash, :result_hash, CAST(:saved_at AS timestamptz))
                """
            ),
            {
                "run_id": run.run_id,
                "tenant_id": tenant_id,
                "source": run.source,
                "csv": run.csv,
                "result": _json_model(run.result),
                "readiness": _json_model(run.readiness),
                "commit_gate": _json_model(run.commit_gate),
                "input_hash": run.input_hash,
                "result_hash": run.result_hash,
                "saved_at": run.saved_at,
            },
        )
        commit_decision_id = run.commit_decision_id or f"{run.run_id}:staging"
        db.execute(
            text(
                """
                INSERT INTO fsma.inflow_workbench_commit_decisions
                    (decision_id, run_id, tenant_id, mode, allowed, export_eligible,
                     reasons, next_state, input_hash, result_hash, created_at)
                VALUES
                    (:decision_id, :run_id, CAST(:tenant_id AS uuid), :mode, :allowed,
                     :export_eligible, CAST(:reasons AS jsonb), :next_state,
                     :input_hash, :result_hash, CAST(:created_at AS timestamptz))
                ON CONFLICT (decision_id) DO NOTHING
                """
            ),
            {
                "decision_id": commit_decision_id,
                "run_id": run.run_id,
                "tenant_id": tenant_id,
                "mode": run.commit_gate.mode,
                "allowed": run.commit_gate.allowed,
                "export_eligible": run.commit_gate.export_eligible,
                "reasons": json.dumps(run.commit_gate.reasons),
                "next_state": run.commit_gate.next_state,
                "input_hash": run.input_hash,
                "result_hash": run.result_hash,
                "created_at": run.saved_at,
            },
        )
        for item in run.fix_queue:
            db.execute(
                text(
                    """
                    INSERT INTO fsma.inflow_workbench_fix_items
                        (item_id, run_id, tenant_id, title, owner, status, severity, impact, source, created_at, updated_at)
                    VALUES
                        (:item_id, :run_id, CAST(:tenant_id AS uuid), :title, :owner, :status, :severity,
                         :impact, :source, CAST(:created_at AS timestamptz), CAST(:updated_at AS timestamptz))
                    ON CONFLICT (item_id) DO UPDATE SET
                        owner = EXCLUDED.owner,
                        status = EXCLUDED.status,
                        severity = EXCLUDED.severity,
                        impact = EXCLUDED.impact,
                        source = EXCLUDED.source,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "item_id": item.id,
                    "run_id": run.run_id,
                    "tenant_id": tenant_id,
                    "title": item.title,
                    "owner": item.owner,
                    "status": item.status,
                    "severity": item.severity,
                    "impact": item.impact,
                    "source": item.source,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                },
            )
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def _db_get_run(run_id: str, tenant_id: str) -> Optional[WorkbenchRun]:
    tenant_uuid = _tenant_uuid(tenant_id)
    if not tenant_uuid:
        return None
    db = _db_session_for_tenant(tenant_uuid)
    if db is None:
        return None
    try:
        _set_tenant_context(db, tenant_uuid)
        row = db.execute(
            text(
                """
                SELECT run_id, tenant_id::text AS tenant_id, source, csv_text,
                       result_payload, readiness_payload, commit_gate_payload,
                       input_hash, result_hash, saved_at,
                       (
                           SELECT decision_id
                           FROM fsma.inflow_workbench_commit_decisions d
                           WHERE d.tenant_id = fsma.inflow_workbench_runs.tenant_id
                             AND d.run_id = fsma.inflow_workbench_runs.run_id
                           ORDER BY d.created_at DESC
                           LIMIT 1
                       ) AS commit_decision_id
                FROM fsma.inflow_workbench_runs
                WHERE tenant_id = CAST(:tenant_id AS uuid) AND run_id = :run_id
                """
            ),
            {"run_id": run_id, "tenant_id": tenant_uuid},
        ).mappings().first()
        if not row:
            return None
        fix_queue = _db_list_fix_queue(tenant_uuid, run_id=run_id) or []
        return _run_from_row(row, fix_queue)
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _db_list_fix_queue(tenant_id: str, run_id: Optional[str] = None) -> Optional[list[FixQueueItem]]:
    tenant_uuid = _tenant_uuid(tenant_id)
    if not tenant_uuid:
        return None
    db = _db_session_for_tenant(tenant_uuid)
    if db is None:
        return None
    try:
        _set_tenant_context(db, tenant_uuid)
        if run_id:
            rows = db.execute(
                text(
                    """
                    SELECT item_id, run_id, tenant_id::text AS tenant_id, title, owner,
                           status, severity, impact, source, created_at, updated_at
                    FROM fsma.inflow_workbench_fix_items
                    WHERE tenant_id = CAST(:tenant_id AS uuid) AND run_id = :run_id
                    ORDER BY created_at DESC
                    """
                ),
                {"tenant_id": tenant_uuid, "run_id": run_id},
            ).mappings().all()
        else:
            rows = db.execute(
                text(
                    """
                    SELECT item_id, run_id, tenant_id::text AS tenant_id, title, owner,
                           status, severity, impact, source, created_at, updated_at
                    FROM fsma.inflow_workbench_fix_items
                    WHERE tenant_id = CAST(:tenant_id AS uuid)
                    ORDER BY created_at DESC
                    """
                ),
                {"tenant_id": tenant_uuid},
            ).mappings().all()
        return [
            FixQueueItem(
                id=row["item_id"],
                run_id=row["run_id"],
                tenant_id=row["tenant_id"],
                title=row["title"],
                owner=row["owner"],
                status=row["status"],
                severity=row["severity"],
                impact=row["impact"],
                source=row["source"],
                created_at=_iso(row["created_at"]),
                updated_at=_iso(row["updated_at"]),
            )
            for row in rows
        ]
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _db_update_fix_item(item_id: str, tenant_id: str, payload: UpdateFixItemRequest) -> Optional[FixQueueItem]:
    tenant_uuid = _tenant_uuid(tenant_id)
    if not tenant_uuid:
        return None
    db = _db_session_for_tenant(tenant_uuid)
    if db is None:
        return None
    try:
        _set_tenant_context(db, tenant_uuid)
        db.execute(
            text(
                """
                UPDATE fsma.inflow_workbench_fix_items
                SET status = COALESCE(:status, status),
                    owner = COALESCE(:owner, owner),
                    updated_at = now()
                WHERE tenant_id = CAST(:tenant_id AS uuid) AND item_id = :item_id
                """
            ),
            {"item_id": item_id, "tenant_id": tenant_uuid, "status": payload.status, "owner": payload.owner},
        )
        db.commit()
        items = _db_list_fix_queue(tenant_uuid) or []
        return next((item for item in items if item.id == item_id), None)
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _db_readiness_snapshot(tenant_id: str) -> Optional[WorkbenchReadinessSnapshot]:
    tenant_uuid = _tenant_uuid(tenant_id)
    if not tenant_uuid:
        return None
    db = _db_session_for_tenant(tenant_uuid)
    if db is None:
        return None
    try:
        _set_tenant_context(db, tenant_uuid)
        row = db.execute(
            text(
                """
                SELECT run_id, tenant_id::text AS tenant_id, readiness_payload,
                       commit_gate_payload, saved_at, source
                FROM fsma.inflow_workbench_runs
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                ORDER BY saved_at DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_uuid},
        ).mappings().first()
        if not row:
            return WorkbenchReadinessSnapshot(tenant_id=tenant_uuid)
        unresolved = db.execute(
            text(
                """
                SELECT count(*) AS total
                FROM fsma.inflow_workbench_fix_items
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND status IN ('open', 'waiting')
                """
            ),
            {"tenant_id": tenant_uuid},
        ).scalar() or 0
        readiness = ReadinessSummary(**_json_value(row["readiness_payload"]))
        gate = CommitGateDecision(**_json_value(row["commit_gate_payload"]))
        return WorkbenchReadinessSnapshot(
            tenant_id=row["tenant_id"],
            score=readiness.score,
            label=readiness.label,
            run_id=row["run_id"],
            saved_at=_iso(row["saved_at"]),
            unresolved_fix_count=int(unresolved),
            export_eligible=gate.export_eligible,
            source=row["source"],
        )
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _file_readiness_snapshot(tenant_id: str) -> WorkbenchReadinessSnapshot:
    with _STORE_LOCK:
        store = _read_store()
    runs = [
        WorkbenchRun(**run)
        for run in store["runs"].values()
        if run.get("tenant_id") == tenant_id
    ]
    if not runs:
        return WorkbenchReadinessSnapshot(tenant_id=tenant_id)
    latest = max(runs, key=lambda run: run.saved_at)
    unresolved = len(
        [
            item
            for item in store["fix_queue"].values()
            if item.get("tenant_id") == tenant_id and item.get("status") in {"open", "waiting"}
        ]
    )
    return WorkbenchReadinessSnapshot(
        tenant_id=tenant_id,
        score=latest.readiness.score,
        label=latest.readiness.label,
        run_id=latest.run_id,
        saved_at=latest.saved_at,
        unresolved_fix_count=unresolved,
        export_eligible=latest.commit_gate.export_eligible,
        source=latest.source,
    )


def _result_counts(result: SandboxResponse) -> dict[str, int]:
    blocking = 1 if result.submission_blocked else 0
    duplicate_warning_count = len(result.duplicate_warnings or [])
    entity_warning_count = len(result.entity_warnings or [])
    return {
        "events": result.total_events,
        "compliant": result.compliant_events,
        "non_compliant": result.non_compliant_events,
        "kde_errors": result.total_kde_errors,
        "rule_failures": result.total_rule_failures,
        "warnings": duplicate_warning_count + entity_warning_count,
        "blocking": blocking,
    }


def build_readiness_summary(result: SandboxResponse) -> ReadinessSummary:
    counts = _result_counts(result)
    total_events = max(1, counts["events"])
    pass_rate = round((counts["compliant"] / total_events) * 100)
    kde_score = max(0, 100 - min(100, counts["kde_errors"] * 12))
    rule_score = max(0, 100 - min(100, counts["rule_failures"] * 18))
    duplicate_score = max(0, 100 - min(100, counts["warnings"] * 10))
    export_score = 100 if not result.submission_blocked and counts["non_compliant"] == 0 else max(0, 70 - counts["blocking"] * 35 - counts["non_compliant"] * 8)
    score = round(pass_rate * 0.3 + kde_score * 0.25 + rule_score * 0.25 + duplicate_score * 0.1 + export_score * 0.1)

    if score >= 90:
        label = "export ready after authenticated commit"
    elif score >= 75:
        label = "ready with warnings"
    elif score >= 50:
        label = "needs remediation"
    else:
        label = "blocked"

    return ReadinessSummary(
        score=max(0, min(100, score)),
        label=label,
        components=[
            ReadinessComponent(id="kde_completeness", label="KDE completeness", score=kde_score, detail=f"{counts['kde_errors']} KDE fixes found"),
            ReadinessComponent(id="rule_pass_rate", label="Rule pass rate", score=rule_score, detail=f"{counts['rule_failures']} rule failures found"),
            ReadinessComponent(id="cte_lifecycle", label="CTE lifecycle coverage", score=pass_rate, detail=f"{counts['compliant']} of {counts['events']} events compliant"),
            ReadinessComponent(id="duplicate_risk", label="Duplicate/idempotency risk", score=duplicate_score, detail=f"{counts['warnings']} duplicate or entity warnings"),
            ReadinessComponent(id="export_readiness", label="Export readiness", score=export_score, detail="Blocked submissions cannot support FDA export"),
        ],
    )


def build_fix_queue(result: SandboxResponse, tenant_id: str, run_id: str) -> list[FixQueueItem]:
    created_at = _now()
    items: list[FixQueueItem] = []

    for event in result.events:
        defects = list(event.kde_errors or [])
        defects.extend(
            defect.rule_title
            for defect in event.blocking_defects
            if defect.result == "fail"
        )
        if not defects and event.compliant:
            continue
        first_defect = defects[0] if defects else "failed rule evaluation"
        remediation = (
            event.blocking_defects[0].remediation
            if event.blocking_defects and event.blocking_defects[0].remediation
            else "Correct the source record and rerun preflight validation."
        )
        items.append(
            FixQueueItem(
                id=f"{run_id}:row:{event.event_index}",
                run_id=run_id,
                tenant_id=tenant_id,
                title=f"Row {event.event_index + 1} {event.cte_type} needs {first_defect}",
                owner="Source data owner",
                status="open" if result.submission_blocked else "waiting",
                severity="blocked" if result.submission_blocked or event.blocking_defects else "warning",
                impact=remediation,
                source=event.traceability_lot_code or f"row-{event.event_index + 1}",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    for index, reason in enumerate(result.blocking_reasons[:3]):
        items.append(
            FixQueueItem(
                id=f"{run_id}:blocking:{index}",
                run_id=run_id,
                tenant_id=tenant_id,
                title=reason,
                owner="Implementation",
                status="open",
                severity="blocked",
                impact="Commit gate stays closed until this blocker is resolved.",
                source="Sandbox evaluator",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    return items[:25]


def decide_commit_gate(payload: CommitGateRequest) -> CommitGateDecision:
    reasons: list[str] = []
    result = payload.result
    unresolved = payload.unresolved_fix_count
    if result:
        unresolved += result.total_kde_errors + result.total_rule_failures + result.non_compliant_events
        if result.submission_blocked:
            reasons.append("Sandbox evaluation has blocking rule failures.")
        if result.non_compliant_events:
            reasons.append(f"{result.non_compliant_events} events are not compliant.")

    if payload.mode in {"simulation", "preflight"}:
        return CommitGateDecision(
            mode=payload.mode,
            allowed=True,
            export_eligible=False,
            reasons=reasons or ["Allowed for sandbox diagnosis only; no production evidence is created."],
            next_state="staging" if payload.mode == "preflight" and not reasons else payload.mode,
        )

    if payload.mode == "staging":
        allowed = unresolved == 0
        return CommitGateDecision(
            mode=payload.mode,
            allowed=allowed,
            export_eligible=False,
            reasons=reasons or (["Ready to request authenticated production commit."] if allowed else ["Active fixes remain open."]),
            next_state="production_evidence" if allowed else "preflight",
        )

    if not payload.authenticated:
        reasons.append("Production evidence requires an authenticated session.")
    if not payload.persisted:
        reasons.append("Production evidence requires persisted tenant records.")
    if not payload.provenance_attached:
        reasons.append("Production evidence requires provenance metadata.")
    if unresolved:
        reasons.append(f"{unresolved} unresolved validation issues remain.")

    allowed = not reasons
    return CommitGateDecision(
        mode=payload.mode,
        allowed=allowed,
        export_eligible=allowed,
        reasons=reasons or ["Record is authenticated, persisted, provenance-tagged, and export-eligible."],
        next_state="production_evidence" if allowed else "preflight",
    )


@router.get("/scenarios", response_model=list[WorkbenchScenario])
async def list_scenarios(tenant_id: str = Query(default="default")) -> list[WorkbenchScenario]:
    db_scenarios = _db_list_scenarios(tenant_id)
    if db_scenarios is not None:
        return [WorkbenchScenario(**item) for item in BUILT_IN_SCENARIOS] + db_scenarios

    with _STORE_LOCK:
        store = _read_store()
    custom = [
        item
        for item in store["scenarios"]
        if item.get("tenant_id") in {tenant_id, "system"}
    ]
    return [WorkbenchScenario(**item) for item in [*BUILT_IN_SCENARIOS, *custom]]


@router.post("/scenarios", response_model=WorkbenchScenario)
async def create_scenario(payload: CreateScenarioRequest) -> WorkbenchScenario:
    tenant_id = _tenant_uuid(payload.tenant_id) or payload.tenant_id
    scenario = WorkbenchScenario(
        id=f"custom-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        name=payload.name,
        outcome=payload.outcome,
        records=f"{max(0, len(payload.csv.splitlines()) - 1)} CTE records",
        csv=payload.csv,
        created_at=_now(),
        built_in=False,
    )
    if _db_create_scenario(scenario):
        return scenario

    with _STORE_LOCK:
        store = _read_store()
        store["scenarios"].append(scenario.model_dump())
        _write_store(store)
    return scenario


@router.post("/readiness/preview", response_model=ReadinessSummary)
async def preview_readiness(result: SandboxResponse) -> ReadinessSummary:
    return build_readiness_summary(result)


@router.get("/readiness/summary", response_model=WorkbenchReadinessSnapshot)
async def readiness_summary(tenant_id: str = Query(default="default")) -> WorkbenchReadinessSnapshot:
    db_snapshot = _db_readiness_snapshot(tenant_id)
    if db_snapshot is not None:
        return db_snapshot
    return _file_readiness_snapshot(tenant_id)


@router.post("/commit-gate", response_model=CommitGateDecision)
async def commit_gate(payload: CommitGateRequest) -> CommitGateDecision:
    return decide_commit_gate(payload)


@router.post("/runs", response_model=WorkbenchRun)
async def save_run(payload: SaveRunRequest) -> WorkbenchRun:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    tenant_id = _tenant_uuid(payload.tenant_id) or payload.tenant_id
    readiness = build_readiness_summary(payload.result)
    fix_queue = build_fix_queue(payload.result, tenant_id, run_id)
    commit_gate_decision = decide_commit_gate(
        CommitGateRequest(
            mode="staging",
            tenant_id=tenant_id,
            result=payload.result,
            authenticated=False,
            persisted=False,
            provenance_attached=False,
            unresolved_fix_count=len([item for item in fix_queue if item.status in {"open", "waiting"}]),
        )
    )
    run = WorkbenchRun(
        run_id=run_id,
        tenant_id=tenant_id,
        source=payload.source,
        csv=payload.csv,
        result=payload.result,
        readiness=readiness,
        fix_queue=fix_queue,
        commit_gate=commit_gate_decision,
        saved_at=_now(),
        input_hash=_sha256_text(payload.csv),
        result_hash=_sha256_text(_json_model(payload.result)),
        commit_decision_id=f"{run_id}:staging",
    )

    if _db_save_run(run):
        return run

    with _STORE_LOCK:
        store = _read_store()
        store["runs"][run_id] = run.model_dump()
        for item in fix_queue:
            store["fix_queue"][item.id] = item.model_dump()
        _write_store(store)

    return run


@router.get("/runs/{run_id}", response_model=WorkbenchRun)
async def get_run(run_id: str, tenant_id: Optional[str] = Query(default=None)) -> WorkbenchRun:
    if tenant_id:
        db_run = _db_get_run(run_id, tenant_id)
        if db_run is not None:
            return db_run

    with _STORE_LOCK:
        store = _read_store()
    run = store["runs"].get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workbench run not found")
    return WorkbenchRun(**run)


@router.get("/fix-queue", response_model=list[FixQueueItem])
async def list_fix_queue(tenant_id: str = Query(default="default")) -> list[FixQueueItem]:
    db_items = _db_list_fix_queue(tenant_id)
    if db_items is not None:
        return db_items

    with _STORE_LOCK:
        store = _read_store()
    items = [
        FixQueueItem(**item)
        for item in store["fix_queue"].values()
        if item.get("tenant_id") == tenant_id
    ]
    return sorted(items, key=lambda item: item.created_at, reverse=True)


@router.patch("/fix-queue/{item_id}", response_model=FixQueueItem)
async def update_fix_item(
    item_id: str,
    payload: UpdateFixItemRequest,
    tenant_id: Optional[str] = Query(default=None),
) -> FixQueueItem:
    if tenant_id:
        db_item = _db_update_fix_item(item_id, tenant_id, payload)
        if db_item is not None:
            return db_item

    with _STORE_LOCK:
        store = _read_store()
        item = store["fix_queue"].get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Fix queue item not found")
        if payload.status:
            item["status"] = payload.status
        if payload.owner:
            item["owner"] = payload.owner
        item["updated_at"] = _now()
        store["fix_queue"][item_id] = item
        _write_store(store)
    return FixQueueItem(**item)
