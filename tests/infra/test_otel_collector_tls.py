"""Regression tests for the OTel collector exporter TLS settings.

The defect: infra/otel-collector-config.yaml hardcoded
``tls: {insecure: true}`` on the Jaeger OTLP exporter, so every deploy
of that file sent traces over plaintext with no way to opt into
verification. The fix parameterizes the endpoint and the TLS mode.
A later defect paired a plaintext default endpoint (``jaeger:4317``,
which has no TLS listener) with a TLS-verifying default
(``insecure`` false), so a default run dialed TLS at a plaintext
address and export failed. These tests pin the parameterized knobs
and require the two defaults to stay consistent with each other.
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


def _env_default(value, name):
    """Return the default from a ${env:NAME:-default} string, or the value."""
    if isinstance(value, str) and value.startswith("${env:") and ":-" in value:
        return value.rsplit(":-", 1)[-1].rstrip("} ").strip()
    return value


def test_jaeger_exporter_is_not_hardcoded_insecure():
    """insecure must not be a hardcoded true."""
    tls = _jaeger_exporter().get("tls", {})
    assert tls.get("insecure") is not True, "otlp/jaeger exporter hardcodes tls.insecure: true"


def test_jaeger_insecure_default_matches_default_endpoint():
    """The insecure default must be consistent with the endpoint default.

    The default endpoint is the plaintext Jaeger all-in-one
    (``jaeger:4317`` has no TLS listener), so the default TLS mode must
    be off. A TLS-verifying default against that address fails every
    default run. Production opts into TLS by setting both
    JAEGER_OTLP_ENDPOINT and JAEGER_OTLP_INSECURE=false together.
    """
    exporter = _jaeger_exporter()
    endpoint_default = str(_env_default(exporter.get("endpoint", ""), "JAEGER_OTLP_ENDPOINT"))
    insecure_default = str(_env_default(exporter.get("tls", {}).get("insecure"), "JAEGER_OTLP_INSECURE")).lower()
    assert endpoint_default == "jaeger:4317", f"unexpected endpoint default {endpoint_default!r}"
    assert insecure_default == "true", (
        f"insecure default is {insecure_default!r} against plaintext {endpoint_default!r}, default trace export fails"
    )


def test_jaeger_endpoint_is_configurable():
    """The endpoint must be overridable without editing the file."""
    endpoint = str(_jaeger_exporter().get("endpoint", ""))
    assert "${env:" in endpoint, f"endpoint {endpoint!r} is hardcoded, production cannot point at a TLS backend"


def test_jaeger_insecure_is_configurable():
    """The TLS mode must be overridable without editing the file."""
    insecure = _jaeger_exporter().get("tls", {}).get("insecure")
    assert isinstance(insecure, str) and insecure.startswith("${env:JAEGER_OTLP_INSECURE"), (
        f"tls.insecure {insecure!r} is hardcoded, production cannot opt into TLS verify"
    )
