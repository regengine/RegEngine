from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
from threading import Lock
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.models import (
    AuditExportRequest,
    DriftResult,
    FairLendingAnalyzeRequest,
    GeneratedObligation,
    ModelChangeRequest,
    ModelRecordResponse,
    ModelRegistrationRequest,
    RegressionResult,
    ValidationRequest,
)
from app.security import utc_now


logger = logging.getLogger("compliance-api")

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


@dataclass
class ComplianceResultRecord:
    id: str
    tenant_id: str
    model_id: str
    analyzed_at: datetime
    min_dir: float
    regression_bias_flag: bool
    drift_flag: bool
    risk_level: str
    recommended_action: str
    regression_result: Optional[RegressionResult]
    drift_results: List[DriftResult]
    dir_results: List[dict]


@dataclass
class AuditArtifactRecord:
    id: str
    tenant_id: str
    model_id: str
    output_type: str
    version: int
    hash_sha256: str
    generated_at: datetime
    reviewer: str
    metadata: Dict[str, str]


class ComplianceStore:
    def __init__(self) -> None:
        self._lock = Lock()

        self._engine: Optional[Engine] = None
        self._db_enabled = False
        self._database_url = os.getenv("COMPLIANCE_DATABASE_URL") or os.getenv("DATABASE_URL")
        if self._database_url and self._database_url.startswith("postgresql://"):
            self._database_url = self._database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self._database_url and self._database_url.startswith("postgres://"):
            self._database_url = self._database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self._database_url and self._database_url.startswith("postgresql"):
            self._initialize_db_engine()

        self.regulations: List[dict] = []
        self.obligations: List[dict] = []
        self.controls: List[dict] = []
        self.tests: List[dict] = []

        self.models: Dict[tuple[str, str], ModelRecordResponse] = {}
        self.validations: List[dict] = []
        self.model_changes: List[dict] = []
        self.model_compliance_results: List[ComplianceResultRecord] = []
        self.audit_exports: List[AuditArtifactRecord] = []

        self.ckg_nodes: Dict[tuple[str, str, str], dict] = {}
        self.ckg_edges: List[dict] = []

    def _initialize_db_engine(self) -> None:
        try:
            self._engine = create_engine(self._database_url, future=True, pool_pre_ping=True)
            engine = self._engine
            if not engine:
                return
            with engine.begin() as connection:
                connection.execute(text("SELECT 1"))
            self._run_migration_if_needed()
            self._db_enabled = True
            logger.info("compliance_store_db_enabled")
        except SQLAlchemyError as error:
            logger.warning("compliance_store_db_disabled", extra={"error": str(error)})
            self._engine = None
            self._db_enabled = False

    def _run_migration_if_needed(self) -> None:
        engine = self._engine
        if not engine:
            return

        migration_file = Path(__file__).resolve().parents[1] / "migrations" / "V1__fair_lending_compliance_os.sql"
        if not migration_file.exists():
            return

        try:
            with engine.begin() as connection:
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_name = 'model_compliance_results'"
                    )
                ).scalar()
                if exists:
                    return

            sql = migration_file.read_text(encoding="utf-8")
            with engine.begin() as connection:
                connection.exec_driver_sql(sql)
            logger.info("compliance_store_migration_applied")
        except SQLAlchemyError as error:
            logger.warning("compliance_store_migration_failed", extra={"error": str(error)})

    def _set_tenant_context(self, connection: Connection, tenant_id: str) -> None:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    def _safe_json(self, payload: object) -> str:
        return json.dumps(payload, default=str)

    def _fetch_model_internal_id(self, connection: Connection, tenant_id: str, external_model_id: str) -> Optional[str]:
        self._set_tenant_context(connection, tenant_id)
        row = connection.execute(
            text(
                "SELECT id::text FROM models "
                "WHERE tenant_id = CAST(:tenant_id AS uuid) AND external_model_id = :external_model_id"
            ),
            {
                "tenant_id": tenant_id,
                "external_model_id": external_model_id,
            },
        ).mappings().first()
        if not row:
            return None
        return row["id"]

    def _ensure_model_internal_id(self, connection: Connection, tenant_id: str, external_model_id: str) -> str:
        model_id = self._fetch_model_internal_id(connection, tenant_id, external_model_id)
        if model_id:
            return model_id

        generated_id = str(uuid4())
        self._set_tenant_context(connection, tenant_id)
        connection.execute(
            text(
                "INSERT INTO models (id, tenant_id, external_model_id, name, version, owner, deployment_date, status, deployment_locked) "
                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :external_model_id, :name, :version, :owner, :deployment_date, 'active', false)"
            ),
            {
                "id": generated_id,
                "tenant_id": tenant_id,
                "external_model_id": external_model_id,
                "name": external_model_id,
                "version": "unknown",
                "owner": "system",
                "deployment_date": utc_now().date().isoformat(),
            },
        )
        return generated_id

    def _persist_node(self, tenant_id: str, node_type: str, node_key: str, attrs: dict) -> None:
        if not (self._db_enabled and self._engine):
            return
        try:
            with self._engine.begin() as connection:
                self._set_tenant_context(connection, tenant_id)
                connection.execute(
                    text(
                        "INSERT INTO ckg_nodes (tenant_id, node_type, node_key, attributes) "
                        "VALUES (CAST(:tenant_id AS uuid), :node_type, :node_key, CAST(:attributes AS jsonb)) "
                        "ON CONFLICT (tenant_id, node_type, node_key) "
                        "DO UPDATE SET attributes = ckg_nodes.attributes || EXCLUDED.attributes"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "node_type": node_type,
                        "node_key": node_key,
                        "attributes": self._safe_json(attrs),
                    },
                )
        except SQLAlchemyError as error:
            logger.warning("compliance_store_node_persist_failed", extra={"error": str(error)})

    def _persist_edge(
        self,
        tenant_id: str,
        source_type: str,
        source_key: str,
        relation: str,
        target_type: str,
        target_key: str,
    ) -> None:
        if not (self._db_enabled and self._engine):
            return
        try:
            with self._engine.begin() as connection:
                self._set_tenant_context(connection, tenant_id)
                connection.execute(
                    text(
                        "INSERT INTO ckg_edges "
                        "(tenant_id, source_node_type, source_node_key, edge_type, target_node_type, target_node_key, attributes) "
                        "VALUES (CAST(:tenant_id AS uuid), :source_node_type, :source_node_key, :edge_type, :target_node_type, :target_node_key, '{}'::jsonb)"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "source_node_type": source_type,
                        "source_node_key": source_key,
                        "edge_type": relation,
                        "target_node_type": target_type,
                        "target_node_key": target_key,
                    },
                )
        except SQLAlchemyError as error:
            logger.warning("compliance_store_edge_persist_failed", extra={"error": str(error)})

    def _node_key(self, tenant_id: str, node_type: str, node_id: str) -> tuple[str, str, str]:
        return (tenant_id, node_type, node_id)

    def _upsert_node(self, tenant_id: str, node_type: str, node_id: str, attrs: Optional[dict] = None) -> None:
        key = self._node_key(tenant_id, node_type, node_id)
        existing = self.ckg_nodes.get(key)
        attributes = attrs or {}
        payload = {
            "tenant_id": tenant_id,
            "type": node_type,
            "id": node_id,
            "attributes": attributes,
            "updated_at": utc_now().isoformat(),
        }
        if existing:
            existing["attributes"].update(payload["attributes"])
            existing["updated_at"] = payload["updated_at"]
        else:
            self.ckg_nodes[key] = payload

        self._persist_node(tenant_id, node_type, node_id, attributes)

    def _add_edge(
        self,
        tenant_id: str,
        source_type: str,
        source_id: str,
        relation: str,
        target_type: str,
        target_id: str,
    ) -> None:
        self.ckg_edges.append(
            {
                "id": str(uuid4()),
                "tenant_id": tenant_id,
                "source_type": source_type,
                "source_id": source_id,
                "relation": relation,
                "target_type": target_type,
                "target_id": target_id,
                "created_at": utc_now().isoformat(),
            }
        )
        self._persist_edge(tenant_id, source_type, source_id, relation, target_type, target_id)

    def save_regulatory_map(
        self,
        tenant_id: str,
        request: dict,
        generated_obligations: List[GeneratedObligation],
    ) -> str:
        with self._lock:
            regulation_id = str(uuid4())

            db_connection: Optional[Connection] = None
            db_tx = None
            if self._db_enabled and self._engine:
                try:
                    db_tx = self._engine.begin()
                    db_connection = db_tx.__enter__()
                    self._set_tenant_context(db_connection, tenant_id)
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_regulatory_db_begin_failed", extra={"error": str(error)})
                    db_connection = None
                    db_tx = None
            try:
                self.regulations.append(
                    {
                        "id": regulation_id,
                        "tenant_id": tenant_id,
                        "source_name": request["source_name"],
                        "citation": request["citation"],
                        "section": request["section"],
                        "text": request["text"],
                        "effective_date": request.get("effective_date"),
                        "created_at": utc_now().isoformat(),
                    }
                )

                if db_connection:
                    db_connection.execute(
                        text(
                            "INSERT INTO regulations "
                            "(id, tenant_id, source_name, citation, section, text, effective_date) "
                            "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :source_name, :citation, :section, :text, :effective_date)"
                        ),
                        {
                            "id": regulation_id,
                            "tenant_id": tenant_id,
                            "source_name": request["source_name"],
                            "citation": request["citation"],
                            "section": request["section"],
                            "text": request["text"],
                            "effective_date": request.get("effective_date"),
                        },
                    )

                self._upsert_node(
                    tenant_id,
                    "Regulation",
                    regulation_id,
                    {"citation": request["citation"], "section": request["section"]},
                )

                for obligation in generated_obligations:
                    obligation_id = str(uuid4())
                    self.obligations.append(
                        {
                            "id": obligation_id,
                            "tenant_id": tenant_id,
                            "regulation_id": regulation_id,
                            "obligation_text": obligation.obligation_text,
                            "risk_category": obligation.risk_category,
                        }
                    )

                    if db_connection:
                        db_connection.execute(
                            text(
                                "INSERT INTO obligations "
                                "(id, tenant_id, regulation_id, obligation_text, risk_category) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:regulation_id AS uuid), :obligation_text, :risk_category)"
                            ),
                            {
                                "id": obligation_id,
                                "tenant_id": tenant_id,
                                "regulation_id": regulation_id,
                                "obligation_text": obligation.obligation_text,
                                "risk_category": obligation.risk_category,
                            },
                        )

                    self._upsert_node(
                        tenant_id,
                        "Obligation",
                        obligation_id,
                        {
                            "risk_category": obligation.risk_category,
                            "obligation_text": obligation.obligation_text,
                        },
                    )
                    self._add_edge(tenant_id, "Regulation", regulation_id, "HAS_OBLIGATION", "Obligation", obligation_id)

                    for control in obligation.controls:
                        control_id = str(uuid4())
                        self.controls.append(
                            {
                                "id": control_id,
                                "tenant_id": tenant_id,
                                "obligation_id": obligation_id,
                                "control_name": control.control_name,
                                "control_type": control.control_type,
                                "frequency": control.frequency,
                                "threshold_value": control.threshold_value,
                            }
                        )

                        if db_connection:
                            db_connection.execute(
                                text(
                                    "INSERT INTO controls "
                                    "(id, tenant_id, obligation_id, control_name, control_type, frequency, threshold_value) "
                                    "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:obligation_id AS uuid), :control_name, :control_type, :frequency, :threshold_value)"
                                ),
                                {
                                    "id": control_id,
                                    "tenant_id": tenant_id,
                                    "obligation_id": obligation_id,
                                    "control_name": control.control_name,
                                    "control_type": control.control_type,
                                    "frequency": control.frequency,
                                    "threshold_value": control.threshold_value,
                                },
                            )

                        self._upsert_node(
                            tenant_id,
                            "Control",
                            control_id,
                            {
                                "control_name": control.control_name,
                                "control_type": control.control_type,
                                "frequency": control.frequency,
                            },
                        )
                        self._add_edge(tenant_id, "Obligation", obligation_id, "IMPLEMENTED_BY", "Control", control_id)

                        for test in control.tests:
                            test_id = str(uuid4())
                            self.tests.append(
                                {
                                    "id": test_id,
                                    "tenant_id": tenant_id,
                                    "control_id": control_id,
                                    "test_name": test.test_name,
                                    "methodology": test.methodology,
                                    "metric_definition": test.metric_definition,
                                    "failure_threshold": test.failure_threshold,
                                }
                            )

                            if db_connection:
                                db_connection.execute(
                                    text(
                                        "INSERT INTO tests "
                                        "(id, tenant_id, control_id, test_name, methodology, metric_definition, failure_threshold) "
                                        "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:control_id AS uuid), :test_name, :methodology, :metric_definition, :failure_threshold)"
                                    ),
                                    {
                                        "id": test_id,
                                        "tenant_id": tenant_id,
                                        "control_id": control_id,
                                        "test_name": test.test_name,
                                        "methodology": test.methodology,
                                        "metric_definition": test.metric_definition,
                                        "failure_threshold": test.failure_threshold,
                                    },
                                )

                            self._upsert_node(
                                tenant_id,
                                "Test",
                                test_id,
                                {
                                    "test_name": test.test_name,
                                    "methodology": test.methodology,
                                    "failure_threshold": test.failure_threshold,
                                },
                            )
                            self._add_edge(tenant_id, "Control", control_id, "VERIFIED_BY", "Test", test_id)

                return regulation_id
            finally:
                if db_tx is not None:
                    db_tx.__exit__(*sys.exc_info())

    def register_model(self, tenant_id: str, request: ModelRegistrationRequest) -> ModelRecordResponse:
        with self._lock:
            record = ModelRecordResponse(
                id=request.id,
                name=request.name,
                version=request.version,
                owner=request.owner,
                deployment_date=request.deployment_date,
                status=request.status,
                deployment_locked=False,
                lock_reason=None,
                last_fairness_result_at=None,
            )
            self.models[(tenant_id, request.id)] = record
            self._upsert_node(
                tenant_id,
                "Model",
                request.id,
                {
                    "name": request.name,
                    "version": request.version,
                    "owner": request.owner,
                    "status": request.status,
                },
            )

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        self._set_tenant_context(connection, tenant_id)
                        connection.execute(
                            text(
                                "INSERT INTO models "
                                "(id, tenant_id, external_model_id, name, version, owner, deployment_date, status, deployment_locked, lock_reason) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :external_model_id, :name, :version, :owner, :deployment_date, :status, false, NULL) "
                                "ON CONFLICT (tenant_id, external_model_id) "
                                "DO UPDATE SET name = EXCLUDED.name, version = EXCLUDED.version, owner = EXCLUDED.owner, "
                                "deployment_date = EXCLUDED.deployment_date, status = EXCLUDED.status"
                            ),
                            {
                                "id": str(uuid4()),
                                "tenant_id": tenant_id,
                                "external_model_id": request.id,
                                "name": request.name,
                                "version": request.version,
                                "owner": request.owner,
                                "deployment_date": request.deployment_date.isoformat(),
                                "status": request.status,
                            },
                        )
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_register_model_persist_failed", extra={"error": str(error)})

            return record

    def get_model(self, tenant_id: str, model_id: str) -> Optional[ModelRecordResponse]:
        cached = self.models.get((tenant_id, model_id))
        if cached:
            return cached

        if not (self._db_enabled and self._engine):
            return None

        try:
            with self._engine.begin() as connection:
                self._set_tenant_context(connection, tenant_id)
                row = connection.execute(
                    text(
                        "SELECT m.external_model_id, m.name, m.version, m.owner, m.deployment_date, m.status, "
                        "m.deployment_locked, m.lock_reason, "
                        "(SELECT max(r.analyzed_at) FROM model_compliance_results r WHERE r.model_id = m.id) AS last_fairness_result_at "
                        "FROM models m "
                        "WHERE m.tenant_id = CAST(:tenant_id AS uuid) AND m.external_model_id = :external_model_id "
                        "LIMIT 1"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "external_model_id": model_id,
                    },
                ).mappings().first()

            if not row:
                return None

            model = ModelRecordResponse(
                id=row["external_model_id"],
                name=row["name"],
                version=row["version"],
                owner=row["owner"],
                deployment_date=row["deployment_date"],
                status=row["status"],
                deployment_locked=row["deployment_locked"],
                lock_reason=row["lock_reason"],
                last_fairness_result_at=row["last_fairness_result_at"],
            )
            self.models[(tenant_id, model_id)] = model
            return model
        except SQLAlchemyError as error:
            logger.warning("compliance_store_get_model_failed", extra={"error": str(error)})
            return None

    def add_validation(self, tenant_id: str, model_id: str, request: ValidationRequest) -> dict:
        with self._lock:
            row = {
                "id": str(uuid4()),
                "tenant_id": tenant_id,
                "model_id": model_id,
                "validation_type": request.validation_type,
                "validator": request.validator,
                "date": request.date.isoformat(),
                "status": request.status,
                "notes": request.notes,
            }
            self.validations.append(row)

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        internal_model_id = self._ensure_model_internal_id(connection, tenant_id, model_id)
                        self._set_tenant_context(connection, tenant_id)
                        connection.execute(
                            text(
                                "INSERT INTO validations "
                                "(id, tenant_id, model_id, validation_type, validator, date, status, notes) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:model_id AS uuid), :validation_type, :validator, :date, :status, :notes)"
                            ),
                            {
                                "id": row["id"],
                                "tenant_id": tenant_id,
                                "model_id": internal_model_id,
                                "validation_type": request.validation_type,
                                "validator": request.validator,
                                "date": request.date.isoformat(),
                                "status": request.status,
                                "notes": request.notes,
                            },
                        )
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_validation_persist_failed", extra={"error": str(error)})

            return row

    def add_model_change(self, tenant_id: str, model_id: str, request: ModelChangeRequest) -> dict:
        with self._lock:
            requires_revalidation = request.change_type in {"retrain", "feature_added", "threshold_change"}
            row = {
                "id": str(uuid4()),
                "tenant_id": tenant_id,
                "model_id": model_id,
                "change_type": request.change_type,
                "description": request.description,
                "date": request.date.isoformat(),
                "requires_revalidation": requires_revalidation,
            }
            self.model_changes.append(row)

            model = self.models.get((tenant_id, model_id))
            if model and requires_revalidation:
                model.deployment_locked = True
                model.lock_reason = (
                    "Change requires fairness re-test before deployment (retrain/feature/threshold modification)."
                )

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        internal_model_id = self._ensure_model_internal_id(connection, tenant_id, model_id)
                        self._set_tenant_context(connection, tenant_id)
                        connection.execute(
                            text(
                                "INSERT INTO model_changes "
                                "(id, tenant_id, model_id, change_type, description, date, requires_revalidation) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:model_id AS uuid), :change_type, :description, :date, :requires_revalidation)"
                            ),
                            {
                                "id": row["id"],
                                "tenant_id": tenant_id,
                                "model_id": internal_model_id,
                                "change_type": request.change_type,
                                "description": request.description,
                                "date": request.date.isoformat(),
                                "requires_revalidation": requires_revalidation,
                            },
                        )
                        if requires_revalidation:
                            connection.execute(
                                text(
                                    "UPDATE models "
                                    "SET deployment_locked = true, "
                                    "lock_reason = :lock_reason "
                                    "WHERE id = CAST(:model_id AS uuid)"
                                ),
                                {
                                    "model_id": internal_model_id,
                                    "lock_reason": "Change requires fairness re-test before deployment.",
                                },
                            )
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_model_change_persist_failed", extra={"error": str(error)})

            return row

    def save_compliance_result(
        self,
        tenant_id: str,
        request: FairLendingAnalyzeRequest,
        analyzed_at: datetime,
        min_dir: float,
        dir_results: List[dict],
        regression_result: Optional[RegressionResult],
        drift_results: List[DriftResult],
        risk_level: str,
        recommended_action: str,
        regression_bias_flag: bool,
        drift_flag: bool,
    ) -> ComplianceResultRecord:
        with self._lock:
            result = ComplianceResultRecord(
                id=str(uuid4()),
                tenant_id=tenant_id,
                model_id=request.model_id,
                analyzed_at=analyzed_at,
                min_dir=min_dir,
                regression_bias_flag=regression_bias_flag,
                drift_flag=drift_flag,
                risk_level=risk_level,
                recommended_action=recommended_action,
                regression_result=regression_result,
                drift_results=drift_results,
                dir_results=dir_results,
            )
            self.model_compliance_results.append(result)

            model = self.models.get((tenant_id, request.model_id))
            if model:
                model.last_fairness_result_at = analyzed_at
                if min_dir >= 0.80 and not regression_bias_flag and not drift_flag:
                    model.deployment_locked = False
                    model.lock_reason = None

            self._upsert_node(
                tenant_id,
                "Model",
                request.model_id,
                {"protected_attribute": request.protected_attribute},
            )
            self._upsert_node(
                tenant_id,
                "Evidence",
                result.id,
                {
                    "risk_level": risk_level,
                    "analysis_type": ",".join(request.analysis_type),
                    "analyzed_at": analyzed_at.isoformat(),
                },
            )
            self._add_edge(tenant_id, "Evidence", result.id, "EVIDENCE_FOR_MODEL_VERSION", "Model", request.model_id)

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        internal_model_id = self._ensure_model_internal_id(connection, tenant_id, request.model_id)
                        self._set_tenant_context(connection, tenant_id)
                        connection.execute(
                            text(
                                "INSERT INTO model_compliance_results "
                                "(id, tenant_id, model_id, protected_attribute, min_dir, dir_results, regression_result, drift_results, "
                                "regression_bias_flag, drift_flag, risk_level, recommended_action, analyzed_at) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:model_id AS uuid), :protected_attribute, :min_dir, CAST(:dir_results AS jsonb), "
                                "CAST(:regression_result AS jsonb), CAST(:drift_results AS jsonb), :regression_bias_flag, :drift_flag, :risk_level, "
                                ":recommended_action, :analyzed_at)"
                            ),
                            {
                                "id": result.id,
                                "tenant_id": tenant_id,
                                "model_id": internal_model_id,
                                "protected_attribute": request.protected_attribute,
                                "min_dir": min_dir,
                                "dir_results": self._safe_json(dir_results),
                                "regression_result": self._safe_json(regression_result.model_dump()) if regression_result else "null",
                                "drift_results": self._safe_json([entry.model_dump() for entry in drift_results]),
                                "regression_bias_flag": regression_bias_flag,
                                "drift_flag": drift_flag,
                                "risk_level": risk_level,
                                "recommended_action": recommended_action,
                                "analyzed_at": analyzed_at,
                            },
                        )
                        connection.execute(
                            text(
                                "UPDATE models "
                                "SET deployment_locked = :deployment_locked, lock_reason = :lock_reason "
                                "WHERE id = CAST(:model_id AS uuid)"
                            ),
                            {
                                "deployment_locked": not (min_dir >= 0.80 and not regression_bias_flag and not drift_flag),
                                "lock_reason": None
                                if (min_dir >= 0.80 and not regression_bias_flag and not drift_flag)
                                else "Fair lending analysis indicates unresolved risk.",
                                "model_id": internal_model_id,
                            },
                        )
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_result_persist_failed", extra={"error": str(error)})

            return result

    def latest_compliance_result(self, tenant_id: str, model_id: str) -> Optional[ComplianceResultRecord]:
        if self._db_enabled and self._engine:
            try:
                with self._engine.begin() as connection:
                    self._set_tenant_context(connection, tenant_id)
                    row = connection.execute(
                        text(
                            "SELECT r.id::text AS id, m.external_model_id AS model_id, r.analyzed_at, r.min_dir, "
                            "r.regression_bias_flag, r.drift_flag, r.risk_level, r.recommended_action, "
                            "r.regression_result, r.drift_results, r.dir_results "
                            "FROM model_compliance_results r "
                            "JOIN models m ON m.id = r.model_id "
                            "WHERE m.tenant_id = CAST(:tenant_id AS uuid) AND m.external_model_id = :external_model_id "
                            "ORDER BY r.analyzed_at DESC LIMIT 1"
                        ),
                        {
                            "tenant_id": tenant_id,
                            "external_model_id": model_id,
                        },
                    ).mappings().first()

                if row:
                    regression_payload = row["regression_result"]
                    drift_payload = row["drift_results"]
                    dir_payload = row["dir_results"]

                    if isinstance(regression_payload, str):
                        regression_payload = json.loads(regression_payload)
                    if isinstance(drift_payload, str):
                        drift_payload = json.loads(drift_payload)
                    if isinstance(dir_payload, str):
                        dir_payload = json.loads(dir_payload)

                    regression_result = RegressionResult(**regression_payload) if regression_payload else None
                    drift_results = [DriftResult(**entry) for entry in (drift_payload or [])]

                    return ComplianceResultRecord(
                        id=row["id"],
                        tenant_id=tenant_id,
                        model_id=row["model_id"],
                        analyzed_at=row["analyzed_at"],
                        min_dir=float(row["min_dir"]),
                        regression_bias_flag=row["regression_bias_flag"],
                        drift_flag=row["drift_flag"],
                        risk_level=row["risk_level"],
                        recommended_action=row["recommended_action"],
                        regression_result=regression_result,
                        drift_results=drift_results,
                        dir_results=dir_payload or [],
                    )
            except (SQLAlchemyError, ValueError, TypeError, json.JSONDecodeError) as error:
                logger.warning("compliance_store_latest_result_query_failed", extra={"error": str(error)})

        candidates = [
            result
            for result in self.model_compliance_results
            if result.tenant_id == tenant_id and result.model_id == model_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.analyzed_at)

    def save_audit_artifact(
        self,
        tenant_id: str,
        request: AuditExportRequest,
        reviewer_token: str,
        hash_sha256: str,
        metadata: Dict[str, str],
    ) -> AuditArtifactRecord:
        with self._lock:
            version = 1
            existing_versions = [
                artifact
                for artifact in self.audit_exports
                if artifact.tenant_id == tenant_id
                and artifact.model_id == request.model_id
                and artifact.output_type == request.output_type
            ]
            if existing_versions:
                version = max(item.version for item in existing_versions) + 1

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        self._set_tenant_context(connection, tenant_id)
                        db_version = connection.execute(
                            text(
                                "SELECT coalesce(max(version), 0) + 1 AS next_version "
                                "FROM audit_exports a "
                                "JOIN models m ON m.id = a.model_id "
                                "WHERE a.tenant_id = CAST(:tenant_id AS uuid) "
                                "AND m.external_model_id = :external_model_id "
                                "AND a.output_type = :output_type"
                            ),
                            {
                                "tenant_id": tenant_id,
                                "external_model_id": request.model_id,
                                "output_type": request.output_type,
                            },
                        ).scalar()
                        if db_version:
                            version = int(db_version)
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_audit_version_query_failed", extra={"error": str(error)})

            artifact = AuditArtifactRecord(
                id=str(uuid4()),
                tenant_id=tenant_id,
                model_id=request.model_id,
                output_type=request.output_type,
                version=version,
                hash_sha256=hash_sha256,
                generated_at=utc_now(),
                reviewer=reviewer_token,
                metadata=metadata,
            )
            self.audit_exports.append(artifact)

            self._upsert_node(
                tenant_id,
                "Evidence",
                artifact.id,
                {
                    "output_type": request.output_type,
                    "hash_sha256": hash_sha256,
                    "version": str(version),
                },
            )
            self._upsert_node(tenant_id, "Reviewer", reviewer_token, {})
            self._add_edge(tenant_id, "Reviewer", reviewer_token, "SIGNED_OFF", "Evidence", artifact.id)
            self._add_edge(tenant_id, "Evidence", artifact.id, "EVIDENCE_FOR_MODEL_VERSION", "Model", request.model_id)

            if self._db_enabled and self._engine:
                try:
                    with self._engine.begin() as connection:
                        internal_model_id = self._ensure_model_internal_id(connection, tenant_id, request.model_id)
                        self._set_tenant_context(connection, tenant_id)
                        connection.execute(
                            text(
                                "INSERT INTO audit_exports "
                                "(id, tenant_id, model_id, output_type, version, immutable, hash_sha256, reviewer_sign_off, metadata, generated_at) "
                                "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:model_id AS uuid), :output_type, :version, true, :hash_sha256, :reviewer, CAST(:metadata AS jsonb), :generated_at)"
                            ),
                            {
                                "id": artifact.id,
                                "tenant_id": tenant_id,
                                "model_id": internal_model_id,
                                "output_type": request.output_type,
                                "version": version,
                                "hash_sha256": hash_sha256,
                                "reviewer": reviewer_token,
                                "metadata": self._safe_json(metadata),
                                "generated_at": artifact.generated_at,
                            },
                        )
                except SQLAlchemyError as error:
                    logger.warning("compliance_store_audit_persist_failed", extra={"error": str(error)})

            return artifact

    def ckg_summary(self, tenant_id: str) -> dict:
        if self._db_enabled and self._engine:
            try:
                with self._engine.begin() as connection:
                    self._set_tenant_context(connection, tenant_id)
                    node_rows = connection.execute(
                        text(
                            "SELECT node_type, count(*) AS count "
                            "FROM ckg_nodes WHERE tenant_id = CAST(:tenant_id AS uuid) "
                            "GROUP BY node_type"
                        ),
                        {"tenant_id": tenant_id},
                    ).mappings().all()

                    edge_count = connection.execute(
                        text("SELECT count(*) FROM ckg_edges WHERE tenant_id = CAST(:tenant_id AS uuid)"),
                        {"tenant_id": tenant_id},
                    ).scalar() or 0

                    latest_evidence_id = connection.execute(
                        text(
                            "SELECT node_key FROM ckg_nodes "
                            "WHERE tenant_id = CAST(:tenant_id AS uuid) AND node_type = 'Evidence' "
                            "ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"tenant_id": tenant_id},
                    ).scalar()

                return {
                    "nodes_by_type": {row["node_type"]: int(row["count"]) for row in node_rows},
                    "edge_count": int(edge_count),
                    "latest_evidence_id": latest_evidence_id,
                }
            except SQLAlchemyError as error:
                logger.warning("compliance_store_ckg_summary_failed", extra={"error": str(error)})

        node_counts: Dict[str, int] = {}
        latest_evidence: Optional[str] = None
        latest_seen = datetime.min.replace(tzinfo=utc_now().tzinfo)

        for node in self.ckg_nodes.values():
            if node["tenant_id"] != tenant_id:
                continue
            node_type = node["type"]
            node_counts[node_type] = node_counts.get(node_type, 0) + 1
            if node_type == "Evidence":
                updated_at = datetime.fromisoformat(node["updated_at"])
                if updated_at > latest_seen:
                    latest_seen = updated_at
                    latest_evidence = node["id"]

        edge_count = sum(1 for edge in self.ckg_edges if edge["tenant_id"] == tenant_id)
        return {
            "nodes_by_type": node_counts,
            "edge_count": edge_count,
            "latest_evidence_id": latest_evidence,
        }


STORE = ComplianceStore()
