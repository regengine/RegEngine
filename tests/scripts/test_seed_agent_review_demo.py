from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlunparse
from uuid import UUID

from shared.agent_artifacts import AgentArtifact
from shared.agent_task_bridge import build_agent_artifact_task_payload

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "seed_agent_review_demo.py"

EXPECTED_TYPES = {
    "field_mapping_suggestion",
    "identity_match_suggestion",
    "validation_explanation",
    "review_routing_suggestion",
    "export_readiness_summary",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_agent_review_demo", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_agent_review_demo"] = module
    spec.loader.exec_module(module)
    return module


def _postgres_url(
    *,
    username: str,
    credential: str,
    host: str,
    port: int,
    database: str,
) -> str:
    return urlunparse(
        (
            "postgresql",
            f"{username}:{credential}@{host}:{port}",
            f"/{database}",
            "",
            "",
            "",
        )
    )


def test_build_demo_artifacts_are_valid_deterministic_and_cover_all_payload_types() -> None:
    module = _load_module()

    first = module.build_demo_artifacts()
    second = module.build_demo_artifacts()

    assert [artifact.artifact_id for artifact in first] == [artifact.artifact_id for artifact in second]
    assert {artifact.artifact_type for artifact in first} == EXPECTED_TYPES
    assert len(first) == 5

    for artifact in first:
        validated = AgentArtifact.model_validate(artifact.model_dump(mode="json"))

        assert validated.model_dump(mode="json") == artifact.model_dump(mode="json")
        assert validated.tenant_id == module.DEFAULT_TENANT_ID
        assert validated.context.ingestion_run_id == module.DEFAULT_INGESTION_RUN_ID
        assert validated.context.source_hashes
        assert validated.context.evidence_ids or validated.context.canonical_event_ids
        assert validated.context.rule_id
        assert validated.context.rule_version
        assert validated.context.request_id == "synthetic-agent-review-demo"
        assert "Synthetic FSMA agent-review demo" in validated.suggestion


def test_build_demo_artifacts_accepts_explicit_tenant_and_ingestion_run_ids() -> None:
    module = _load_module()
    tenant_id = UUID("10000000-0000-4000-8000-000000000001")
    ingestion_run_id = UUID("20000000-0000-4000-8000-000000000001")

    artifacts = module.build_demo_artifacts(
        tenant_id=tenant_id,
        ingestion_run_id=ingestion_run_id,
    )

    assert {artifact.tenant_id for artifact in artifacts} == {tenant_id}
    assert {artifact.context.ingestion_run_id for artifact in artifacts} == {ingestion_run_id}


def test_demo_artifacts_build_valid_bridge_payloads_without_a_database() -> None:
    module = _load_module()

    payloads = [
        build_agent_artifact_task_payload(artifact.model_dump(mode="json"))
        for artifact in module.build_demo_artifacts()
    ]

    assert {payload.artifact_type for payload in payloads} == EXPECTED_TYPES
    assert all(payload.ingestion_run_id == module.DEFAULT_INGESTION_RUN_ID for payload in payloads)
    assert all(payload.source_hashes for payload in payloads)
    assert all(payload.artifact.artifact_id == payload.artifact_id for payload in payloads)


def test_seed_agent_review_demo_uses_bridge_helpers_idempotently(monkeypatch) -> None:
    module = _load_module()
    artifacts = module.build_demo_artifacts()[:2]
    existing_artifact_ids = {artifacts[0].artifact_id}
    existing_receipt_ids = {artifacts[1].artifact_id}
    tenant_contexts = []
    ensured_runs = []
    persisted = []
    receipts = []

    monkeypatch.setattr(
        module,
        "set_tenant_guc",
        lambda session, tenant_id: tenant_contexts.append((session, tenant_id)),
    )
    monkeypatch.setattr(
        module,
        "_ensure_ingestion_run",
        lambda session, artifact: ensured_runs.append((session, artifact.context.ingestion_run_id)),
    )
    monkeypatch.setattr(
        module,
        "_artifact_exists",
        lambda session, artifact: artifact.artifact_id in existing_artifact_ids,
    )
    monkeypatch.setattr(
        module,
        "_receipt_exists",
        lambda session, payload: payload.artifact_id in existing_receipt_ids,
    )
    monkeypatch.setattr(
        module,
        "persist_agent_artifact",
        lambda session, payload: persisted.append(payload.artifact_id),
    )
    monkeypatch.setattr(
        module,
        "append_agent_artifact_receipt",
        lambda session, payload: receipts.append(payload.artifact_id),
    )

    result = module.seed_agent_review_demo("session", artifacts)

    assert result.artifacts_created == 1
    assert result.artifacts_skipped == 1
    assert result.receipts_created == 1
    assert result.receipts_skipped == 1
    assert tenant_contexts == [("session", str(module.DEFAULT_TENANT_ID))]
    assert ensured_runs == [("session", module.DEFAULT_INGESTION_RUN_ID)]
    assert persisted == [artifacts[1].artifact_id]
    assert receipts == [artifacts[0].artifact_id]


def test_database_url_safety_guard_defaults_to_local_development_only() -> None:
    module = _load_module()

    assert module.is_safe_database_url_for_demo_seed(None) is False
    assert module.is_safe_database_url_for_demo_seed("sqlite:///:memory:") is True
    assert (
        module.is_safe_database_url_for_demo_seed(
            _postgres_url(
                username="regengine",
                credential="regengine",
                host="localhost",
                port=5432,
                database="regengine",
            )
        )
        is True
    )
    assert (
        module.is_safe_database_url_for_demo_seed(
            _postgres_url(
                username="regengine",
                credential="regengine",
                host="postgres",
                port=5432,
                database="regengine",
            )
        )
        is True
    )
    assert (
        module.is_safe_database_url_for_demo_seed(
            _postgres_url(
                username="postgres",
                credential="example-value",
                host="db.example.supabase.co",
                port=6543,
                database="postgres",
            )
        )
        is False
    )
    assert (
        module.is_safe_database_url_for_demo_seed(
            _postgres_url(
                username="postgres",
                credential="example-value",
                host="pooler.supabase.com",
                port=6543,
                database="postgres",
            )
        )
        is False
    )


def test_seed_script_has_no_builtin_database_url_default() -> None:
    module = _load_module()

    assert not hasattr(module, "DEFAULT_DEV_DATABASE_URL")

    source = Path(module.__file__).read_text()
    assert "DEFAULT_DEV_DATABASE_URL" not in source
    assert "@postgres:5432/regengine" not in source


def test_main_refuses_to_seed_without_an_explicit_database_url(monkeypatch, capsys) -> None:
    module = _load_module()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    for marker in ("RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "VERCEL_ENV", "VERCEL_URL"):
        monkeypatch.delenv(marker, raising=False)

    assert module.main([]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_main_accepts_database_url_flag(monkeypatch, capsys) -> None:
    module = _load_module()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(module, "seed_agent_review_demo", lambda session, artifacts: module.SeedResult())
    monkeypatch.setattr(module, "_environment_looks_production", lambda: False)
    monkeypatch.setattr(
        module,
        "is_safe_database_url_for_demo_seed",
        lambda database_url: database_url == "sqlite:///:memory:",
    )

    opened_urls: list[str] = []

    class _Session:
        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

        def get_bind(self):
            return None

    def _fake_open_seed_session(database_url: str):
        opened_urls.append(database_url)
        return _Session()

    monkeypatch.setattr(module, "_open_seed_session", _fake_open_seed_session)

    import shared.database

    def _forbidden_session_factory(*args, **kwargs):
        raise AssertionError("main must build the session from --database-url, not import-time SessionLocal")

    monkeypatch.setattr(shared.database, "SessionLocal", _forbidden_session_factory)

    assert module.main(["--database-url", "sqlite:///:memory:"]) == 0
    assert "Seeded FSMA agent-review demo artifacts" in capsys.readouterr().out
    assert "sqlite:///:memory:" in opened_urls


def test_open_seed_session_binds_to_given_url() -> None:
    module = _load_module()

    session = module._open_seed_session("sqlite:///:memory:")
    try:
        assert str(session.get_bind().url) == "sqlite:///:memory:"
    finally:
        bind = session.get_bind()
        session.close()
        bind.dispose()
