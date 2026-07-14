"""Regression coverage for the packaged Python SDK."""

from __future__ import annotations

import ast
from pathlib import Path

import regengine
from regengine import RegEngineClient


def _setup_kwargs() -> dict[str, ast.AST]:
    setup_path = Path(__file__).resolve().parents[2] / "regengine" / "setup.py"
    module = ast.parse(setup_path.read_text(encoding="utf-8"))
    setup_call = next(
        node for node in ast.walk(module) if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"
    )
    return {kw.arg: kw.value for kw in setup_call.keywords}


def test_sdk_import_and_client_constructor() -> None:
    client = RegEngineClient(api_key="rge_test")
    try:
        assert client.api_key == "rge_test"  # pragma: allowlist secret
    finally:
        client._session.close()


def test_setup_declares_runtime_http_clients() -> None:
    install_requires = ast.literal_eval(_setup_kwargs()["install_requires"])
    assert any(requirement.startswith("httpx>=") for requirement in install_requires)
    assert any(requirement.startswith("requests>=") for requirement in install_requires)


def test_version_single_source_of_truth() -> None:
    """WS-11: __init__.py is the only place the version string lives.

    setup.py must NOT carry its own literal — it reads __version__ from
    __init__.py at build time (the pre-WS-11 state had three diverging
    strings: setup.py 0.1.0.dev0, CHANGELOG 1.1.0, verify_chain 1.0.0).
    """
    version_kwarg = _setup_kwargs()["version"]
    # A literal string here means someone reintroduced a second copy.
    assert not isinstance(version_kwarg, ast.Constant), (
        "setup.py hardcodes version= again — it must derive from "
        "regengine/__init__.py __version__ (WS-11 single source of truth)"
    )
    setup_text = (Path(__file__).resolve().parents[2] / "regengine" / "setup.py").read_text(encoding="utf-8")
    assert "__version__" in setup_text
    assert regengine.__version__.count(".") >= 2


def test_verifier_version_derives_from_package() -> None:
    """regengine-verify --version must report the package version, not a
    hardcoded string (pre-WS-11 it claimed 1.0.0 while the package was
    0.1.0.dev0)."""
    from regengine import verify_records

    assert verify_records._sdk_version() == regengine.__version__
