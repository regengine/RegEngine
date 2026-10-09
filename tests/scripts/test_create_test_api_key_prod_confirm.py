"""Production override for create_test_api_key.py needs interactive confirmation.

A single --allow-production flag used to bypass the production key-minting
guard silently. The guard must now require the operator to type an explicit
confirmation phrase from an interactive terminal.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "create_test_api_key.py"


def _load(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    spec = importlib.util.spec_from_file_location("create_test_api_key_confirm", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _args(**kwargs):
    base = {"allow_production": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


PROD_URL = "postgresql://user@db.supabase.co:5432/postgres"
LOCAL_URL = "postgresql://regengine@localhost:5432/regengine"


def test_local_target_passes_without_flag(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    module._guard_against_production(_args(), LOCAL_URL)


def test_production_refused_without_flag(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="Refusing to mint"):
        module._guard_against_production(_args(), PROD_URL)


def test_production_flag_requires_terminal(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="interactive confirmation"):
        module._guard_against_production(
            _args(allow_production=True),
            PROD_URL,
            _prompt=lambda _p: module.PRODUCTION_CONFIRM_PHRASE,
            _is_tty=lambda: False,
        )


def test_production_flag_wrong_phrase_aborts(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    with pytest.raises(SystemExit, match="Aborted"):
        module._guard_against_production(
            _args(allow_production=True),
            PROD_URL,
            _prompt=lambda _p: "yes",
            _is_tty=lambda: True,
        )


def test_production_flag_eof_aborts(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")

    def _boom(_p):
        raise EOFError

    with pytest.raises(SystemExit, match="Aborted"):
        module._guard_against_production(
            _args(allow_production=True),
            PROD_URL,
            _prompt=_boom,
            _is_tty=lambda: True,
        )


def test_production_flag_correct_phrase_proceeds(monkeypatch, capsys):
    module = _load(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    module._guard_against_production(
        _args(allow_production=True),
        PROD_URL,
        _prompt=lambda _p: module.PRODUCTION_CONFIRM_PHRASE,
        _is_tty=lambda: True,
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
