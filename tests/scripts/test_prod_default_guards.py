"""Guards that keep helper scripts pointed at localhost by default.

Every script that can write to a live environment must default to
localhost and refuse non-localhost targets unless the operator passes an
explicit --allow-production flag. Test API keys must not default to a
wildcard scope, and regctl list must never print full tenant API keys or
store them in a world-readable file (create shows the new key once so the
operator can record it, then list masks it).
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
    _sentinel = object()
    old = sys.modules.get(name, _sentinel)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if old is _sentinel:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old
    return module


def _load_seed_lifecycle(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "test-key")
    monkeypatch.delenv("REGENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    return _load("seed_lifecycle_test", SCRIPTS / "seed_lifecycle_test.py")


def _load_regctl():
    # tenant.py imports Neo4jClient at module top; stub it so the test does
    # not need a live Neo4j driver. Scoped stubs: never mutate a preexisting
    # module object, restore temporary entries before returning.
    stub_names = (
        "services",
        "services.graph",
        "services.graph.app",
        "services.graph.app.neo4j_utils",
    )
    with pytest.MonkeyPatch.context() as mp:
        created = set()
        for stub_name in stub_names:
            if stub_name not in sys.modules:
                mp.setitem(sys.modules, stub_name, types.ModuleType(stub_name))
                created.add(stub_name)
        target = "services.graph.app.neo4j_utils"
        if target in created:
            sys.modules[target].Neo4jClient = object
        else:
            existing = sys.modules[target]
            stub = types.ModuleType(target)
            stub.__dict__.update(existing.__dict__)
            stub.Neo4jClient = object
            mp.setitem(sys.modules, target, stub)
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
    assert "REGENGINE_API_BASE:-http://localhost" in text
    # The header documents a production example, but only together with
    # --allow-production; the default itself must stay localhost.
    assert "--allow-production" in text
    assert "--noproxy" in text
    assert "not a production R2 check" in text


def test_smoke_script_refuses_production_without_flag(tmp_path):
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, "https://regengine.co/api/ingestion")
    assert proc.returncode == 2
    assert curl_calls == 0
    assert "allow-production" in (proc.stdout + proc.stderr).lower()


# --- create_test_api_key.py: no wildcard scope by default ---


def test_api_key_default_scopes_are_not_wildcard(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@localhost:5432/regengine")
    module = _load("create_test_api_key", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = module._parse_args()
    assert "*" not in args.scopes
    assert "webhooks.ingest" in args.scopes


def test_api_key_default_scope_passes_ingest_permissions(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@localhost:5432/regengine")
    module = _load("create_test_api_key_scopes", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = module._parse_args()
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    perms = _load("shared_permissions_check", ROOT / "services" / "shared" / "permissions.py")
    assert perms.has_permission(scopes, "webhooks.ingest")


def test_api_key_still_guards_production(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@localhost:5432/regengine")
    module = _load("create_test_api_key_prod_guard", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = module._parse_args()
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="Refusing to mint"):
        module._guard_against_production(args, "postgresql://user@db.supabase.co:5432/postgres")


@pytest.mark.parametrize(
    "hosted_url",
    [
        "postgresql://user@db.supabase.co:5432/postgres",
        "postgresql://regengine@db.railway.app:5432/regengine",
        "postgresql://regengine@ep-cool-123.us-east-2.aws.neon.tech:5432/regengine",
        "postgresql://regengine@10.0.0.5:5432/regengine",
        "postgresql://regengine:regengine@localhost:5432/regengine?host=10.0.0.5",
        "postgresql://regengine:regengine@localhost:5432/regengine?hostaddr=10.0.0.5",
        "postgresql://regengine:regengine@localhost:5432/regengine?host=localhost,10.0.0.5",
    ],
)
def test_api_key_guard_refuses_hosted_urls_without_flag(monkeypatch, hosted_url):
    module = _load("create_test_api_key_hosted", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    args = module._parse_args()
    with pytest.raises(SystemExit, match="Refusing to mint"):
        module._guard_against_production(args, hosted_url)


@pytest.mark.parametrize(
    "local_url",
    [
        "postgresql://regengine:regengine@localhost:5432/regengine",
        "postgresql://regengine:regengine@127.0.0.1:5432/regengine",
        "postgresql://regengine:regengine@localhost:5432/regengine?sslmode=require",
        "postgresql://regengine:regengine@localhost:5432/regengine?host=localhost",
        "postgresql://regengine:regengine@postgres:5432/regengine",
    ],
)
def test_api_key_guard_allows_localhost_urls(monkeypatch, local_url):
    module = _load("create_test_api_key_local", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    args = module._parse_args()
    module._guard_against_production(args, local_url)


def test_compose_hostnames_count_as_local(monkeypatch):
    diag = _load("diag_db_compose", SCRIPTS / "utilities" / "diag_db.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    diag.ensure_local_database("postgresql://regengine:regengine@postgres:5432/regengine", False)
    chaos = _load("seed_chaos_data_compose", SCRIPTS / "seed_chaos_data.py")
    assert not chaos.is_production_target("postgresql://regengine:regengine@postgres:5432/regengine")
    assert not chaos.is_production_target("bolt://neo4j:7687")
    inflow = _load("verify_inflow_e2e_compose", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    inflow.ensure_local_database("postgresql://regengine:regengine@postgres:5432/regengine", False)


def test_api_key_guard_refuses_remote_redis_without_flag(monkeypatch):
    module = _load("create_test_api_key_redis", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://shared-redis.example:6379/0")
    args = module._parse_args()
    with pytest.raises(SystemExit, match="REDIS_URL"):
        module._guard_against_production(args, "postgresql://regengine@localhost:5432/regengine")
    args.allow_production = True
    module._guard_against_production(args, "postgresql://regengine@localhost:5432/regengine")


def test_api_key_billing_seed_skips_remote_redis(monkeypatch):
    module = _load("create_test_api_key_billing", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setenv("REDIS_URL", "redis://shared-redis.example:6379/0")
    note = module._seed_billing_status("11111111-1111-1111-1111-111111111111")
    assert "without --allow-production" in note


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


@pytest.mark.parametrize(
    "crafted_url",
    [
        "postgresql://regengine:regengine@localhost:5432/regengine?host=10.0.0.5",
        "postgresql://regengine:regengine@localhost:5432/regengine?hostaddr=10.0.0.5",
        "postgresql://regengine:regengine@localhost:5432/regengine?host=localhost,10.0.0.5",
    ],
)
def test_diag_db_refuses_query_host_override(monkeypatch, crafted_url):
    module = _load("diag_db_query_host", SCRIPTS / "utilities" / "diag_db.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    with pytest.raises(SystemExit, match="non-localhost"):
        module.ensure_local_database(crafted_url, False)
    module.ensure_local_database(crafted_url, True)


def test_diag_db_refuses_production_env_on_localhost(monkeypatch):
    module = _load("diag_db_env", SCRIPTS / "utilities" / "diag_db.py")
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="non-localhost"):
        module.ensure_local_database("postgresql://regengine@localhost:5432/regengine", False)


def test_chaos_seeder_refuses_query_host_override(monkeypatch):
    module = _load("seed_chaos_data_query_host", SCRIPTS / "seed_chaos_data.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    assert module.is_production_target("postgresql://regengine@localhost:5432/regengine?host=10.0.0.5")
    assert not module.is_production_target("postgresql://regengine@localhost:5432/regengine?sslmode=require")
    with pytest.raises(SystemExit):
        module.ensure_local_targets(
            "postgresql://regengine@localhost:5432/regengine?hostaddr=10.0.0.5",
            "bolt://localhost:7687",
            False,
        )


def test_inflow_verifier_refuses_query_host_override(monkeypatch):
    module = _load("verify_inflow_e2e_query_host", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    with pytest.raises(module.VerificationError, match="non-localhost"):
        module.ensure_local_database("postgresql://regengine@localhost:5432/regengine?host=10.0.0.5", False)
    with pytest.raises(module.VerificationError, match="non-localhost"):
        module.ensure_local_database("postgresql://regengine@localhost:5432/regengine?hostaddr=10.0.0.5", False)
    module.ensure_local_database("postgresql://regengine@localhost:5432/regengine?sslmode=require", False)


# --- entrypoint wiring: the guard must run inside main(), not just as a helper ---


def test_lifecycle_main_refuses_production_before_posting(monkeypatch):
    module = _load_seed_lifecycle(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--base-url", "https://regengine-production.up.railway.app"])
    assert excinfo.value.code == 2


def test_lifecycle_main_refuses_production_env_on_localhost(monkeypatch):
    module = _load_seed_lifecycle(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--base-url", "http://localhost:8000"])
    assert excinfo.value.code == 2


def test_chaos_main_refuses_remote_store_before_seeding(monkeypatch):
    module = _load("seed_chaos_data_main", SCRIPTS / "seed_chaos_data.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_chaos_data.py"])
    monkeypatch.setattr(module, "POSTGRES_URL", "postgresql://user@db.supabase.co:5432/postgres")
    monkeypatch.setattr(module, "NEO4J_URI", "bolt://localhost:7687")
    # Code 2 is the guard refusal; a seeding failure exits 1, success exits 0.
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 2


def test_chaos_cleanup_still_guarded(monkeypatch):
    module = _load("seed_chaos_data_cleanup", SCRIPTS / "seed_chaos_data.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_chaos_data.py", "--cleanup"])
    monkeypatch.setattr(module, "POSTGRES_URL", "postgresql://user@db.supabase.co:5432/postgres")
    monkeypatch.setattr(module, "NEO4J_URI", "bolt://localhost:7687")
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 2


def test_diag_main_refuses_remote_database(monkeypatch):
    module = _load("diag_db_main", SCRIPTS / "utilities" / "diag_db.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.setattr(module, "ADMIN_DATABASE_URL", "postgresql://user@db.supabase.co:5432/postgres")
    with pytest.raises(SystemExit, match="non-localhost"):
        module.main([])


def test_inflow_configure_environment_refuses_production(monkeypatch):
    module = _load("verify_inflow_e2e_env", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    args = module._parse_args(["--database-url", "postgresql://user@db.supabase.co:5432/postgres"])
    with pytest.raises(module.VerificationError, match="non-localhost"):
        module._configure_environment(args)
    assert os.getenv("DATABASE_URL") != "postgresql://user@db.supabase.co:5432/postgres"


def test_inflow_configure_environment_refuses_production_env_on_localhost(monkeypatch):
    module = _load("verify_inflow_e2e_env_local", SCRIPTS / "verify_inflow_to_regengine_e2e.py")
    monkeypatch.setenv("REGENGINE_ENV", "production")
    args = module._parse_args(["--database-url", "postgresql://regengine@localhost:5432/regengine"])
    with pytest.raises(module.VerificationError, match="non-localhost"):
        module._configure_environment(args)


def test_api_key_main_refuses_hosted_database(monkeypatch):
    import asyncio

    module = _load("create_test_api_key_main", SCRIPTS / "create_test_api_key.py")
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@db.railway.app:5432/regengine")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(SystemExit, match="Refusing to mint"):
        asyncio.run(module._main())


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
    assert not module.is_production_target("postgresql://regengine@localhost:5432/regengine")
    assert not module.is_production_target("bolt://localhost:7687")
    with pytest.raises(SystemExit):
        module.ensure_local_targets("postgresql://user@db.supabase.co:5432/postgres", "bolt://localhost:7687", False)
    module.ensure_local_targets(
        "postgresql://regengine@localhost:5432/regengine",
        "bolt://localhost:7687",
        False,
    )


# --- regctl: masked keys in list output, 0600 secret file ---


def test_regctl_masks_api_keys():
    module = _load_regctl()
    full = "example-api-key-for-masking-tests-1234"
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


def test_regctl_create_refuses_production_database(monkeypatch, tmp_path):
    module = _load_regctl()
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@db.railway.app:5432/regengine")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    with pytest.raises(SystemExit, match="non-localhost"):
        manager.create_tenant("Prod Co")
    assert not (tmp_path / ".tenants.db").exists()


def test_regctl_delete_refuses_production_database(monkeypatch, tmp_path):
    module = _load_regctl()
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine@db.railway.app:5432/regengine")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    with pytest.raises(SystemExit, match="non-localhost"):
        manager.delete_tenant(uuid4())


def test_regctl_create_allows_localhost_database(monkeypatch, tmp_path):
    module = _load_regctl()
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    module.ensure_local_database(os.environ["DATABASE_URL"], False)


def test_regctl_list_tightens_old_world_readable_file(tmp_path, capsys):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    full_key = f"sk_live_{uuid4().hex}"
    manager._save_tenant_record(uuid4(), "Masked Co", full_key)
    capsys.readouterr()
    os.chmod(manager.tenants_db_file, 0o644)
    manager.list_tenants()
    capsys.readouterr()
    assert stat.S_IMODE(os.stat(manager.tenants_db_file).st_mode) == 0o600


def test_regctl_save_refuses_symlink(tmp_path):
    module = _load_regctl()
    manager = module.TenantManager()
    target = tmp_path / "real.db"
    target.write_text("")
    link = tmp_path / ".tenants.db"
    link.symlink_to(target)
    manager.tenants_db_file = str(link)
    with pytest.raises(OSError):
        manager._save_tenant_record(uuid4(), "Symlink Co", f"sk_live_{uuid4().hex}")
    assert target.read_text() == ""


# --- smoke_test_ingest.sh: exact hostname guard (no glob bypass) ---

_FIXED_SMOKE_BODY = "/tmp/smoke_ingest_body"


def _make_fake_smoke_bin(tmp_path: Path):
    """Create fake curl/cat/rm that never touch the fixed body or network.

    Isolation is by design (no stat/read of the fixed path): fake curl
    ignores -o and only appends to run-owned logs, fake cat short-circuits
    the fixed path, fake rm no-ops for it. All logs live under tmp_path.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    curl_log = tmp_path / "curl.log"
    cat_log = tmp_path / "cat.log"
    rm_log = tmp_path / "rm.log"
    (bin_dir / "curl").write_text('#!/usr/bin/env bash\necho "curl $*" >> "$FAKE_CURL_LOG"\nprintf "200"\nexit 0\n')
    (bin_dir / "cat").write_text(
        "#!/usr/bin/env bash\n"
        'echo "cat $*" >> "$FAKE_CAT_LOG"\n'
        'for _a in "$@"; do\n'
        f'  if [[ "$_a" == "{_FIXED_SMOKE_BODY}" ]]; then\n'
        '    printf "fake-body"\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        'exec /bin/cat "$@"\n'
    )
    (bin_dir / "rm").write_text(
        "#!/usr/bin/env bash\n"
        'echo "rm $*" >> "$FAKE_RM_LOG"\n'
        'for _a in "$@"; do\n'
        f'  if [[ "$_a" == "{_FIXED_SMOKE_BODY}" ]]; then\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        'exec /bin/rm "$@"\n'
    )
    for name in ("curl", "cat", "rm"):
        os.chmod(bin_dir / name, 0o755)
    return bin_dir, curl_log, cat_log, rm_log


def _run_smoke_with_fake_curl(tmp_path: Path, api_base: str, extra_args=()):
    bin_dir, curl_log, cat_log, rm_log = _make_fake_smoke_bin(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REGENGINE_API_KEY": uuid4().hex,
        "REGENGINE_API_BASE": api_base,
        "FAKE_CURL_LOG": str(curl_log),
        "FAKE_CAT_LOG": str(cat_log),
        "FAKE_RM_LOG": str(rm_log),
    }
    env.pop("REGENGINE_ALLOW_PRODUCTION", None)
    proc = subprocess.run(
        ["bash", str(SCRIPTS / "smoke_test_ingest.sh"), *extra_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    curl_calls = 0
    if curl_log.exists():
        curl_calls = len([line for line in curl_log.read_text().splitlines() if line.strip()])
    return proc, curl_calls


@pytest.mark.parametrize(
    "bad_base",
    [
        "http://localhost.attacker.example",
        "http://localhost.attacker.example:8000",
        "http://127.0.0.1.attacker.example",
        "http://127.0.0.1@attacker.example",
        "http://localhost@attacker.example",
        "http://[::1]@attacker.example",
    ],
)
def test_smoke_script_rejects_lookalike_and_userinfo_without_flag(tmp_path, bad_base):
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, bad_base)
    assert proc.returncode == 2
    assert curl_calls == 0
    combined = (proc.stdout + proc.stderr).lower()
    assert "allow-production" in combined or "malformed" in combined


@pytest.mark.parametrize(
    "userinfo_base",
    [
        "http://127.0.0.1@attacker.example",
        "http://localhost@attacker.example",
        "http://[::1]@attacker.example",
        f"http://user:{uuid4().hex}@localhost:8000",
    ],
)
def test_smoke_script_rejects_userinfo_even_with_flag(tmp_path, userinfo_base):
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, userinfo_base, extra_args=("--allow-production",))
    assert proc.returncode == 2
    assert curl_calls == 0


@pytest.mark.parametrize(
    "bad_base",
    [
        "ftp://localhost:8000",
        "not-a-url",
        "http://",
        "http://[::1",
        "http://localhost:abc",
    ],
)
def test_smoke_script_rejects_malformed_even_with_flag(tmp_path, bad_base):
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, bad_base, extra_args=("--allow-production",))
    assert proc.returncode == 2
    assert curl_calls == 0


@pytest.mark.parametrize(
    "good_base",
    [
        "http://localhost:8000",
        "http://localhost:1234",
        "http://127.0.0.1:8000",
        "http://127.0.0.1",
        "http://[::1]:8000",
        "http://[::1]",
        "https://localhost:8000",
        "https://127.0.0.1:8443",
    ],
)
def test_smoke_script_allows_loopback_variants(tmp_path, good_base):
    # Allow-path: guard must pass (curl invoked) and the full run must end
    # in the localhost success line, never the production R2 line.
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, good_base)
    assert curl_calls >= 1, (
        f"expected fake curl for {good_base}, rc={proc.returncode} out={proc.stdout + proc.stderr!r}"
    )
    assert proc.returncode == 0
    assert "not a production R2 check" in proc.stdout
    assert "R2 wired and all endpoints functional" not in proc.stdout


@pytest.mark.parametrize(
    "remote_base",
    [
        "https://regengine.co/api/ingestion",
        "http://localhost.attacker.example",
    ],
)
def test_smoke_script_allows_remote_with_explicit_opt_in(tmp_path, remote_base):
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, remote_base, extra_args=("--allow-production",))
    assert curl_calls >= 1, (
        f"expected fake curl for {remote_base} with flag, rc={proc.returncode} out={proc.stdout + proc.stderr!r}"
    )
    assert proc.returncode != 2


# --- regctl loader isolation: no permanent stub pollution ---

_REGCTL_STUB_NAMES = (
    "services",
    "services.graph",
    "services.graph.app",
    "services.graph.app.neo4j_utils",
)


def test_load_restores_temporary_sys_modules_entry():
    probe_name = f"_tmp_load_restore_probe_{uuid4().hex}"
    assert probe_name not in sys.modules
    try:
        module = _load(probe_name, SCRIPTS / "create_test_api_key.py")
        assert hasattr(module, "_parse_args")
        assert probe_name not in sys.modules, "_load leaked temporary sys.modules entry"
    finally:
        sys.modules.pop(probe_name, None)


def test_load_regctl_preserves_preexisting_modules():
    saved = {}
    for name in _REGCTL_STUB_NAMES:
        if name in sys.modules:
            saved[name] = sys.modules[name]
    sentinel = type("RealNeo4jClient", (), {})()
    fakes = {name: types.ModuleType(name) for name in _REGCTL_STUB_NAMES}
    fakes["services.graph.app.neo4j_utils"].Neo4jClient = sentinel
    for name, mod in fakes.items():
        sys.modules[name] = mod
    regctl_saved = sys.modules.pop("regctl_tenant", None)
    try:
        module = _load_regctl()
        full = "example-api-key-for-masking-tests-1234"
        assert full not in module.mask_api_key(full)
        for name in _REGCTL_STUB_NAMES:
            assert sys.modules[name] is fakes[name], f"{name} identity not preserved"
        assert sys.modules["services.graph.app.neo4j_utils"].Neo4jClient is sentinel
    finally:
        for name in _REGCTL_STUB_NAMES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)
        sys.modules.pop("regctl_tenant", None)
        if regctl_saved is not None:
            sys.modules["regctl_tenant"] = regctl_saved


def test_load_regctl_restores_absent_stubs():
    watched = (*_REGCTL_STUB_NAMES, "regctl_tenant")
    saved = {}
    for name in watched:
        if name in sys.modules:
            saved[name] = sys.modules.pop(name)
    try:
        assert all(name not in sys.modules for name in watched)
        module = _load_regctl()
        assert hasattr(module, "mask_api_key")
        for name in watched:
            assert name not in sys.modules, f"{name} leaked into sys.modules"
    finally:
        for name in watched:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


# --- seed_lifecycle_test.py: redirects must not carry the API key ---


def test_lifecycle_post_does_not_follow_redirect(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(dict(self.headers))
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    target = HTTPServer(("127.0.0.1", 0), TargetHandler)
    thread_b = threading.Thread(target=target.serve_forever, daemon=True)
    thread_b.start()
    target_url = f"http://127.0.0.1:{target.server_port}/collect"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, *args):
            pass

    redirect = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread_a = threading.Thread(target=redirect.serve_forever, daemon=True)
    thread_a.start()
    try:
        module = _load_seed_lifecycle(monkeypatch)
        with pytest.raises(SystemExit):
            module.api_post(f"http://127.0.0.1:{redirect.server_port}/seed", {"ping": True})
    finally:
        redirect.shutdown()
        target.shutdown()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)
    assert received == []


def test_lifecycle_get_does_not_follow_redirect(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(dict(self.headers))
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    target = HTTPServer(("127.0.0.1", 0), TargetHandler)
    thread_b = threading.Thread(target=target.serve_forever, daemon=True)
    thread_b.start()
    target_url = f"http://127.0.0.1:{target.server_port}/collect"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, *args):
            pass

    redirect = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread_a = threading.Thread(target=redirect.serve_forever, daemon=True)
    thread_a.start()
    try:
        module = _load_seed_lifecycle(monkeypatch)
        with pytest.raises(SystemExit):
            module.api_get(f"http://127.0.0.1:{redirect.server_port}/seed")
    finally:
        redirect.shutdown()
        target.shutdown()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)
    assert received == []


# --- the guard suite itself must run in the required merge gate ---


def test_guard_suite_runs_in_required_backend_ci():
    text = (ROOT / ".github" / "workflows" / "backend-ci.yml").read_text()
    assert "tests/scripts/test_prod_default_guards.py" in text
