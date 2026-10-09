from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "utilities" / "test_redis_sessions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("test_redis_sessions", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()
_SOURCE = _SCRIPT.read_text(encoding="utf-8")


def test_no_hardcoded_password_in_source() -> None:
    assert "password123" not in _SOURCE


def test_credentials_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TEST_USER_EMAIL", "qa@example.com")
    monkeypatch.setenv("TEST_USER_PASSWORD", "s3cret-from-env")
    email, password = _MODULE.get_test_credentials()
    assert email == "qa@example.com"
    assert password == "s3cret-from-env"


def test_missing_password_aborts_before_login(monkeypatch) -> None:
    monkeypatch.delenv("TEST_USER_PASSWORD", raising=False)
    monkeypatch.setenv("TEST_USER_EMAIL", "qa@example.com")
    with patch.object(_MODULE, "run_redis_cmd", return_value="PONG"):
        with patch.object(_MODULE.requests, "post") as mock_post:
            assert _MODULE.test_redis_sessions() is False
            mock_post.assert_not_called()


def test_scan_keys_uses_scan_not_keys() -> None:
    with patch.object(_MODULE, "run_redis_cmd", return_value="a\nb") as mock_run:
        assert _MODULE.scan_keys("session:*") == ["a", "b"]
        sent_cmd = mock_run.call_args[0][0]
        assert "--scan" in sent_cmd
        assert "KEYS" not in sent_cmd
    assert "KEYS session" not in _SOURCE
    assert "KEYS user_sessions" not in _SOURCE
    assert "KEYS token_hash" not in _SOURCE


def test_run_redis_cmd_has_subprocess_timeout() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "PONG"
        _MODULE.run_redis_cmd("PING")
        assert "timeout" in mock_run.call_args[1]


def test_every_http_call_sets_a_timeout() -> None:
    tree = ast.parse(_SOURCE)
    http_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"get", "post"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
    ]
    assert len(http_calls) >= 4
    for node in http_calls:
        assert any(kw.arg == "timeout" for kw in node.keywords), ast.dump(node)
