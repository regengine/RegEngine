"""Static regression guards for the reviewed v109 -> v114 migration chain."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"
V112_PATH = VERSIONS / "20260826_d8b2056471a7_v112_seed_obligations_security_definer.py"
V113_PATH = VERSIONS / "20260826_228275bfe7e1_v113_review_permissions.py"
V114_PATH = VERSIONS / "20260826_036afcef7299_v114_runtime_role_grants.py"
V112_MAIN_SHA256 = "21561246ef4b71d811957d5eff18255b98fc09118083cfd4e76b8a270ee8cd73"  # pragma: allowlist secret


def _literal(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name} does not declare {name}")


def test_reviewed_migration_chain_is_single_and_linear() -> None:
    expected = (
        (
            "20260802_51701aedee57_v109_team_roster_security_definer.py",
            "51701aedee57",
            "a43b0fb1edd0",  # pragma: allowlist secret
        ),
        (
            "20260815_6f8c2d1a4b90_v110_developer_profile_insert_policy.py",
            "6f8c2d1a4b90",  # pragma: allowlist secret
            "51701aedee57",
        ),
        (
            "20260826_df664d92adba_v111_public_controls_regulations_force_rls.py",
            "df664d92adba",
            "6f8c2d1a4b90",  # pragma: allowlist secret
        ),
        (
            V112_PATH.name,
            "d8b2056471a7",  # pragma: allowlist secret
            "df664d92adba",
        ),
        (
            V113_PATH.name,
            "228275bfe7e1",
            "d8b2056471a7",  # pragma: allowlist secret
        ),
        (
            V114_PATH.name,
            "036afcef7299",  # pragma: allowlist secret
            "228275bfe7e1",
        ),
    )

    for filename, revision, down_revision in expected:
        path = VERSIONS / filename
        assert path.is_file(), f"missing reviewed migration {filename}"
        assert _literal(path, "revision") == revision
        assert _literal(path, "down_revision") == down_revision

    assert not (VERSIONS / "20260803_6f4c2a9d8b17_v110_review_permissions.py").exists()
    assert not (VERSIONS / "20260803_b71d9e4c2a60_v111_runtime_role_grants.py").exists()


def test_v112_seed_function_is_byte_exact_and_v114_is_acl_only() -> None:
    v112_bytes = V112_PATH.read_bytes()
    assert hashlib.sha256(v112_bytes).hexdigest() == V112_MAIN_SHA256

    v114_source = V114_PATH.read_text(encoding="utf-8")
    v114_lower = v114_source.lower()
    assert "_SEED_FUNCTION" not in v114_source
    assert "create or replace function public.seed_obligations_for_tenant" not in v114_lower
    assert "create policy seed_definer_" not in v114_lower
    assert "_V112_SEED_POSTURE" in v114_source
    assert "search_path=public, fsma" in v114_source
    assert "pg_temp.seed_tpl_regulations" in v114_source
    assert (
        "GRANT EXECUTE ON FUNCTION public.seed_obligations_for_tenant(uuid)\n"
        "        TO regengine, regengine_sysadmin;"
    ) in v114_source


def test_unpublished_draft_artifacts_fail_closed_before_v114_cutover() -> None:
    v114_source = V114_PATH.read_text(encoding="utf-8")
    runner_source = (ROOT / "scripts" / "run-migrations.sh").read_text(encoding="utf-8")
    helper_source = (ROOT / "scripts" / "apply_runtime_role_cutover.py").read_text(
        encoding="utf-8"
    )

    for source in (v114_source, runner_source):
        assert "6f4c2a9d8b17" in source  # pragma: allowlist secret
        assert "b71d9e4c2a60" in source  # pragma: allowlist secret
        assert "trg_v111_" in source
        assert "seed_definer_" in source

    assert "CUTOVER_STATEMENTS = (\n    _UNPUBLISHED_DRAFT_GUARD," in v114_source
    assert "trg_v114_sysadmin_dml_" in v114_source
    assert "CREATE TRIGGER trg_v111_" not in v114_source
    assert "20260826_036afcef7299_v114_runtime_role_grants.py" in helper_source


def test_owned_migration_scripts_have_no_conflict_markers() -> None:
    for relative_path in ("scripts/init-postgres.sh", "scripts/run-migrations.sh"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "<<<<<<<" not in source
        assert ">>>>>>>" not in source
