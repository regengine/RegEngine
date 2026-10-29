"""Offline safeguards for the capped, explicitly opted-in review evaluation."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("jev_review_eval", ROOT / "scripts" / "jev_review_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def case():
    return {
        "id": "synthetic-1",
        "mode": "mode_b",
        "cohort": "original_controls",
        "state": {},
        "expected": {"label": "insufficient"},
        "evidence_flags": {},
    }


def test_order_variant_preserves_state_and_membership_and_hides_labels():
    plan = ev.build_plan([case()])
    assert len(plan) == 4
    base, reordered = plan[:2]
    assert base["payload"]["state"] == reordered["payload"]["state"]
    assert set(base["payload"]["questions"]) == set(reordered["payload"]["questions"])
    options = base["payload"]["questions"]["q3_evidence_polarity"]["criteria"]
    reversed_options = reordered["payload"]["questions"]["q3_evidence_polarity"]["criteria"]
    assert list(options) == list(reversed(reversed_options))
    assert "expected" not in base["payload"]
    assert "evidence_flags" not in base["payload"]


@pytest.mark.parametrize("identifier", ["../escape", "x/y", "", "a" * 81])
def test_rejects_unsafe_artifact_names(identifier):
    with pytest.raises(ValueError, match="identifier"):
        ev.build_plan([{**case(), "id": identifier}])


def test_missing_credential_sends_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: pytest.fail("network constructed"))
    with pytest.raises(RuntimeError, match="not configured"):
        ev.run(ev.build_plan([case()]), tmp_path, 1)


def test_budget_blocks_request_before_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")

    class NoNetwork:
        def open(self, *args, **kwargs):
            pytest.fail("Budget must stop the request")

    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: NoNetwork())
    with pytest.raises(RuntimeError, match="Budget exhausted"):
        ev.run(ev.build_plan([case()]), tmp_path, ev.RESERVATION / 2)


def test_timeout_retains_reservation_and_never_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")
    calls = []

    class Timeout:
        def open(self, request, **kwargs):
            calls.append(request.full_url)
            raise TimeoutError()

    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: Timeout())
    plan = ev.build_plan([case()])
    with pytest.raises(RuntimeError, match="no retry"):
        ev.run(plan, tmp_path, 1)
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["reserved_usd"] == ev.RESERVATION
    assert ledger["attempts"][0]["status"] == "failed_or_ambiguous"
    with pytest.raises(RuntimeError, match="replay prohibited"):
        ev.run(plan, tmp_path, 1)
    assert calls == [ev.ENDPOINT]
    assert "test-placeholder" not in json.dumps(ledger)


def test_redirect_cannot_forward_authentication():
    with pytest.raises(RuntimeError, match="redirects"):
        ev.NoRedirect().redirect_request(None, None, 302, "", {}, "https://untrusted.invalid")
