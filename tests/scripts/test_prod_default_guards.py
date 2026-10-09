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
    assert "regengine.co" not in text
    assert "--allow-production" in text


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
    # Allow-path: guard must pass (curl invoked). Do not require full smoke
    # success: the script has an unrelated unquoted-semicolon multipart bug
    # that exits 1 after the first fake curl calls.
    proc, curl_calls = _run_smoke_with_fake_curl(tmp_path, good_base)
    assert curl_calls >= 1, (
        f"expected fake curl for {good_base}, rc={proc.returncode} out={proc.stdout + proc.stderr!r}"
    )
    assert proc.returncode != 2


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


# --- phone_test_quickstart.sh: localhost default, production needs the flag,
# and the replay idempotency key is honored ---


def _make_fake_phone_bin(tmp_path: Path):
    """Fake curl that never touches the network; logs calls under tmp_path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    curl_log = tmp_path / "curl.log"
    (bin_dir / "curl").write_text(
        '#!/usr/bin/env bash\necho "curl-called" >> "$FAKE_CURL_LOG"\n'
        'printf \'{"accepted": 1, "rejected": 0}\\n__HTTP_STATUS__:200\'\nexit 0\n'
    )
    os.chmod(bin_dir / "curl", 0o755)
    return bin_dir, curl_log


def _run_phone_with_fake_curl(tmp_path: Path, env_overrides=None, extra_args=()):
    bin_dir, curl_log = _make_fake_phone_bin(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REGENGINE_API_KEY": uuid4().hex,
        "REGENGINE_TENANT_ID": str(uuid4()),
        "FAKE_CURL_LOG": str(curl_log),
    }
    env.pop("REGENGINE_ALLOW_PRODUCTION", None)
    env.pop("REGENGINE_API_BASE", None)
    env.pop("REGENGINE_IDEMPOTENCY_KEY", None)
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.run(
        ["bash", str(SCRIPTS / "phone_test_quickstart.sh"), *extra_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    curl_calls = 0
    if curl_log.exists():
        curl_calls = len([line for line in curl_log.read_text().splitlines() if line.strip()])
    return proc, curl_calls


def test_phone_script_defaults_to_localhost():
    text = (SCRIPTS / "phone_test_quickstart.sh").read_text()
    assert "REGENGINE_API_BASE:-http://localhost" in text
    assert "regengine.co" not in text
    assert "--allow-production" in text


def test_phone_script_honors_replay_idempotency_key():
    text = (SCRIPTS / "phone_test_quickstart.sh").read_text()
    assert "REGENGINE_IDEMPOTENCY_KEY" in text


def test_phone_script_refuses_production_without_flag(tmp_path):
    proc, curl_calls = _run_phone_with_fake_curl(tmp_path, {"REGENGINE_API_BASE": "https://regengine.co"})
    assert proc.returncode == 2
    assert curl_calls == 0
    assert "allow-production" in (proc.stdout + proc.stderr).lower()


def test_phone_script_allows_remote_with_explicit_opt_in(tmp_path):
    proc, curl_calls = _run_phone_with_fake_curl(
        tmp_path,
        {"REGENGINE_API_BASE": "https://regengine.co"},
        extra_args=("--allow-production",),
    )
    assert curl_calls == 1
    assert proc.returncode == 0
    assert "PASS: 1 event accepted" in proc.stdout


def test_phone_script_uses_localhost_default_target(tmp_path):
    proc, curl_calls = _run_phone_with_fake_curl(tmp_path)
    assert curl_calls == 1
    assert "POST http://localhost" in proc.stdout
    assert proc.returncode == 0


def test_phone_script_replays_with_given_idempotency_key(tmp_path):
    replay_key = str(uuid4())
    proc, curl_calls = _run_phone_with_fake_curl(tmp_path, {"REGENGINE_IDEMPOTENCY_KEY": replay_key})
    assert curl_calls == 1
    assert proc.returncode == 0
    assert f"Idempotency-Key: {replay_key}" in proc.stdout
    assert f"REGENGINE_IDEMPOTENCY_KEY={replay_key}" in proc.stdout


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
