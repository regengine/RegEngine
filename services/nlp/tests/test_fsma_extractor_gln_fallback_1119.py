"""Regression tests for #1119 — GLN fallback must not mirror a single
GLN into both ``ship_from_gln`` and ``tlc_source_gln``.

Background
----------
Before the fix, ``FSMAExtractor._extract_gln_roles`` ran an unlabeled
positional fallback that unconditionally set::

    roles.setdefault("ship_from_gln", normalize(unique_glns[0]))
    if len(unique_glns) > 1:
        roles.setdefault("ship_to_gln", normalize(unique_glns[1]))
    roles.setdefault("tlc_source_gln", normalize(unique_glns[0]))  # <-- BUG

That asserts the TLC Source (originator / packer / processor — FSMA
§1.1320 KDE) is **always** the same party as the Ship-From, which is
only true when the supplier is also the packer. For co-packed
products, distribution hubs, or any multi-hop supply chain this
silently mislabels provenance. In a recall scenario, investigators
walk to the wrong facility.

The fix:

* Keep the positional fallback for ``ship_from_gln`` / ``ship_to_gln``
  — BOL headers reliably lead with Ship-From then Ship-To.
* Do **not** infer ``tlc_source_gln`` from document order. The only
  path to populating it is an explicit labeled pattern (``TLC Source``,
  ``Lot Owner``, ``Packer``, ``Packed By``). If that label is absent,
  ``tlc_source_gln`` stays ``None`` and the extractor logs a warning
  for HITL review routing.

The three tests below cover the exact cases the issue reporter
demanded:

* ``test_single_unlabeled_gln_does_not_mirror_to_tlc_source`` — one
  raw GLN with no role label; ``ship_from_gln`` may populate, but
  ``tlc_source_gln`` MUST stay ``None``.
* ``test_two_unlabeled_glns_populate_ship_but_not_tlc_source`` — two
  raw GLNs; ``ship_from_gln`` and ``ship_to_gln`` populate, but
  ``tlc_source_gln`` stays ``None``.
* ``test_explicit_packed_by_label_populates_tlc_source_distinctly`` —
  BOL with ``Ship From: GLN X`` and ``Packed By: GLN Y``; the TLC
  source resolves to Y, not X.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo root importable so ``services.nlp.*`` resolves.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor


@pytest.fixture
def extractor() -> FSMAExtractor:
    return FSMAExtractor(confidence_threshold=0.85)


class TestGLNFallbackDoesNotMirrorToTLCSource_Issue1119:
    def test_single_unlabeled_gln_does_not_mirror_to_tlc_source(
        self, extractor: FSMAExtractor
    ) -> None:
        """One unlabeled GLN must populate ship_from only — never
        tlc_source. The pre-fix code mirrored the same value into both
        slots, which destroys provenance in multi-hop chains."""
        text = "Some shipment document. GLN: 0012345678905. Case count: 40."

        roles = extractor._extract_gln_roles(text)

        assert roles.get("ship_from_gln") == "urn:gln:0012345678905"
        assert roles.get("tlc_source_gln") is None, (
            "tlc_source_gln must NOT be inferred from a single unlabeled "
            "GLN — packer != shipper in multi-hop supply chains (#1119)"
        )

    def test_two_unlabeled_glns_populate_ship_but_not_tlc_source(
        self, extractor: FSMAExtractor
    ) -> None:
        """With two unlabeled GLNs the positional fallback maps them to
        ship_from and ship_to, but tlc_source_gln stays None because
        there is no textual signal that either party is the TLC
        originator."""
        text = (
            "BOL header. GLN: 0012345678905.\n"
            "Body: delivery address GLN 0098765432108. 40 cases shipped."
        )

        roles = extractor._extract_gln_roles(text)

        assert roles.get("ship_from_gln") == "urn:gln:0012345678905"
        assert roles.get("ship_to_gln") == "urn:gln:0098765432108"
        assert roles.get("tlc_source_gln") is None, (
            "tlc_source_gln must NOT be inferred from document order; "
            "Ship-From is not the originator unless the supplier is the "
            "packer (#1119)"
        )

    def test_explicit_packed_by_label_populates_tlc_source_distinctly(
        self, extractor: FSMAExtractor
    ) -> None:
        """With explicit role labels the TLC source resolves to the
        PACKER, not the SHIPPER — the two values must be distinct."""
        text = (
            "Bill of Lading\n"
            "Ship From: GLN 0011111111116\n"
            "Ship To: GLN 0022222222225\n"
            "Packed By: GLN 0033333333334\n"
            "40 cases of romaine lettuce, lot RM-2024-A.\n"
        )

        roles = extractor._extract_gln_roles(text)

        assert roles.get("ship_from_gln") == "urn:gln:0011111111116"
        assert roles.get("ship_to_gln") == "urn:gln:0022222222225"
        assert roles.get("tlc_source_gln") == "urn:gln:0033333333334", (
            "Explicit Packed-By label must drive tlc_source_gln; it must "
            "NOT be silently aliased to ship_from_gln (#1119)"
        )
        # Sanity: the packer GLN is genuinely distinct from the shipper.
        assert roles["tlc_source_gln"] != roles["ship_from_gln"]
