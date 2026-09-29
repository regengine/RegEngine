"""Chain diagnostics cannot attest an export from a different content store."""

from types import SimpleNamespace

import pytest
from app.fda_export.queries import _verify_chain_for_export
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.verification import CanonicalChainVerification


@pytest.fixture
def chain_result(monkeypatch):
    result = CanonicalChainVerification(
        valid=True,
        chain_length=3,
        errors=[],
        checked_at="2026-09-28T00:00:00+00:00",
        store="canonical",
    )
    monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "1")
    monkeypatch.setattr(CanonicalEventStore, "verify_chain_canonical", lambda *args: result)
    return result


def test_unknown_export_source_is_unverified_despite_valid_canonical_chain(chain_result):
    result = _verify_chain_for_export(None, None, "tenant")

    assert result.valid is False
    assert result.chain_length == 3
    assert result.checked_at == chain_result.checked_at
    assert any("exported content" in error.lower() for error in result.errors)
    assert chain_result.valid is True
    assert chain_result.errors == []


def test_legacy_export_cannot_borrow_canonical_content_verification(chain_result):
    result = _verify_chain_for_export(None, None, "tenant", source="legacy")

    assert result.valid is False
    assert any("exported content" in error.lower() for error in result.errors)


def test_declared_canonical_source_retains_canonical_content_verification(chain_result):
    result = _verify_chain_for_export(None, None, "tenant", source="canonical")

    assert result.valid is True
    assert result.chain_length == 3
    assert result.errors == []


def test_canonical_content_failure_is_preserved(chain_result):
    chain_result.valid = False
    chain_result.errors = ["Canonical content hash mismatch"]
    result = _verify_chain_for_export(None, None, "tenant", source="canonical")

    assert result.valid is False
    assert result.errors == ["Canonical content hash mismatch"]


@pytest.mark.parametrize("source", [None, "legacy", "canonical"])
def test_legacy_verifier_flag_never_upgrades_export_content_evidence(monkeypatch, source):
    monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "0")
    stored_hash_result = SimpleNamespace(valid=True, errors=[], chain_length=2, checked_at="checked")
    persistence = SimpleNamespace(verify_chain=lambda **kwargs: stored_hash_result)

    result = _verify_chain_for_export(persistence, None, "tenant", source=source)

    assert result.valid is False
    assert result.chain_length == 2
    assert any("exported content" in error.lower() for error in result.errors)
    assert stored_hash_result.valid is True


def test_existing_chain_errors_survive_unverified_export_scope(chain_result):
    chain_result.valid = False
    chain_result.errors = ["Sequence gap"]
    result = _verify_chain_for_export(None, None, "tenant")

    assert result.valid is False
    assert "Sequence gap" in result.errors
    assert len(result.errors) == 2
