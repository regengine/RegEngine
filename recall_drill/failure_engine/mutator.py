"""Deterministic mutation engine for FSMA 204 traceability records."""

from __future__ import annotations

import copy
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .mutation_library import (
    MUTATION_SEVERITY,
    REQUIRED_CTE_FIELDS,
    REQUIRED_KDES,
    MutationType,
    Severity,
)


class MutationResult:
    """Immutable result of a single mutation operation."""

    __slots__ = ("data", "metadata")

    def __init__(self, data: Any, metadata: dict):
        self.data = data
        self.metadata = metadata

    def to_dict(self) -> dict:
        return {"data": self.data, "metadata": self.metadata}


class Mutator:
    """Apply controlled mutations to CTE/KDE datasets.

    Every method returns a ``MutationResult`` containing the mutated data
    and structured metadata describing exactly what changed.
    """

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def _meta(
        self,
        mutation_type: MutationType,
        affected: int,
        *,
        details: dict | None = None,
    ) -> dict:
        return {
            "mutation_id": str(uuid.uuid4()),
            "type": mutation_type.value,
            "severity": MUTATION_SEVERITY[mutation_type].value,
            "affected_records": affected,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        }

    # ------------------------------------------------------------------
    # Record-level mutations
    # ------------------------------------------------------------------

    def remove_required_field(
        self, record: dict, field: str | None = None
    ) -> MutationResult:
        """Remove a required KDE field from a single record."""
        rec = copy.deepcopy(record)
        target = field or self._rng.choice(list(REQUIRED_KDES & set(rec.keys())))
        rec.pop(target, None)
        return MutationResult(
            rec,
            self._meta(
                MutationType.REMOVE_REQUIRED_FIELD,
                1,
                details={"removed_field": target},
            ),
        )

    def corrupt_type(
        self, record: dict, field: str, new_value: Any = None
    ) -> MutationResult:
        """Replace a field value with an incompatible type."""
        rec = copy.deepcopy(record)
        original = rec.get(field)
        if new_value is not None:
            rec[field] = new_value
        elif isinstance(original, (int, float)):
            rec[field] = "NOT_A_NUMBER"
        elif isinstance(original, str):
            rec[field] = -9999
        elif isinstance(original, list):
            rec[field] = "NOT_A_LIST"
        else:
            rec[field] = {"__corrupted": True}
        return MutationResult(
            rec,
            self._meta(
                MutationType.CORRUPT_TYPE,
                1,
                details={
                    "field": field,
                    "original_type": type(original).__name__,
                    "injected_type": type(rec[field]).__name__,
                },
            ),
        )

    # ------------------------------------------------------------------
    # Dataset-level mutations
    # ------------------------------------------------------------------

    def duplicate_tlc(self, dataset: list[dict]) -> MutationResult:
        """Duplicate a TLC across two records, creating an ambiguous lot."""
        ds = copy.deepcopy(dataset)
        if len(ds) < 2:
            return MutationResult(ds, self._meta(MutationType.DUPLICATE_TLC, 0))
        src = self._rng.choice(ds)
        tgt_idx = self._rng.randrange(len(ds))
        original_tlc = ds[tgt_idx].get("traceability_lot_code")
        ds[tgt_idx]["traceability_lot_code"] = src["traceability_lot_code"]
        return MutationResult(
            ds,
            self._meta(
                MutationType.DUPLICATE_TLC,
                2,
                details={
                    "duplicated_tlc": src.get("traceability_lot_code"),
                    "overwritten_tlc": original_tlc,
                },
            ),
        )

    def break_cte_chain(self, dataset: list[dict]) -> MutationResult:
        """Remove linking fields so CTE events cannot be chained."""
        ds = copy.deepcopy(dataset)
        broken = []
        for rec in ds:
            for field in REQUIRED_CTE_FIELDS:
                if field in rec:
                    rec.pop(field)
                    broken.append(field)
                    break
            if broken:
                break
        return MutationResult(
            ds,
            self._meta(
                MutationType.BREAK_CTE_CHAIN,
                len(broken),
                details={"removed_fields": broken},
            ),
        )

    def shuffle_timestamps(self, dataset: list[dict]) -> MutationResult:
        """Randomly reorder event timestamps, breaking temporal integrity."""
        ds = copy.deepcopy(dataset)
        dates = [r.get("event_date") for r in ds if r.get("event_date")]
        self._rng.shuffle(dates)
        affected = 0
        for rec in ds:
            if rec.get("event_date") and dates:
                old = rec["event_date"]
                rec["event_date"] = dates.pop(0)
                if rec["event_date"] != old:
                    affected += 1
        return MutationResult(
            ds, self._meta(MutationType.SHUFFLE_TIMESTAMPS, affected)
        )

    def create_orphan_record(self, dataset: list[dict]) -> MutationResult:
        """Insert a record that references a non-existent upstream TLC."""
        ds = copy.deepcopy(dataset)
        orphan = {
            "traceability_lot_code": f"ORPHAN-{uuid.uuid4().hex[:8]}",
            "event_type": "receiving",
            "event_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "product_description": "ORPHAN PRODUCT — NO UPSTREAM",
            "quantity": 1,
            "unit_of_measure": "case",
            "origin_gln": "0000000000000",
            "destination_gln": "9999999999999",
            "immediate_previous_source": f"GHOST-{uuid.uuid4().hex[:8]}",
        }
        ds.append(orphan)
        return MutationResult(
            ds,
            self._meta(
                MutationType.CREATE_ORPHAN,
                1,
                details={"orphan_tlc": orphan["traceability_lot_code"]},
            ),
        )

    def simulate_partial_ingestion(
        self, dataset: list[dict], drop_ratio: float = 0.3
    ) -> MutationResult:
        """Randomly drop records to simulate partial ingestion failure."""
        ds = copy.deepcopy(dataset)
        drop_count = max(1, int(len(ds) * drop_ratio))
        indices = sorted(self._rng.sample(range(len(ds)), min(drop_count, len(ds))))
        dropped_tlcs = [ds[i].get("traceability_lot_code") for i in indices]
        ds = [r for i, r in enumerate(ds) if i not in set(indices)]
        return MutationResult(
            ds,
            self._meta(
                MutationType.PARTIAL_INGESTION,
                drop_count,
                details={"dropped_tlcs": dropped_tlcs, "drop_ratio": drop_ratio},
            ),
        )

    def inject_encoding_errors(self, csv_text: str) -> MutationResult:
        """Inject encoding errors into CSV text."""
        replacements = [
            ("e", "\xe9"),
            ("a", "\xe4"),
            (",", "\x00,"),
        ]
        mutated = csv_text
        choice = self._rng.choice(replacements)
        mutated = mutated.replace(choice[0], choice[1], 3)
        return MutationResult(
            mutated,
            self._meta(
                MutationType.ENCODING_ERROR,
                3,
                details={"replacement": f"{choice[0]!r} -> {choice[1]!r}"},
            ),
        )

    def create_orphan(self, dataset: list[dict]) -> MutationResult:
        """Alias for create_orphan_record — matches MutationType.CREATE_ORPHAN.value."""
        return self.create_orphan_record(dataset)

    def partial_ingestion(
        self, dataset: list[dict], drop_ratio: float = 0.3
    ) -> MutationResult:
        """Alias for simulate_partial_ingestion — matches MutationType.PARTIAL_INGESTION.value."""
        return self.simulate_partial_ingestion(dataset, drop_ratio=drop_ratio)

    def encoding_error(self, csv_text: str) -> MutationResult:
        """Alias for inject_encoding_errors — matches MutationType.ENCODING_ERROR.value."""
        return self.inject_encoding_errors(csv_text)

    def invalid_gln(self, record: dict) -> MutationResult:
        """Replace a GLN field with an invalid value."""
        rec = copy.deepcopy(record)
        gln_fields = [f for f in ("origin_gln", "destination_gln") if f in rec]
        if not gln_fields:
            return MutationResult(rec, self._meta(MutationType.INVALID_GLN, 0))
        target = self._rng.choice(gln_fields)
        original = rec[target]
        rec[target] = "INVALID_GLN_999"
        return MutationResult(
            rec,
            self._meta(
                MutationType.INVALID_GLN,
                1,
                details={"field": target, "original": original, "injected": rec[target]},
            ),
        )

    def missing_supplier(self, record: dict) -> MutationResult:
        """Remove the immediate_previous_source field."""
        rec = copy.deepcopy(record)
        removed = rec.pop("immediate_previous_source", None)
        rec.pop("tlc_source_gln", None)
        return MutationResult(
            rec,
            self._meta(
                MutationType.MISSING_SUPPLIER,
                1,
                details={"removed_value": removed},
            ),
        )
