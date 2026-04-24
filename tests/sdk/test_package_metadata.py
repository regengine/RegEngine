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
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"
    )
    return {kw.arg: kw.value for kw in setup_call.keywords}


def test_sdk_import_and_client_constructor() -> None:
    client = RegEngineClient(api_key="rge_test")
    try:
        assert client.api_key == "rge_test"
    finally:
        client._session.close()


def test_setup_declares_runtime_http_clients() -> None:
    install_requires = ast.literal_eval(_setup_kwargs()["install_requires"])
    assert any(requirement.startswith("httpx>=") for requirement in install_requires)
    assert any(requirement.startswith("requests>=") for requirement in install_requires)


def test_package_version_matches_setup_version() -> None:
    setup_version = ast.literal_eval(_setup_kwargs()["version"])
    assert regengine.__version__ == setup_version
