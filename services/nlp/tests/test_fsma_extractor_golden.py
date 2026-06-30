"""Golden/snapshot tests for the FSMA regex extractor (#2525).

The FSMA extractor's KDE field extraction (TLC/GTIN-14, GLN role
assignment, quantity+unit, date, CTE type) is driven entirely by the
positional regex in ``patterns.py``. ``FSMAExtractor.extract()`` output
flows through the consumer into CTE/KDE persistence and the
graph/evidence layer, so a silent change to any pattern can shift which
lot or location is extracted — corrupting the exact evidence an FSMA
204 traceback depends on — with no existing test failing.

This module freezes a representative corpus of document text under
``fixtures/extractor_corpus/`` and asserts the full extracted CTE/KDE
field set per fixture against a committed ``<name>.expected.json``
snapshot. Editing any regex in ``patterns.py`` that changes extracted
output will make the matching assertion fail until the snapshot is
deliberately regenerated.

Regenerating the snapshots
--------------------------
The expected JSON files are committed and treated as a reviewed
artifact. To regenerate them after an intentional extractor change::

    REGEN_FSMA_GOLDEN=1 python -m pytest \
        services/nlp/tests/test_fsma_extractor_golden.py

then review the resulting diff before committing. The default run never
writes snapshots — it only asserts against the committed values.

The corpus deliberately includes:

* ``bol_labeled_packer`` — the #1119 packer-GLN case: a BOL with
  distinct Ship-From / Ship-To / Packed-By GLNs. ``tlc_source_gln``
  must resolve to the packer, NOT mirror ship_from. Also exercises the
  #1123 SHIPPING+RECEIVING split and the #1104 verbatim-TLC / separate
  GTIN behavior.
* ``bol_unlabeled_glns`` — two unlabeled GLNs: the positional fallback
  fills ship_from/ship_to but ``tlc_source_gln`` stays null (#1119).
* ``packing_slip_qty_unit`` / ``packing_slip_qty_unitless`` — the
  #1129 quantity-with-unit vs quantity-without-unit pair. The unitless
  variant MUST drop both quantity and unit_of_measure (no silent
  unitless quantity).
* ``harvest_log`` / ``landing_report`` — origin-side documents map to
  the correct CTE types (#1103), not the legacy SHIPPING fallback.
* ``invoice`` — invoices emit no CTE and route to review.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Make the repo root importable so ``services.nlp.*`` resolves.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import CTE, FSMAExtractionResult

_CORPUS_DIR = Path(__file__).parent / "fixtures" / "extractor_corpus"
_TENANT_ID = "00000000-0000-0000-0000-000000000123"

# KDE fields frozen in the snapshot. Deliberately excludes volatile /
# derived values (event_id UUID, redacted raw_text, confidence floats)
# and keeps the load-bearing evidence fields a traceback relies on.
_KDE_FIELDS = (
    "traceability_lot_code",
    "gtin",
    "product_description",
    "quantity",
    "unit_of_measure",
    "location_identifier",
    "event_date",
    "ship_from_gln",
    "ship_to_gln",
    "tlc_source_gln",
    "tlc_source_fda_reg",
    "prior_source_tlc",
)


def _project_cte(cte: CTE) -> Dict[str, Any]:
    kde = cte.kdes
    projected = {"cte_type": cte.type.value}
    projected.update({field: getattr(kde, field) for field in _KDE_FIELDS})
    return projected


def _project_result(result: FSMAExtractionResult) -> Dict[str, Any]:
    """Project an extraction result into a stable, comparable snapshot.

    Only deterministic, evidence-bearing fields are kept. CTEs are
    emitted in extraction order (the extractor keeps SHIPPING before its
    paired RECEIVING, etc.).
    """
    return {
        "document_type": result.document_type.value,
        "review_required": result.review_required,
        "confidence_level": result.confidence_level.value,
        "ctes": [_project_cte(cte) for cte in result.ctes],
    }


def _fixture_names() -> List[str]:
    return sorted(p.stem for p in _CORPUS_DIR.glob("*.txt"))


@pytest.fixture(scope="module")
def extractor() -> FSMAExtractor:
    return FSMAExtractor(confidence_threshold=0.85)


@pytest.mark.parametrize("name", _fixture_names())
def test_fsma_extractor_golden_corpus(name: str, extractor: FSMAExtractor) -> None:
    """Each corpus document extracts to its committed snapshot exactly.

    A regex edit in ``patterns.py`` that shifts extracted output (a
    different GLN assigned to a role, a dropped lot/quantity, a changed
    proximity window) makes this assertion fail until the snapshot is
    deliberately regenerated with ``REGEN_FSMA_GOLDEN=1``.
    """
    text = (_CORPUS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    result = extractor.extract(text, document_id=name, tenant_id=_TENANT_ID)
    actual = _project_result(result)

    expected_path = _CORPUS_DIR / f"{name}.expected.json"

    if os.getenv("REGEN_FSMA_GOLDEN"):
        expected_path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip(f"Regenerated snapshot for {name}")

    assert expected_path.exists(), (
        f"Missing golden snapshot {expected_path.name}. Generate it with "
        "REGEN_FSMA_GOLDEN=1 and review the diff before committing."
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"FSMA extraction for {name!r} drifted from the committed golden "
        f"snapshot. If this change is intentional, regenerate with "
        f"REGEN_FSMA_GOLDEN=1 and review the diff.\n"
        f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
        f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
    )


def test_packer_gln_not_mirrored_into_tlc_source(extractor: FSMAExtractor) -> None:
    """#1119 guard, asserted directly on the golden corpus.

    The BOL fixture carries distinct Ship-From / Ship-To / Packed-By
    GLNs. ``tlc_source_gln`` MUST resolve to the packer and stay
    distinct from ``ship_from_gln`` — the original #1119 regression
    mirrored ship_from into the TLC source slot.
    """
    text = (_CORPUS_DIR / "bol_labeled_packer.txt").read_text(encoding="utf-8")
    result = extractor.extract(text, document_id="bol_labeled_packer", tenant_id=_TENANT_ID)

    shipping = next(c for c in result.ctes if c.type.value == "SHIPPING")
    assert shipping.kdes.tlc_source_gln == "urn:gln:0033333333334"
    assert shipping.kdes.ship_from_gln == "urn:gln:0011111111116"
    assert shipping.kdes.tlc_source_gln != shipping.kdes.ship_from_gln


def test_unitless_quantity_is_dropped(extractor: FSMAExtractor) -> None:
    """#1129 guard, asserted directly on the golden corpus.

    A quantity with no unit ("Quantity: 50") must NOT populate
    ``quantity``/``unit_of_measure`` — the pre-fix code silently stored
    a unitless quantity. The companion with-unit fixture proves the
    extractor still captures the pair when a unit IS present.
    """
    with_unit_text = (_CORPUS_DIR / "packing_slip_qty_unit.txt").read_text(encoding="utf-8")
    unitless_text = (_CORPUS_DIR / "packing_slip_qty_unitless.txt").read_text(encoding="utf-8")

    with_unit = extractor.extract(with_unit_text, document_id="qty_unit", tenant_id=_TENANT_ID)
    unitless = extractor.extract(unitless_text, document_id="qty_unitless", tenant_id=_TENANT_ID)

    with_unit_cte = with_unit.ctes[0]
    assert with_unit_cte.kdes.quantity == 50.0
    assert with_unit_cte.kdes.unit_of_measure == "cases"

    unitless_cte = unitless.ctes[0]
    assert unitless_cte.kdes.quantity is None, "unitless quantity must not be stored (#1129)"
    assert unitless_cte.kdes.unit_of_measure is None
