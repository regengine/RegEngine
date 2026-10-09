"""Regression tests: Lot, TraceEvent and Facility require tenant_id.

Previously ``tenant_id`` defaulted to ``None`` and ``node_properties``
silently dropped it, so omitting the field constructed a tenantless
node that the tenant-scoped MERGE templates could not isolate.
Construction without a tenant must now fail, and valid nodes must
always carry ``tenant_id`` in their properties.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.models.fsma_nodes import CTEType, Facility, Lot, TraceEvent


def test_lot_requires_tenant() -> None:
    with pytest.raises(TypeError):
        Lot(tlc="TLC-1")


def test_trace_event_requires_tenant() -> None:
    with pytest.raises(TypeError):
        TraceEvent(event_id="E-1", type=CTEType.SHIPPING, event_date="2026-01-01")


def test_facility_requires_tenant() -> None:
    with pytest.raises(TypeError):
        Facility(gln="1234567890128")


def test_blank_tenant_rejected() -> None:
    with pytest.raises(ValueError):
        Lot(tlc="TLC-1", tenant_id="")
    with pytest.raises(ValueError):
        TraceEvent(
            event_id="E-1",
            type=CTEType.SHIPPING,
            event_date="2026-01-01",
            tenant_id="",
        )
    with pytest.raises(ValueError):
        Facility(gln="1234567890128", tenant_id="")


def test_node_properties_always_carry_tenant() -> None:
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a")
    assert lot.node_properties["tenant_id"] == "tenant-a"

    event = TraceEvent(
        event_id="E-1",
        type=CTEType.SHIPPING,
        event_date="2026-01-01",
        tenant_id="tenant-a",
    )
    assert event.node_properties["tenant_id"] == "tenant-a"

    facility = Facility(gln="1234567890128", tenant_id="tenant-a")
    assert facility.node_properties["tenant_id"] == "tenant-a"


def test_hash_derivation_still_works() -> None:
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a")
    assert lot.sha256_hash is not None

    event = TraceEvent(
        event_id="E-1",
        type=CTEType.SHIPPING,
        event_date="2026-01-01",
        tenant_id="tenant-a",
    )
    assert event.sha256_hash is not None

    facility = Facility(gln="1234567890128", tenant_id="tenant-a")
    assert facility.sha256_hash is not None
