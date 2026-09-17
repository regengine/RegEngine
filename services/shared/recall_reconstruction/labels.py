"""Vocabulary for recall-scope reconstruction verdicts and findings."""

from __future__ import annotations

from enum import Enum


class LinkLabel(str, Enum):
    """Exactly one label per worksheet row.

    ``LINKED``: an unbroken evidence chain connects this quantity to the
    implicated lot and no blocking finding sits on that chain.

    ``NO_LINK_ESTABLISHED``: the chain for this quantity is complete within the
    reviewed evidence and no record on it names the implicated lot. This is
    not a declaration that the product is safe; excluding product from a
    recall is a practitioner decision.

    ``UNRESOLVED``: a required record is missing, conflicting, or was not
    available at the time of review. The row must not be read as either
    linked or excluded.
    """

    LINKED = "linked"
    NO_LINK_ESTABLISHED = "no_link_established"
    UNRESOLVED = "unresolved"


class FindingType(str, Enum):
    MISSING_HANDOFF_SHIPPING = "missing_handoff_shipping"
    MISSING_HANDOFF_RECEIVING = "missing_handoff_receiving"
    MISSING_PALLET_CONTENTS = "missing_pallet_contents"
    CONFLICTING_PALLET_CONTENTS = "conflicting_pallet_contents"
    UNMATCHED_IDENTIFIER = "unmatched_identifier"
    QUANTITY_DISCREPANCY = "quantity_discrepancy"
    SOURCE_UNAVAILABLE_AFTER_CUTOFF = "source_unavailable_after_cutoff"
