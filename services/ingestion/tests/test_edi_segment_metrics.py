"""Regression tests for EDI segment-count metrics (#1171).

The cap on ``EDI_MAX_SEGMENTS`` is enforced at parse time
(``test_edi_ingestion_api.test_segment_cap_exceeded_returns_413``
covers the HTTP-layer behaviour). This file adds the observability
half of the issue: without per-parse metrics, an SRE can't tell
whether a cap bump request is driven by hostile payloads or
legitimate partner growth.

Metrics added:
- ``edi_segment_count{transaction_set}`` — histogram of successful
  parses.
- ``edi_segment_cap_rejected_total{transaction_set}`` — counter of
  parses rejected at the cap.

These tests lock in:
1. Both metrics exist at parser-module import time.
2. A successful parse observes on ``edi_segment_count`` with a useful
   transaction_set label.
3. A cap hit increments ``edi_segment_cap_rejected_total`` with a
   best-effort transaction_set label (``"unknown"`` is an
   acceptable value when the envelope is too malformed to peek).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Make the edi_ingestion package importable.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "app")
)


def _reset_parser_module(monkeypatch):
    """Force a clean reimport of the parser so the metric objects
    are the ones the test holds references to."""
    import importlib

    import edi_ingestion.parser as parser_mod  # type: ignore

    parser_mod = importlib.reload(parser_mod)
    return parser_mod


def _build_envelope(segment_count: int, transaction_set: str = "856") -> str:
    """Build a minimal X12 envelope with exactly `segment_count`
    padding segments beyond the ISA/GS/ST/SE/GE/IEA frame so tests
    can dial in the parsed-segment count.

    ISA uses the standard 105-char header so the parser's hard-coded
    element_sep=* / segment_term=~ apply.
    """
    isa = (
        "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
        "*260418*0000*U*00401*000000001*0*P*>~"
    )
    gs = f"GS*SH*SENDER*RECEIVER*20260418*0000*1*X*004010~"
    st = f"ST*{transaction_set}*0001~"
    # Padding N1 segments (name/identifier) — cheapest to emit.
    pads = "\n".join(f"N1*ST*PARTNER{i}~" for i in range(segment_count))
    se = f"SE*{segment_count + 2}*0001~"
    ge = "GE*1*1~"
    iea = "IEA*1*000000001~"
    return "\n".join([isa, gs, st, pads, se, ge, iea])


# ── 1. Module-level metric presence ────────────────────────────────────────


def test_metrics_exist_on_parser_module():
    """Both metrics must be importable from the parser module. A
    refactor that accidentally removes them (or renames them) will
    break SRE dashboards silently — this test fails loudly instead."""
    from edi_ingestion import parser  # type: ignore

    assert hasattr(parser, "EDI_SEGMENT_COUNT"), (
        "#1171: parser must expose EDI_SEGMENT_COUNT histogram"
    )
    assert hasattr(parser, "EDI_SEGMENT_CAP_REJECTED"), (
        "#1171: parser must expose EDI_SEGMENT_CAP_REJECTED counter"
    )
    # Metrics might be None if prometheus_client is absent; in that
    # case _METRICS_ENABLED must be False so the parser still works.
    if parser._METRICS_ENABLED:
        assert parser.EDI_SEGMENT_COUNT is not None
        assert parser.EDI_SEGMENT_CAP_REJECTED is not None


# ── 2. Successful-parse metric emission ────────────────────────────────────


def _histogram_sample_count(hist, label_value: str) -> float:
    """Sum the `_count` of a labelled histogram. Prometheus stores
    histograms as multiple samples; we pull the `_count` suffixed one."""
    for metric in hist.collect():
        for sample in metric.samples:
            if (
                sample.name.endswith("_count")
                and sample.labels.get("transaction_set") == label_value
            ):
                return sample.value
    return 0.0


def test_successful_parse_observes_segment_count():
    """#1171 observability: a clean parse must observe on the
    edi_segment_count histogram with the detected transaction_set."""
    from edi_ingestion import parser  # type: ignore

    if not parser._METRICS_ENABLED:
        pytest.skip("prometheus_client not available")

    before = _histogram_sample_count(parser.EDI_SEGMENT_COUNT, "856")

    envelope = _build_envelope(segment_count=5, transaction_set="856")
    segments = parser._parse_x12_segments(envelope)
    assert len(segments) >= 5  # sanity

    after = _histogram_sample_count(parser.EDI_SEGMENT_COUNT, "856")
    assert after == before + 1, (
        "#1171: successful parse must increment edi_segment_count "
        f"histogram for transaction_set=856; before={before} after={after}"
    )


# ── 3. Cap-rejection metric emission ───────────────────────────────────────


def _counter_value(counter, label_value: str) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.labels.get("transaction_set") == label_value:
                return sample.value
    return 0.0


def test_cap_rejection_increments_counter(monkeypatch):
    """#1171: when the parser rejects over-cap input, the rejection
    counter must increment with a best-effort transaction_set label so
    an SRE can build a dashboard that differentiates DoS attempts
    from legitimate partner-volume growth."""
    monkeypatch.setenv("EDI_MAX_SEGMENTS", "3")

    from edi_ingestion import parser  # type: ignore

    if not parser._METRICS_ENABLED:
        pytest.skip("prometheus_client not available")

    # Build an envelope with > 3 segments → definitely over the cap.
    envelope = _build_envelope(segment_count=20, transaction_set="856")

    # Capture the "856" AND "unknown" bucket — the peek might fall back.
    labels_to_check = ["856", "unknown", "unsupported"]
    before_totals = {
        lbl: _counter_value(parser.EDI_SEGMENT_CAP_REJECTED, lbl)
        for lbl in labels_to_check
    }

    with pytest.raises(HTTPException) as excinfo:
        parser._parse_x12_segments(envelope)
    assert excinfo.value.status_code == 413
    assert excinfo.value.detail["error"] == "segment_count_exceeded"

    after_totals = {
        lbl: _counter_value(parser.EDI_SEGMENT_CAP_REJECTED, lbl)
        for lbl in labels_to_check
    }

    # Exactly one of the labels must have incremented by 1 — and it
    # should be "856" (the transaction set in the envelope). We allow
    # "unknown" as a fallback if the peek heuristic misses, but the
    # total delta across our bucket set must be 1.
    delta = sum(after_totals[lbl] - before_totals[lbl] for lbl in labels_to_check)
    assert delta == 1, (
        f"#1171: cap rejection should increment the counter by 1; "
        f"before={before_totals} after={after_totals} delta={delta}"
    )


# ── 4. Peek heuristic resilience ───────────────────────────────────────────


def test_peek_transaction_set_handles_malformed_envelope():
    """The peek helper is called on REJECTED input — that input can be
    garbage by definition. It must never raise; only return a label
    string."""
    from edi_ingestion.parser import _peek_transaction_set  # type: ignore

    # Completely empty
    assert isinstance(_peek_transaction_set("", "*", "~"), str)
    # No ST segment
    assert _peek_transaction_set("ISA*00*foo~GS*SH~", "*", "~") == "unknown"
    # ST with unsupported transaction set — bounded label cardinality
    result = _peek_transaction_set("ST*99999~", "*", "~")
    assert result in {"unsupported", "unknown"}


def test_metrics_disabled_path_does_not_crash(monkeypatch):
    """If the metrics init failed (e.g. prometheus_client missing),
    the parser must still work — metrics are observability, not
    correctness. Simulate by flipping the module flag."""
    from edi_ingestion import parser  # type: ignore

    monkeypatch.setattr(parser, "_METRICS_ENABLED", False)

    envelope = _build_envelope(segment_count=5, transaction_set="856")
    # Should not raise.
    segments = parser._parse_x12_segments(envelope)
    assert len(segments) >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
