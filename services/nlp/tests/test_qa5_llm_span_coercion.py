"""QA5: the LLM bridge must not crash the batch on a bad span offset.

``_convert_llm_results_to_extractions`` accepts LLMExtraction models and
plain mappings (via ``_llm_field``). The mapping path bypasses pydantic,
so a non-numeric ``source_span_start`` (for example ``"abc"``) made
``int(span_start or 0)`` raise, killing the whole batch: every good
extraction in the message was dropped and the message went to the DLQ
instead of the review queue. A bad span is a provenance gap, not a batch
failure: the item is kept with offset 0.
"""

from __future__ import annotations

from services.nlp.app.consumer.conversion import (
    _convert_llm_results_to_extractions,
)

PROVISION = "The handler shall retain records for two years under this section."


def _item(**overrides):
    base = {
        "provision_text": PROVISION,
        "obligation_type": "REQUIREMENT",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_garbage_span_start_defaults_to_zero_instead_of_crashing():
    out = _convert_llm_results_to_extractions(
        [_item(source_span_start="abc")], "doc-1", "s3://b/k"
    )
    assert len(out) == 1
    assert out[0].source_offset == 0
    assert out[0].source_text == PROVISION


def test_none_span_start_still_zero():
    out = _convert_llm_results_to_extractions(
        [_item(source_span_start=None)], "doc-1", "s3://b/k"
    )
    assert len(out) == 1
    assert out[0].source_offset == 0


def test_numeric_span_start_preserved():
    out = _convert_llm_results_to_extractions(
        [_item(source_span_start=42)], "doc-1", "s3://b/k"
    )
    assert len(out) == 1
    assert out[0].source_offset == 42


def test_one_bad_item_does_not_drop_the_batch():
    out = _convert_llm_results_to_extractions(
        [
            _item(source_span_start="abc"),
            _item(source_span_start=7, obligation_type="PROHIBITION"),
        ],
        "doc-1",
        "s3://b/k",
    )
    assert len(out) == 2
