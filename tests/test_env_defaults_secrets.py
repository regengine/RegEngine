"""Audit fix: tests/env_defaults.py must use random per-run secrets.

A hard-coded test credential that passes validation hides gaps production
would catch, so the auth defaults must be freshly generated, strong, and
never equal to the old fixed values.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_AUTH_KEYS = (
    "AUTH_SECRET_KEY",
    "AUTH_TEST_BYPASS_TOKEN",
    "INTERNAL_SERVICE_SECRET",
)

_OLD_WEAK_VALUES = {
    "dev_secret_key_change_me",
    "test-bypass-ci-only-not-for-production",
    "trusted-internal-v1",
}


def _load_fresh(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / "env_defaults.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_auth_defaults_are_not_hardcoded():
    module = _load_fresh("_env_defaults_under_test_not_hardcoded")
    for key in _AUTH_KEYS:
        assert module._DEFAULTS[key] not in _OLD_WEAK_VALUES


def test_auth_defaults_are_random_per_import():
    first = _load_fresh("_env_defaults_under_test_first")
    second = _load_fresh("_env_defaults_under_test_second")
    for key in _AUTH_KEYS:
        assert first._DEFAULTS[key] != second._DEFAULTS[key]


def test_auth_defaults_meet_strength_floor():
    module = _load_fresh("_env_defaults_under_test_strength")
    for key in _AUTH_KEYS:
        value = module._DEFAULTS[key]
        assert isinstance(value, str)
        assert len(value) >= 32
