"""#3009 — permissive text containing "required" must not become MANDATORY.

``infer_obligation_type`` used to scan for requirement keywords (phase 3)
before evaluating the modal (phase 4), so any sentence containing "required"
short-circuited to MANDATORY — including permissions whose noun phrase merely
mentions required records. "You may keep the required records in electronic
form." grants a choice about *format*; recording it as MANDATORY manufactures
a compliance gap the regulation does not contain. Same failure class as #2942
(a modality stored as its opposite), in the direction that invents
obligations rather than dropping them.

The fix keys phase 3 to the mandatory modals (shall/must) and to the
*operative* use of "required" (a be-verb predicate: "is required", "are
required to register"). An attributive "required" ("the required records",
"information required to be maintained") defers to the permissive-modal check
and only decides when no permissive modal governs the sentence.

Per the issue's acceptance criteria, the table below covers both directions
and is drawn from real 21 CFR Part 1 prose (Subpart S — FSMA 204 traceability
— plus, where Subpart S has no sentence of the required shape, the FSVP
regulations in the same part). Sentence sources are cited case by case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractor import infer_obligation_type

# (id, text, expected obligation)
_PHASE_ORDERING_TABLE = [
    # --- Permissive modal governing a requirement noun phrase → PERMITTED ---
    (
        "issue-example",
        # The issue's motivating sentence, patterned on 21 CFR 1.1455.
        "You may keep the required records in electronic form.",
        "PERMITTED",
    ),
    (
        "1.1455(b)",
        # 21 CFR 1.1455(b), verbatim: permissive "may" with "records
        # required under this subpart" as the object.
        "You may have another entity establish and maintain records "
        "required under this subpart on your behalf, but you are "
        "responsible for ensuring that such records can be retrieved and "
        "provided onsite within 24 hours of request for official review.",
        "PERMITTED",
    ),
    (
        "1.1455(a)(1)",
        # 21 CFR 1.1455(a)(1), verbatim: "required to" inside a reduced
        # relative clause ("information required to be maintained") under a
        # governing "may include" — proof that "required to" alone is not
        # the operative use.
        "Electronic records may include valid, working electronic links to "
        "the information required to be maintained under this subpart.",
        "PERMITTED",
    ),
    # --- Operative "required" stays MANDATORY --------------------------------
    (
        "1.1310-definition",
        # 21 CFR 1.1310 ("Food Traceability List" definition), verbatim:
        # operative "are required to be maintained", no governing modal.
        "Food Traceability List means the list of foods for which "
        "additional traceability records are required to be maintained, as "
        "designated in accordance with section 204(d)(2) of the FDA Food "
        "Safety Modernization Act.",
        "MANDATORY",
    ),
    (
        "1.1305-register",
        # Trimmed from 21 CFR 1.1305(h)(3): operative "is required to
        # register".
        "Such person is required to register with FDA under section 415 of the Federal Food, Drug, and Cosmetic Act.",
        "MANDATORY",
    ),
    (
        "are-required-to-register",
        # Pinned pre-#3009 behavior from the #1299 suite.
        "All entities are required to register.",
        "MANDATORY",
    ),
    # --- Mandatory modal alongside a requirement noun → MANDATORY ------------
    (
        "1.1455(c)(1)",
        # Trimmed from 21 CFR 1.1455(c)(1): "must" governs; "records
        # required under this subpart" is attributive.
        "You must make all records required under this subpart available "
        "to an authorized FDA representative, upon request, within 24 "
        "hours after the request.",
        "MANDATORY",
    ),
    # --- Mandatory modal with "may" in a subordinate clause → MANDATORY ------
    (
        "1.504(b)(2)",
        # Trimmed from 21 CFR 1.504(b)(2) (FSVP hazard analysis, same part;
        # Subpart S contains no sentence mixing "must" and "may"): the
        # permissive token sits in a relative clause and must not override
        # the governing "must".
        "Your hazard analysis must include known or reasonably foreseeable hazards that may be present in a food.",
        "MANDATORY",
    ),
    (
        "third-party-audit",
        # Trimmed from 21 CFR 1.660(a)(1) (accredited third-party
        # certification, same part): "must complete ... activities that may
        # be necessary".
        "The certification body must complete a regulatory audit and any "
        "other activities that may be necessary to determine compliance.",
        "MANDATORY",
    ),
    # --- Attributive "required" with no permissive modal → MANDATORY (4b) ----
    (
        "bare-required-list",
        "The required records: traceability lot code, quantity, and unit of measure.",
        "MANDATORY",
    ),
]


class TestPhaseOrdering3009:
    @pytest.mark.parametrize(
        "case_id,text,expected",
        _PHASE_ORDERING_TABLE,
        ids=[case_id for case_id, _, _ in _PHASE_ORDERING_TABLE],
    )
    def test_modal_outranks_requirement_noun(self, case_id, text, expected):
        result = infer_obligation_type(text)
        assert result["obligation"] == expected, (
            f"[{case_id}] {text!r} → {result['obligation']}, expected {expected}. "
            "#3009: the modal governing the main verb must be evaluated before "
            "requirement-keyword presence."
        )

    def test_issue_example_is_not_mandatory(self):
        """AC #1 verbatim: the motivating sentence must not return MANDATORY."""
        result = infer_obligation_type("You may keep the required records in electronic form.")
        assert result["obligation"] != "MANDATORY"

    def test_negated_permissive_with_required_noun_is_still_prohibited(self):
        """Phase ordering must not leak past phase 1: 'may not' is a ban even
        when a requirement noun is present."""
        result = infer_obligation_type("You may not store the required records offsite.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_scope"] == "prohibition"

    def test_exemption_with_required_still_wins_over_permissive(self):
        """Phase 0 precedence unchanged: 'not required' is an exemption even
        alongside a permissive modal."""
        result = infer_obligation_type("Small farms are not required to file and may keep summary records.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_scope"] == "exemption"

    def test_conditional_hedge_still_wins_over_permissive(self):
        """Phase 2 precedence unchanged (#1299): hedge + mandatory keyword is
        CONDITIONAL, not PERMITTED, even with 'may' present."""
        result = infer_obligation_type(
            "All handlers are required to file unless exempt under subsection (b), and may file electronically."
        )
        assert result["obligation"] == "CONDITIONAL"
