"""Regression tests for the Grafana dashboard provisioning file.

The defect: infra/monitoring/grafana_dashboard.json hardcoded a top-level
``id`` of 1. Grafana treats that as an existing dashboard id, so importing
the file into a Grafana that already owns that id collides instead of
creating a new dashboard. Provisioned dashboards must carry ``id`` null so
Grafana assigns the id on import. These tests pin that.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "infra" / "monitoring" / "grafana_dashboard.json"


def _dashboard():
    return json.loads(DASHBOARD_PATH.read_text())


def test_dashboard_id_is_null_for_import():
    """Fails on the old file, which hardcoded a numeric dashboard id."""
    dashboard = _dashboard()
    assert "id" in dashboard, "dashboard must carry an explicit id key"
    assert dashboard["id"] is None, (
        f"dashboard id must be null so Grafana assigns one on import, got {dashboard['id']!r}"
    )


def test_dashboard_stays_valid_json_with_uid():
    dashboard = _dashboard()
    assert dashboard.get("uid"), "dashboard must keep a uid for provisioning"
    assert dashboard.get("title"), "dashboard must keep a title"
