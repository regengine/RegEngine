"""Regression tests for the OTel collector exporter TLS settings.

The defect: infra/otel-collector-config.yaml hardcoded
``tls: {insecure: true}`` on the Jaeger OTLP exporter, so every deploy
of that file sent traces over unverified TLS with no way to opt into
verification. The fix parameterizes the endpoint and the TLS mode with
a secure default. These tests fail on the hardcoded plaintext config.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "infra" / "otel-collector-config.yaml"


def _jaeger_exporter():
    config = yaml.safe_load(CONFIG_PATH.read_text())
    exporter = config["exporters"]["otlp/jaeger"]
    return exporter


def test_jaeger_exporter_is_not_hardcoded_insecure():
    """insecure must not be a hardcoded true."""
    tls = _jaeger_exporter().get("tls", {})
    assert tls.get("insecure") is not True, "otlp/jaeger exporter hardcodes tls.insecure: true"


def test_jaeger_insecure_defaults_to_secure():
    """When parameterized, the default expansion must be false."""
    insecure = _jaeger_exporter().get("tls", {}).get("insecure")
    if isinstance(insecure, str) and ":-" in insecure:
        default = insecure.rsplit(":-", 1)[-1].rstrip("} ").strip().lower()
        assert default == "false", f"insecure default is {default!r}, expected false"
    else:
        assert insecure is False, f"expected insecure false, got {insecure!r}"


def test_jaeger_endpoint_is_configurable():
    """The endpoint must be overridable without editing the file."""
    endpoint = str(_jaeger_exporter().get("endpoint", ""))
    assert "${env:" in endpoint, f"endpoint {endpoint!r} is hardcoded, production cannot point at a TLS backend"
