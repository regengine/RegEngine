"""Regression tests for the EDI segment-count cap (#1171).

``services/ingestion/app/edi_ingestion/parser.py`` reads the full file,
strips newlines, and splits on the segment terminator. ``MAX_EDI_FILE_SIZE_BYTES``
bounds the *raw* upload, but not the list-length expansion after
``.split(segment_term)``. A crafted envelope with millions of tiny
segments could still drive the process OOM before any validation runs.

The parser's defence is ``EDI_MAX_SEGMENTS`` (default 100,000). These
tests lock in the boundary behaviour of that cap directly at the
parser level, independent of the FastAPI surface:

* ``MAX_EDI_SEGMENTS + 1`` segments → rejected with ``E_EDI_TOO_MANY_SEGMENTS``
  (error code embedded in the HTTPException detail).
* Exactly ``MAX_EDI_SEGMENTS`` segments → cap does not trip (the parse
  may fail for other reasons — that is *not* this test's concern).

Complementary coverage:
* ``test_edi_ingestion_api.test_segment_cap_exceeded_returns_413`` —
  HTTP-layer round trip.
* ``test_edi_segment_metrics`` — Prometheus metric emission on reject
  and success.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Make the edi_ingestion package importable the same way the existing
# parser/metrics tests do.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "app")
)


def _reload_parser():
    """Reimport the parser module after env changes so ``_max_segments``
    reads the patched value. ``_max_segments()`` re-reads the env on
    every call, so a reload is not strictly required, but it keeps the
    tests hermetic against any future module-level caching."""
    import edi_ingestion.parser as parser_mod  # type: ignore

    return importlib.reload(parser_mod)


def _build_envelope_with_raw_count(raw_count: int) -> str:
    """Build an X12-shaped string whose ``split('~')`` produces exactly
    ``raw_count`` entries (the value the parser's cap compares against).

    The point of this helper is NOT to produce a *validly structured*
    856/850 envelope — it is to control the length of the list the
    parser produces after the split, which is the only thing the cap
    guards. We use ``N1`` padding segments because the parser's
    segment-id filter accepts anything alphanumeric.

    An ISA header is emitted so that ``compact[3]`` (element
    separator) and ``compact[105]`` (segment terminator) land on the
    standard ``*`` / ``~`` pair the parser expects.

    Counting: the ISA header already ends in ``~``. Every N1 segment
    we append also ends in ``~``. The trailing ``~`` produces a final
    empty entry under ``split``. So for ``N`` N1 segments appended to
    the ISA, ``split('~')`` returns ``1 (ISA) + N (pads) + 1 (empty
    tail) = N + 2`` entries. To hit a target ``raw_count`` we need
    ``N = raw_count - 2`` padding segments.
    """
    if raw_count < 2:
        raise ValueError("raw_count must be >= 2 to produce ISA + trailing empty")

    # Standard 106-char ISA (ends with ``~`` at index 105).
    isa = (
        "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
        "*260418*0000*U*00401*000000001*0*P*>~"
    )
    assert len(isa) == 106, f"ISA must be 106 chars for separator detection, got {len(isa)}"

    n_pads = raw_count - 2
    pads = "".join(f"N1*ST*P{i}~" for i in range(n_pads))
    return isa + pads


@pytest.fixture()
def parser(monkeypatch):
    """Fresh parser module with a tiny cap (10) so we never need to
    build a multi-MB payload in-test. The parser reads the env on
    every call via ``_max_segments``, so this is cheap."""
    monkeypatch.setenv("EDI_MAX_SEGMENTS", "10")
    return _reload_parser()


def _raw_segment_count(envelope: str) -> int:
    """Mirror the parser's own measurement: count what ``split('~')``
    produces on the compacted content. The cap check runs against this
    exact number (*not* against the post-filter non-empty count)."""
    compact = envelope.replace("\n", "").replace("\r", "")
    return len(compact.split("~"))


# ── Reject path ────────────────────────────────────────────────────────────


def test_parser_rejects_file_with_more_than_MAX_EDI_SEGMENTS(parser):
    """An envelope whose raw-segment count is ``cap + 1`` must be
    rejected before it expands further. The rejection must carry the
    ``E_EDI_TOO_MANY_SEGMENTS``-equivalent error code so operators and
    downstream services can distinguish a DoS guard trip from any
    other validation failure."""
    cap = parser._max_segments()
    assert cap == 10, "fixture should patch cap to 10 for speed"

    # Build exactly cap + 1 raw segments — the first value the guard
    # must reject. Deliberately *not* cap + 100 so a rejection at this
    # exact boundary can only come from the `>` comparison firing.
    target_raw_count = cap + 1
    envelope = _build_envelope_with_raw_count(target_raw_count)

    # Sanity: confirm we actually built something over the cap before
    # claiming the parser rejected it for the right reason.
    assert _raw_segment_count(envelope) == cap + 1, (
        f"bogus test setup: raw count {_raw_segment_count(envelope)} "
        f"must equal cap+1 ({cap + 1})"
    )

    with pytest.raises(HTTPException) as excinfo:
        parser._parse_x12_segments(envelope)

    # The parser raises HTTPException(413) with a detail payload rather
    # than ValueError — that's the established pattern in this module
    # (see parser.py L137-150). The task's requested error code
    # ``E_EDI_TOO_MANY_SEGMENTS`` maps to ``segment_count_exceeded``
    # in the existing detail schema; we lock in both the status code
    # and the programmatic error tag.
    assert excinfo.value.status_code == 413, (
        "#1171: over-cap input must be rejected with 413 Payload Too Large"
    )
    detail = excinfo.value.detail
    assert isinstance(detail, dict), f"detail should be structured, got {type(detail)!r}"
    assert detail["error"] == "segment_count_exceeded", (
        "#1171: rejection must carry the programmatic error tag so "
        "callers can distinguish the cap guard from other 413s"
    )
    assert detail["cap"] == cap
    assert detail["count"] > cap, (
        f"detail.count ({detail['count']}) should report the observed "
        f"segment count above the cap ({cap}) for operator triage"
    )


def test_parser_rejects_far_above_cap(parser):
    """Sanity: well past the cap must still reject — not e.g. fall
    through a modular-arithmetic bug where cap*N wraps to 0. A parser
    that accepts 10_000 when the cap is 10 would pass the ``cap+1``
    test for the wrong reason; this catches that."""
    cap = parser._max_segments()
    envelope = _build_envelope_with_raw_count(cap * 100)

    with pytest.raises(HTTPException) as excinfo:
        parser._parse_x12_segments(envelope)
    assert excinfo.value.status_code == 413
    assert excinfo.value.detail["error"] == "segment_count_exceeded"


# ── Accept path ────────────────────────────────────────────────────────────


def test_parser_accepts_file_at_exact_limit(parser):
    """A raw-segment count of exactly ``cap`` must NOT trip the guard.

    The parse itself may or may not succeed (the envelope is
    deliberately minimal and lacks a valid GS/ST/SE chain), but any
    exception raised must NOT be the segment-cap exception. This is
    the important regression to lock in: an off-by-one that flips the
    comparison from ``>`` to ``>=`` would break every legitimate
    partner whose file happens to sit at the configured maximum.
    """
    cap = parser._max_segments()
    envelope = _build_envelope_with_raw_count(cap)

    assert _raw_segment_count(envelope) == cap, (
        "test setup: raw count must equal cap for the boundary check"
    )

    try:
        parser._parse_x12_segments(envelope)
    except HTTPException as exc:
        # Any HTTPException here must be something *other* than the
        # segment-cap guard — e.g. a downstream structural validator
        # tripping on our minimal envelope. The cap itself must not
        # fire at exactly ``cap``.
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        assert detail.get("error") != "segment_count_exceeded", (
            f"#1171 off-by-one: cap={cap} must NOT reject at exactly "
            f"cap segments. Got detail={detail!r}"
        )
    except Exception:
        # Non-HTTPException failures (ValueError, IndexError, ...) are
        # unrelated to the cap — the test only cares that the cap
        # guard does not fire. Re-raise so a real regression in an
        # unrelated code path still surfaces.
        raise


def test_parser_accepts_file_well_under_limit(parser):
    """Baseline: a tiny envelope well under the cap must parse without
    touching the guard. If this fails, the cap guard is firing
    spuriously and every test of the parser is at risk of false
    positives."""
    cap = parser._max_segments()
    assert cap >= 5, "test assumes fixture cap >= 5"

    envelope = _build_envelope_with_raw_count(3)

    # We don't assert on the returned segments' structure — that's
    # covered elsewhere. We only assert the cap did not fire.
    try:
        parser._parse_x12_segments(envelope)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        assert detail.get("error") != "segment_count_exceeded", (
            f"#1171: under-cap input must not trip the guard; detail={detail!r}"
        )


# ── Env / config surface ───────────────────────────────────────────────────


def test_cap_reads_env_var_each_call(monkeypatch):
    """The cap helper must re-read ``EDI_MAX_SEGMENTS`` on every call
    rather than caching at import time. Ops flipping the env var to
    relax the cap for a legitimate oversized partner shouldn't need
    a process restart."""
    import edi_ingestion.parser as parser_mod  # type: ignore

    monkeypatch.setenv("EDI_MAX_SEGMENTS", "7")
    assert parser_mod._max_segments() == 7

    monkeypatch.setenv("EDI_MAX_SEGMENTS", "42")
    assert parser_mod._max_segments() == 42


def test_cap_falls_back_to_default_on_garbage_env(monkeypatch):
    """A non-integer env value must NOT crash the parser at import or
    parse time — the cap falls back to the hard-coded default (100k).
    This keeps a typo in Helm config from taking ingestion down."""
    import edi_ingestion.parser as parser_mod  # type: ignore

    monkeypatch.setenv("EDI_MAX_SEGMENTS", "not-a-number")
    assert parser_mod._max_segments() == 100_000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
