"""Guards that keep helper scripts pointed at localhost by default.

Every script that can write to a live environment must default to
localhost and refuse non-localhost targets unless the operator passes an
explicit --allow-production flag. Test API keys must not default to a
wildcard scope, and regctl must never print full tenant API keys or store
them in a world-readable file.
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_seed_lifecycle(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "test-key")
    monkeypatch.delenv("REGENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    return _load("seed_lifecycle_test", SCRIPTS / "seed_lifecycle_test.py")


def _load_regctl():
    # tenant.py imports Neo4jClient at module top; stub it so the test does
    # not need a live Neo4j driver.
    for stub_name in (
        "services",
        "services.graph",
        "services.graph.app",
        "services.graph.app.neo4j_utils",
    ):
        sys.modules.setdefault(stub_name, types.ModuleType(stub_name))
    sys.modules["services.graph.app.neo4j_utils"].Neo4jClient = object
    return _load("regctl_tenant", SCRIPTS / "regctl" / "tenant.py")


# --- seed_lifecycle_test.py: localhost default, production needs the flag ---


def test_lifecycle_defaults_to_localhost(monkeypatch):
    module = _load_seed_lifecycle(monkeypatch)
    assert module.LOCAL_DEFAULT_BASE == "http://localhost:8000"
    assert module.BASE == "http://localhost:8000"
    assert "railway" not in module.BASE
    assert "regengine.co" not in module.BASE


def test_lifecycle_refuses_production_without_flag(monkeypatch, capsys):
    module = _load_seed_lifecycle(monkeypatch)
    assert module.is_production_base("https://regengine-production.up.railway.app")
    assert not module.is_production_base("http://localhost:8000")
    with pytest.raises(SystemExit):
        module.ensure_local_target("https://regengine-production.up.railway.app", False)
    capsys.readouterr()


def test_lifecycle_production_allowed_with_flag(monkeypatch):
    module = _load_seed_lifecycle(monkeypatch)
    module.ensure_local_target("https://regengine-production.up.railway.app", True)
    module.ensure_local_target("http://localhost:8000", False)


def test_lifecycle_main_parses_allow_production(monkeypatch):
    module = _load_seed_lifecycle(monkeypatch)
    args = module._parse_args(["--allow-production"])
    assert args.allow_production is True
    args = module._parse_args([])
    assert args.allow_production is False


# --- smoke_test_ingest.sh: localhost default, production needs the flag ---


def test_smoke_script_defaults_to_localhost():
    text = (SCRIPTS / "smoke_test_ingest.sh").read_text()
    assert 'REGENGINE_API_BASE:-http://localhost' in text
    assert "regengine.co" not in text
    assert "--allow-production" in text


def test_smoke_script_refuses_production_without_flag():
    proc = subprocess.run(
        ["bash", str(SCRIPTS / "smoke_test_ingest.sh")],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REGENGINE_API_KEY": "smoke-test-key",
            "REGENGINE_API_BASE": "https://regengine.co/api/ingestion",
        },
        timeout=30,
    )
    assert proc.returncode == 2
    assert "allow-production" in (proc.stdout + proc.stderr).lower()


# --- create_test_api_key.py: no wildcard scope by default ---


def test_api_key_default_scopes_are_not_wildcard(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@localhost:5432/regengine")
    module = _load("create_test_api_key", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = module._parse_args()
    assert "*" not in args.scopes
    assert "epcis.ingest" in args.scopes


def test_api_key_still_guards_production(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@localhost:5432/regengine")
    module = _load("create_test_api_key_prod_guard", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = module._parse_args()
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="Refusing to mint"):
        module._guard_against_production(args, "postgresql://user@db.supabase.co:5432/postgres")


# --- verify_inflow_to_regengine_e2e.py: database guard ---


def test_inflow_verifier_refuses_hosted_database(monkeypatch):
    module = _load("verify_inflow_e2e", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    with pytest.raises(module.VerificationError, match="non-localhost"):
        module.ensure_local_database("postgresql://user@db.supabase.co:5432/postgres", False)
    module.ensure_local_database("postgresql://regengine@localhost:5432/regengine", False)
    module.ensure_local_database("postgresql://user@db.supabase.co:5432/postgres", True)


def test_inflow_verifier_parses_allow_production():
    module = _load("verify_inflow_e2e_flag", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    assert module._parse_args(["--allow-production"]).allow_production is True
    assert module._parse_args([]).allow_production is False


# --- diag_db.py: database guard ---


def test_diag_db_refuses_hosted_database(monkeypatch):
    module = _load("diag_db", SCRIPTS / "utilities" / "diag_db.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    with pytest.raises(SystemExit, match="non-localhost"):
        module.ensure_local_database("postgresql://user@db.supabase.co:5432/postgres", False)
    module.ensure_local_database("postgresql://regengine@localhost:5432/regengine", False)
    assert module._parse_args(["--allow-production"]).allow_production is True


# --- seed_chaos_data.py: store guard ---


def test_chaos_seeder_refuses_remote_stores(monkeypatch):
    module = _load("seed_chaos_data", SCRIPTS / "seed_chaos_data.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    assert module.is_production_target("postgresql://user@db.supabase.co:5432/postgres")
    assert not module.is_production_target("postgresql://regengine:regengine@localhost:5432/regengine")
    assert not module.is_production_target("bolt://localhost:7687")
    with pytest.raises(SystemExit):
        module.ensure_local_targets(
            "postgresql://user@db.supabase.co:5432/postgres", "bolt://localhost:7687", False
        )
    module.ensure_local_targets(
        "postgresql://regengine:regengine@localhost:5432/regengine",
        "bolt://localhost:7687",
        False,
    )


# --- regctl: masked keys in list output, 0600 secret file ---


def test_regctl_masks_api_keys():
    module = _load_regctl()
    full = "sk_live_0123456789abcdef0123456789abcdef"
    masked = module.mask_api_key(full)
    assert full not in masked
    assert full[-4:] in masked
    assert module.mask_api_key("") == "***"


def test_regctl_list_never_prints_full_keys(tmp_path, capsys):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    full_key = f"sk_live_{uuid4().hex}"
    manager._save_tenant_record(uuid4(), "Masked Co", full_key)

    mode = stat.S_IMODE(os.stat(manager.tenants_db_file).st_mode)
    assert mode == 0o600

    manager.list_tenants()
    out = capsys.readouterr().out
    assert full_key not in out
    assert full_key[-4:] in out

    stored = [json.loads(line) for line in Path(manager.tenants_db_file).read_text().splitlines()]
    assert stored[0]["api_key"] == full_key
