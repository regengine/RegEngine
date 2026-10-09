"""Tests for scripts/ci/build_registry_seed.py.

Covers the medium audit finding: hardcoded personal paths, an unclosed file
handle that crashes raw on bad input, and short tokens bypassing redaction.
Each test fails on the pre-fix script and passes on the fixed one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "build_registry_seed.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_registry_seed", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["build_registry_seed"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _digest_with(*items: dict) -> dict:
    return {"byFile": {"tests/shared/test_example.py": list(items)}}


def _write_digest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload))
    return path


# Redaction ---------------------------------------------------------------


def test_short_hex_token_is_redacted() -> None:
    # A 16-char token passed straight through the old {32,64} pattern.
    token = "0123456789abcdef"
    assert token not in mod._short_hex(f"auth failed with key {token}")


def test_long_hex_still_redacted() -> None:
    token = "a" * 40
    redacted = mod._short_hex(f"sha {token} seen")
    assert token not in redacted
    assert "aaaaaaaa..." in redacted


def test_prefixed_secret_is_redacted() -> None:
    secret = "sk-test-abc123XYZ456"
    assert secret not in mod._short_hex(f"key {secret} leaked")


def test_plain_message_untouched() -> None:
    msg = "assert 404 == 200, response mismatch"
    assert mod._short_hex(msg) == msg


# Parameterized paths -----------------------------------------------------


def test_main_accepts_digest_and_out_args(tmp_path: Path, capsys) -> None:
    digest = _write_digest(
        tmp_path / "digest.json",
        _digest_with({"nodeid": "tests/shared/test_example.py::test_x", "msg": "boom"}),
    )
    out = tmp_path / "nested" / "seed.json"
    assert mod.main(["--digest", str(digest), "--out", str(out)]) == 0
    written = json.loads(out.read_text())
    assert written["entries"][0]["nodeid"] == "tests/shared/test_example.py::test_x"
    assert "wrote" in capsys.readouterr().out


def test_main_honors_workspace_env_vars(tmp_path: Path, monkeypatch) -> None:
    vector_ws = tmp_path / "vector"
    gate_ws = tmp_path / "gate"
    vector_ws.mkdir()
    _write_digest(
        vector_ws / "residual_digest.json",
        _digest_with({"nodeid": "tests/shared/test_example.py::test_x", "msg": "boom"}),
    )
    monkeypatch.setenv("VECTOR_WORKSPACE", str(vector_ws))
    monkeypatch.setenv("GATE_WORKSPACE", str(gate_ws))
    assert mod.main([]) == 0
    out = gate_ws / "artifacts" / "classification_registry.seed.json"
    assert json.loads(out.read_text())["entries"]


# Bad input handling ------------------------------------------------------


def test_missing_digest_exits_cleanly(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        mod.main(["--digest", str(tmp_path / "nope.json"), "--out", str(tmp_path / "o.json")])
    assert "not found" in str(exc.value)


def test_malformed_digest_exits_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit) as exc:
        mod.main(["--digest", str(bad), "--out", str(tmp_path / "o.json")])
    assert "invalid JSON" in str(exc.value)


def test_digest_without_byfile_exits_cleanly(tmp_path: Path) -> None:
    wrong = _write_digest(tmp_path / "wrong.json", {"entries": []})
    with pytest.raises(SystemExit) as exc:
        mod.main(["--digest", str(wrong), "--out", str(tmp_path / "o.json")])
    assert "byFile" in str(exc.value)
