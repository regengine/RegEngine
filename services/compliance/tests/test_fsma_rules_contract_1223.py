"""Contract tests for services/compliance/app/fsma_rules.json — #1223.

#1223 surfaced "silent contract drift": ``required_fsma_fields`` in
the JSON config listed ``responsible_party_contact`` as a required
per-event KDE, but no ingestion surface (EPCIS, webhook, CSV)
actually captured it. If the rules engine ever consumed this list,
every real production event would fail validation on day one.

These tests are cheap invariants that lock the JSON config against
future drift:

1. Every entry in ``required_fsma_fields`` must map to something the
   ingestion surface can produce (either directly on the
   ``IngestEvent`` pydantic model or via a well-known canonical
   alias).

2. ``responsible_party_contact`` must NOT appear in
   ``required_fsma_fields`` — it's enforced at the graph layer, not
   per-event, and listing it here was the #1223 regression.

3. The ``responsible_party_enforcement`` block must exist and
   document the enforcement split.

These are pure JSON-parse tests — no HTTP, no DB, no FastAPI app
boot — so they run in ~10ms and are safe to keep green in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_RULES_PATH = (
    Path(__file__).parent.parent / "app" / "fsma_rules.json"
)


@pytest.fixture(scope="module")
def rules() -> dict:
    """Load fsma_rules.json once per module."""
    with _RULES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The ingestion contract — what per-event KDEs are *producible* today.
#
# Keep this list in sync with ``services/ingestion/app/webhook_models.py
# ::IngestEvent`` and the EPCIS normalizer. Canonical aliases are listed
# too (``tlc`` == ``traceability_lot_code``, ``event_date`` == ``timestamp``,
# ``location`` == ``location_gln`` / ``location_name``).
# ---------------------------------------------------------------------------

PRODUCIBLE_FIELDS = {
    # Core KDEs — captured by IngestEvent directly
    "cte_type",
    "tlc",
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "location",
    "location_gln",
    "location_name",
    "event_date",
    "timestamp",
    # CTE-specific
    "prior_source_tlc",
    "input_traceability_lot_codes",
    # KDE bag
    "kdes",
}


# ===========================================================================
# required_fsma_fields contract
# ===========================================================================


class TestRequiredFieldsProducibleByIngestion_Issue1223:
    def test_every_required_field_is_producible_by_ingestion(self, rules):
        """Every entry in ``required_fsma_fields`` must map to a field
        that the ingestion surface actually produces. Drift here means
        validation will reject every real event."""
        required = rules["validation"]["required_fsma_fields"]
        missing = [f for f in required if f not in PRODUCIBLE_FIELDS]
        assert missing == [], (
            f"required_fsma_fields lists fields not producible by "
            f"ingestion: {missing}. Either add the field to IngestEvent "
            f"or remove it from required_fsma_fields — the JSON config "
            f"must not drift from runtime schemas (#1223)."
        )

    def test_responsible_party_contact_is_NOT_in_required_fields(self, rules):
        """This is the exact #1223 regression — ``responsible_party_contact``
        was listed as required but never collected. Enforcement lives
        at the graph layer, not per-event."""
        required = rules["validation"]["required_fsma_fields"]
        assert "responsible_party_contact" not in required, (
            "responsible_party_contact is per-graph-event (21 CFR "
            "1.1370(c)), not per-ingestion-event — keeping it in "
            "required_fsma_fields is the #1223 silent-drift bug. "
            "Document the enforcement split in "
            "responsible_party_enforcement instead."
        )

    def test_required_fields_are_nonempty_and_unique(self, rules):
        """Sanity — the list must not be empty (that would degrade to
        'no validation at all') and must have no duplicates."""
        required = rules["validation"]["required_fsma_fields"]
        assert len(required) > 0, "required_fsma_fields is empty"
        assert len(required) == len(set(required)), (
            f"required_fsma_fields contains duplicates: {required}"
        )


# ===========================================================================
# responsible_party_enforcement contract
# ===========================================================================


class TestResponsiblePartyEnforcementDocumented_Issue1223:
    def test_responsible_party_enforcement_block_present(self, rules):
        """The enforcement-split block must exist so future contributors
        understand WHY responsible_party_contact isn't in
        required_fsma_fields."""
        val = rules["validation"]
        assert "responsible_party_enforcement" in val, (
            "responsible_party_enforcement block missing — it documents "
            "the 21 CFR 1.1370(c) enforcement split (graph-layer inline "
            "vs ingestion reference fields) and prevents #1223-style "
            "drift from recurring."
        )

    def test_reference_fields_cover_gln_and_name(self, rules):
        """The documented reference fields must at minimum include a
        GLN path and a human-name path — mirroring IngestEvent."""
        rpe = rules["validation"]["responsible_party_enforcement"]
        refs = rpe.get("reference_fields", [])
        assert "location_gln" in refs, (
            f"responsible_party_enforcement.reference_fields must "
            f"include location_gln; got {refs}"
        )
        assert "location_name" in refs, (
            f"responsible_party_enforcement.reference_fields must "
            f"include location_name as GLN-free fallback; got {refs}"
        )

    def test_inline_field_names_the_graph_layer_contact(self, rules):
        """The inline-only field callout must explicitly name
        responsible_party_contact so grep-audit catches the restriction."""
        rpe = rules["validation"]["responsible_party_enforcement"]
        inline = rpe.get("inline_field_graph_layer_only", "")
        assert inline == "responsible_party_contact", (
            f"inline_field_graph_layer_only must be "
            f"'responsible_party_contact' (graph /traceability KDE); "
            f"got {inline!r}"
        )


# ===========================================================================
# CTE-type enumeration is stable
# ===========================================================================


class TestAllowedCTETypesUnchanged_Issue1223:
    def test_all_seven_core_ftl_ctes_present(self, rules):
        """Lock the FTL CTE enumeration — #1223 should not accidentally
        trim the set. Missing a CTE here would silently disable
        validation for that event type."""
        allowed = set(rules["validation"]["allowed_cte_types"])
        expected = {
            "HARVESTING",
            "COOLING",
            "INITIAL_PACKING",
            "FIRST_LAND_BASED_RECEIVING",
            "SHIPPING",
            "RECEIVING",
            "TRANSFORMATION",
        }
        assert expected <= allowed, (
            f"allowed_cte_types missing FTL CTEs: {expected - allowed}"
        )
