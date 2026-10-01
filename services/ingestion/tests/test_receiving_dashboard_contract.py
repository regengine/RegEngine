"""Validate the exact synthetic browser payload against the webhook owner."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.webhook_models import IngestEvent
from app.webhook_router_v2.validation import _validate_event_kdes


def test_receiving_dashboard_payload_passes_real_schema_and_required_kdes():
    fixture = Path(__file__).resolve().parents[3] / "frontend/src/__tests__/fixtures/receiving-event.json"
    payload = json.loads(fixture.read_text())
    # Keep this immutable wire fixture useful beyond the webhook replay window.
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    event = IngestEvent.model_validate(payload)
    assert _validate_event_kdes(event) == []
    event.kdes.pop("tlc_source_reference")
    assert any("tlc_source_reference" in error for error in _validate_event_kdes(event))
