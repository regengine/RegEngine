"""Regression tests for the OTel collector telemetry safeguards.

The defect (audit finding): receivers accepted data with no
authentication, the traces sampler kept only 20 percent with no exception
for errors, and the log pipeline exported only to stdout.

The fix: the OTLP receiver requires bearer auth on both protocols, the
traces pipeline uses tail sampling that always keeps error traces while
keeping the 20 percent default for the rest, and the log pipeline ships
to a durable file exporter in addition to debug output. These tests fail
on the old config.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "infra" / "otel-collector-config.yaml"


def _config():
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_otlp_receiver_requires_auth_on_both_protocols():
    """Both OTLP protocols must reference a configured authenticator."""
    config = _config()
    protocols = config["receivers"]["otlp"]["protocols"]
    assert set(protocols) >= {"grpc", "http"}
    for name in ("grpc", "http"):
        authenticator = (protocols[name] or {}).get("auth", {}).get("authenticator")
        assert authenticator, f"otlp {name} protocol has no authenticator"
        assert authenticator in config.get("extensions", {}), (
            f"authenticator {authenticator!r} is not defined under extensions"
        )
        assert authenticator in config.get("service", {}).get("extensions", []), (
            f"authenticator {authenticator!r} is not enabled in service.extensions"
        )


def test_traces_pipeline_always_keeps_errors():
    """Error traces must be kept even though default sampling is 20 percent."""
    config = _config()
    traces = config["service"]["pipelines"]["traces"]
    processors = config["processors"]
    for name in traces["processors"]:
        sampler = processors.get(name) or {}
        if "sampling_percentage" in sampler:
            raise AssertionError(f"traces pipeline uses head sampling {name!r} with no exception for errors")
    assert "tail_sampling" in traces["processors"], "traces pipeline must use tail_sampling so errors can be kept"
    policies = processors["tail_sampling"].get("policies", [])
    error_policies = [
        p
        for p in policies
        if p.get("type") == "status_code" and "ERROR" in str(p.get("status_code", {}).get("status_codes", []))
    ]
    assert error_policies, "tail_sampling has no policy that always keeps errors"
    probabilistic = [p for p in policies if p.get("type") == "probabilistic"]
    assert probabilistic, "tail_sampling lost the default probabilistic policy"


def test_log_pipeline_persists_beyond_stdout():
    """The logs pipeline must export to durable storage, not only debug."""
    config = _config()
    exporters = config["service"]["pipelines"]["logs"]["exporters"]
    durable = [name for name in exporters if not name.startswith("debug")]
    assert durable, "logs pipeline exports only to debug (stdout)"
    for name in durable:
        assert name in config["exporters"], f"log exporter {name!r} is referenced but not defined"
        assert config["exporters"][name], f"log exporter {name!r} has no destination configured"
