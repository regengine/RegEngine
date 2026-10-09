"""Stress-test script metrics: no phantom admin key, throughput from wall time.

scripts/stress_test.py used to read ADMIN_KEY without ever sending it (phantom
auth coverage) and derived throughput from summed per-request latencies instead
of the wall-clock window. Both made the report misleading under concurrency.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "stress_test.py"

_SPEC = importlib.util.spec_from_file_location("_stress_test_under_test", SCRIPT)
assert _SPEC and _SPEC.loader
_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _module
_SPEC.loader.exec_module(_module)


def test_no_phantom_admin_key():
    """The script must not read an admin key it never sends."""
    source = SCRIPT.read_text()
    assert "ADMIN_KEY" not in source
    assert not hasattr(_module, "ADMIN_KEY")


def test_rps_uses_wall_time_not_summed_latencies():
    """Ten concurrent 0.5s requests in a 1s window measure 10 req/s."""
    result = _module.EndpointResult(
        name="svc/endpoint",
        method="GET",
        url="http://localhost:1/health",
        total_requests=10,
        success=10,
        latencies=[0.5] * 10,
        wall_seconds=1.0,
    )
    assert result.rps == 10.0


def test_rps_is_zero_without_a_wall_window():
    assert _module.EndpointResult(name="x", method="GET", url="u").rps == 0


def test_summary_throughput_uses_wall_time(capsys):
    """200 requests across 4s of wall time report about 50 req/s."""
    results = [
        _module.EndpointResult(
            name="svc/a",
            method="GET",
            url="u",
            total_requests=100,
            success=100,
            latencies=[0.1] * 100,
            wall_seconds=2.0,
        ),
        _module.EndpointResult(
            name="svc/b",
            method="GET",
            url="u",
            total_requests=100,
            success=100,
            latencies=[0.1] * 100,
            wall_seconds=2.0,
        ),
    ]
    assert _module.print_results(results) is True
    assert "~50 req/s" in capsys.readouterr().out
