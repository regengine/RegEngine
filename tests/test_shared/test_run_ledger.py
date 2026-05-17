"""Tests for ingestion run ledger read-model helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.run_ledger import verify_receipt_chain


NOW = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _receipt(
    *,
    sequence_num: int,
    receipt_hash: str,
    previous_receipt_hash: str | None,
) -> dict[str, object]:
    return {
        "receipt_id": f"receipt-{sequence_num}",
        "sequence_num": sequence_num,
        "state": "received",
        "occurred_at": NOW,
        "actor": "system",
        "request_id": "req-001",
        "canonical_event_id": None,
        "evidence_attachment_id": None,
        "rule_evaluation_id": None,
        "export_log_id": None,
        "metadata": {"row": sequence_num},
        "payload_hash": HASH_C,
        "previous_receipt_hash": previous_receipt_hash,
        "receipt_hash": receipt_hash,
        "created_at": NOW,
    }


def test_verify_receipt_chain_accepts_contiguous_hash_chain() -> None:
    result = verify_receipt_chain([
        _receipt(sequence_num=1, receipt_hash=HASH_A, previous_receipt_hash=None),
        _receipt(sequence_num=2, receipt_hash=HASH_B, previous_receipt_hash=HASH_A),
    ])

    assert result.valid is True
    assert result.chain_length == 2
    assert result.head_receipt_hash == HASH_B
    assert result.errors == []


def test_verify_receipt_chain_rejects_sequence_gaps() -> None:
    result = verify_receipt_chain([
        _receipt(sequence_num=1, receipt_hash=HASH_A, previous_receipt_hash=None),
        _receipt(sequence_num=3, receipt_hash=HASH_B, previous_receipt_hash=HASH_A),
    ])

    assert result.valid is False
    assert "expected sequence 2, got 3" in result.errors


def test_verify_receipt_chain_rejects_hash_breaks() -> None:
    result = verify_receipt_chain([
        _receipt(sequence_num=1, receipt_hash=HASH_A, previous_receipt_hash=None),
        _receipt(sequence_num=2, receipt_hash=HASH_B, previous_receipt_hash=HASH_C),
    ])

    assert result.valid is False
    assert "sequence 2 previous_receipt_hash does not match sequence 1 receipt_hash" in result.errors


def test_verify_receipt_chain_rejects_malformed_hashes() -> None:
    result = verify_receipt_chain([
        _receipt(sequence_num=1, receipt_hash="not-a-sha", previous_receipt_hash=None),
    ])

    assert result.valid is False
    assert "sequence 1 receipt_hash is not a SHA-256 hex string" in result.errors
