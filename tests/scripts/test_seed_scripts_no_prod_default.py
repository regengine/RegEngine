"""Seed scripts must default to localhost, refuse prod without a flag, and never downgrade TLS."""

from __future__ import annotations

import importlib.util
import ssl
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
PROD_URL = "https://regengine-production.up.railway.app"

MODULES = ["seed_demo_ctes", "seed_founder_demo_ctes"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _source(name: str) -> str:
    return (SCRIPTS / f"{name}.py").read_text()


@pytest.mark.parametrize("module_name", MODULES)
def test_default_target_is_localhost(module_name, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    assert mod.is_local_target(mod.resolve_base())
    assert "localhost" in mod.resolve_base()


@pytest.mark.parametrize("module_name", MODULES)
def test_production_url_without_flag_is_refused(module_name, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base(PROD_URL)


@pytest.mark.parametrize("module_name", MODULES)
def test_production_url_via_env_without_flag_is_refused(module_name, monkeypatch):
    mod = _load(module_name)
    monkeypatch.setenv("SEED_BASE_URL", PROD_URL)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base()


@pytest.mark.parametrize("module_name", MODULES)
def test_explicit_production_url_with_flag_is_allowed(module_name, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    assert mod.resolve_base(PROD_URL, allow_production=True) == PROD_URL


@pytest.mark.parametrize("module_name", MODULES)
def test_no_tls_downgrade_path(module_name):
    src = _source(module_name)
    assert "CERT_NONE" not in src
    assert "verify=False" not in src
    assert "check_hostname = False" not in src
    assert "_ssl_ctx" not in src


@pytest.mark.parametrize("module_name", MODULES)
def test_ssl_context_verifies(module_name):
    mod = _load(module_name)
    ctx = mod.create_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_demo_script_key_comes_from_env_only(monkeypatch):
    mod = _load("seed_demo_ctes")
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    assert mod.get_api_key() == "secret-from-env"
    monkeypatch.delenv("REGENGINE_TENANT_API_KEY", raising=False)
    with pytest.raises(mod.UnsafeTargetError):
        mod.get_api_key()


def test_demo_script_rejects_key_as_cli_arg():
    mod = _load("seed_demo_ctes")
    parser = mod.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["http://localhost:8002", "some-api-key"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--api-key", "some-api-key"])


def test_founder_main_refuses_prod_without_flag(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    rc = mod.main(["--base", PROD_URL, "--dry-run"])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out


def test_demo_main_refuses_prod_without_flag(monkeypatch, capsys):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    rc = mod.main([PROD_URL])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out
