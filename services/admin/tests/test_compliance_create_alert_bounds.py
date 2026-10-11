"""Regression tests: manual alert creation must reject absurd input.

``CreateAlertRequest.countdown_hours`` flowed straight into
``timedelta(hours=...)``. A huge value raised ``OverflowError``, which the
route's ``except`` tuple does not catch, producing an unhandled 500.
Negative values and blank titles stored nonsense that downstream
countdown and display logic never expected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from services.admin.app.compliance_routes import CreateAlertRequest


def test_rejects_huge_countdown_hours():
    """Would raise OverflowError inside timedelta(hours=...) -> 500."""
    with pytest.raises(ValidationError):
        CreateAlertRequest(title="Recall watch", countdown_hours=10**12)


def test_rejects_negative_countdown_hours():
    """A countdown ending in the past is never a valid manual alert."""
    with pytest.raises(ValidationError):
        CreateAlertRequest(title="Recall watch", countdown_hours=-5)


def test_rejects_blank_title():
    """Alerts with empty titles break the status widget and exports."""
    with pytest.raises(ValidationError):
        CreateAlertRequest(title="   ", countdown_hours=24)


def test_accepts_sane_alert():
    """Defaults (24h countdown, MEDIUM) still validate."""
    req = CreateAlertRequest(title="Recall watch")
    assert req.countdown_hours == 24
    assert req.severity == "MEDIUM"
