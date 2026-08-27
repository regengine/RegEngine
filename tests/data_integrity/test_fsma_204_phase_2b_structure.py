"""Phase 2b: FSMA-204 golden-corpus obligation mapping (#2924).

What this file used to be
-------------------------
Two function bodies that were a single ``pass``.
``test_obligation_mapping_logic`` carried no marker at all, so it
contributed a green PASS to every run while asserting nothing;
``test_ingestion_pipeline_correctness`` was ``skipif(not
DOCKER_RUNNING)`` over a ``pass`` that would still have asserted
nothing had the gate ever opened. A class docstring advertising
"Verification of mapped obligations against the golden standard" sat
on top of both.

Proof they could not fail (mutation, reverted): breaking the
production mapping so that ``infer_obligation_type`` returned
PROHIBITED for every rule and ``extract_requirements`` returned no
obligations at all left this file at "1 passed, 1 skipped" — and at
"2 passed" with ``DOCKER_RUNNING=1``.

What it is now
--------------
``test_obligation_mapping_logic`` is implemented in-process (no Docker,
no network, no DB) against a pinned golden corpus of real 21 CFR Part 1
Subpart S rule prose, asserting the extracted-fact → compliance-
obligation mapping the product's verdicts depend on:

  * ``services/nlp/app/extractor.infer_obligation_type`` — the modality
    a rule sentence maps to (MANDATORY / PROHIBITED / CONDITIONAL).
  * ``services/nlp/app/extractor.extract_entities`` — the OBLIGATION
    facts carried out of the document, with that modality attached.
  * ``services/nlp/app/extractor.extract_fsma_facts`` — the compliance
    date, the fact an enforcement-posture change turns on.
  * ``services/ingestion/app/regulation_parser.extract_requirements``
    and ``RegulationParser._detect_jurisdiction`` — the ingestion-side
    half of the same mapping.

This is deliberately corpus-level, not unit-level: the modality rules
themselves are unit-tested against synthetic sentences in
``services/nlp/tests/test_obligation_negation_1299.py``. What is only
covered here is that they still produce the right answer on ACTUAL
regulation prose — the case a heuristic tweak can break while every
synthetic unit test stays green.

``test_ingestion_pipeline_correctness`` is genuinely not implemented.
It is now ``xfail(strict=True)`` over an explicit ``pytest.fail`` so
the gap reports as XFAIL — visible in CI output — instead of as a pass
or as a skip with an untrue reason. strict=True means that if someone
implements it, the unexpected pass turns the suite red and forces the
marker off.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure repo root and services/ are importable (mirrors the sibling
# test_fsma_204_verification_phase2b.py — this package has no conftest).
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.ingestion.app.regulation_parser import (  # noqa: E402
    RegulationParser,
    extract_requirements,
)
from services.nlp.app.extractor import (  # noqa: E402
    extract_entities,
    extract_fsma_facts,
    infer_obligation_type,
)

# Retained for the not-yet-implemented end-to-end test below.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
INGEST_SERVICE_URL = os.environ.get("INGEST_SERVICE_URL", "http://localhost:8001")


# ---------------------------------------------------------------------------
# Golden corpus — real 21 CFR Part 1 Subpart S (FSMA 204) rule prose.
#
# (id, rule text, expected obligation modality, expected negation flag)
#
# Every entry is a sentence the product must classify correctly for its
# compliance verdicts to mean anything: a MANDATORY recordkeeping duty
# read as PROHIBITED silently excuses a tenant from the rule, and a
# PROHIBITED exemption read as MANDATORY raises a finding against a
# tenant the rule does not reach.
# ---------------------------------------------------------------------------

GOLDEN_OBLIGATIONS = [
    (
        "records_retention",
        "You must maintain all records required under this subpart for 2 years from the date you created them.",
        "MANDATORY",
        False,
    ),
    (
        "recall_24_hour_sla",
        "When FDA requests it, you must make an electronic sortable spreadsheet available to FDA "
        "within 24 hours of the request.",
        "MANDATORY",
        False,
    ),
    (
        "traceability_lot_code",
        "You shall assign a traceability lot code to a food on the Food Traceability List when you "
        "initially pack a raw agricultural commodity.",
        "MANDATORY",
        False,
    ),
    (
        "farm_exemption",
        "A farm is exempt from the requirements of this subpart when it sells food directly to a consumer.",
        "PROHIBITED",
        True,
    ),
    (
        "receiver_carve_out",
        "You are not required to keep records of the traceability lot code source for food you receive "
        "from a person exempt under this subpart.",
        "PROHIBITED",
        True,
    ),
    (
        "conditional_recordkeeping",
        "Unless you are exempt under 1.1305, you must maintain traceability records for each critical tracking event.",
        "CONDITIONAL",
        False,
    ),
]

COMPLIANCE_DATE_TEXT = (
    "FDA has extended the compliance date for all persons subject to the recordkeeping requirements "
    "of this subpart to July 20, 2028."
)


class TestFSMA204GoldenCorpus:
    """
    Phase 2b: Golden Corpus Verification.

    This suite executes the "Happy Path" for FSMA 204 compliance data:
    1. Ingestion of a known FDA "Golden Corpus" document (PDF/HTML).
    2. NLP Extraction of Authority and Facts.
    3. Verification of mapped obligations against the golden standard.
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "NOT IMPLEMENTED (#2924): the submit/poll/verify-authority/verify-facts "
            "end-to-end flow has never had a body. The live end-to-end path is covered "
            "opt-in by tests/data_integrity/test_fsma_204_verification_phase2b.py::"
            "TestGoldenCorpusLiveSmoke (REGENGINE_LIVE_SMOKE=1); the in-process ingestion "
            "contract is covered by TestIngestionPipelineContract in the same file. "
            "strict=True: implementing this must turn the suite red until the marker goes."
        ),
    )
    def test_ingestion_pipeline_correctness(self):
        """
        End-to-End verification of the ingestion pipeline.

        Step 1: Submit Document
        Step 2: Poll for Completion
        Step 3: Verify Authority Created
        Step 4: Verify Facts Extracted
        """
        pytest.fail(f"not implemented — needs the full stack: {INGEST_SERVICE_URL} + {API_BASE_URL} + a database")

    def test_obligation_mapping_logic(self):
        """
        Verifies that extracted facts correctly map to Compliance Obligations.
        e.g. If 'RETENTION_PERIOD_YEARS' = 2, then Recordkeeping Obligation should reflect that.
        """
        # --- 1. Each golden rule maps to the right obligation modality -----
        mapped = {rule_id: infer_obligation_type(text) for rule_id, text, _, _ in GOLDEN_OBLIGATIONS}
        for rule_id, _text, expected_obligation, expected_negation in GOLDEN_OBLIGATIONS:
            assert mapped[rule_id]["obligation"] == expected_obligation, (
                f"{rule_id}: FSMA-204 rule text mapped to {mapped[rule_id]['obligation']}, "
                f"expected {expected_obligation}"
            )
            assert mapped[rule_id]["negation_detected"] is expected_negation, (
                f"{rule_id}: negation_detected={mapped[rule_id]['negation_detected']}, expected {expected_negation}"
            )

        # The corpus must actually discriminate — if every rule came back with
        # the same verdict the assertions above would be satisfiable by a
        # constant, which is exactly the defect class #2924 is about.
        assert {m["obligation"] for m in mapped.values()} == {"MANDATORY", "PROHIBITED", "CONDITIONAL"}

        # --- 2. Obligations survive extraction as facts, with modality -----
        # The recordkeeping duty and the 24-hour recall SLA are the two
        # obligations every FSMA-204 verdict rests on.
        retention_text = GOLDEN_OBLIGATIONS[0][1]
        recall_text = GOLDEN_OBLIGATIONS[1][1]
        entities = extract_entities(f"{retention_text} {recall_text}")
        obligations = [e for e in entities if e["type"] == "OBLIGATION"]

        assert len(obligations) == 2, f"expected one OBLIGATION fact per rule sentence, got {len(obligations)}"
        assert all(o["attrs"]["obligation"] == "MANDATORY" for o in obligations)
        assert all(o["attrs"]["negation_detected"] is False for o in obligations)
        # The retention duty keeps its "2 years" term, and the recall duty its
        # "24 hours" term — a span that dropped the number would map to an
        # obligation with no deadline.
        assert "2 years" in obligations[0]["text"]
        assert "24 hours" in obligations[1]["text"]

        # --- 3. The compliance date is extracted as a dated fact -----------
        facts = extract_fsma_facts(COMPLIANCE_DATE_TEXT)
        assert len(facts) == 1, f"expected exactly one REGULATORY_DATE fact, got {facts!r}"
        assert facts[0]["type"] == "REGULATORY_DATE"
        assert facts[0]["attrs"]["key"] == "Compliance Date"
        assert facts[0]["attrs"]["value"] == "July 20, 2028"
        # An undated sentence must NOT yield a compliance date.
        assert extract_fsma_facts("The rule was published on July 20, 2028 in the Federal Register.") == []

        # --- 4. Ingestion-side extraction agrees with the NLP side ---------
        corpus = " ".join(text for _id, text, _o, _n in GOLDEN_OBLIGATIONS)
        requirements = extract_requirements(corpus)
        assert any("must maintain all records" in r for r in requirements), (
            f"the recordkeeping obligation was not extracted as a requirement: {requirements!r}"
        )
        assert any("within 24 hours" in r for r in requirements), (
            f"the 24-hour recall obligation was not extracted as a requirement: {requirements!r}"
        )

        parser = RegulationParser()
        assert parser._detect_jurisdiction("This FSMA rule is issued by FDA under 21 CFR 1.1455.") == "FDA"
        assert parser._detect_jurisdiction("See the Code of Federal Regulations.") == "US-FEDERAL"
        assert parser._detect_jurisdiction("Nothing regulatory here.") == "UNKNOWN"
