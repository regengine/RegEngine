"""Load a recall fixture directory into typed records.

Rules enforced here, because they are where honesty is won or lost:

* A blank required value never becomes a default. It becomes a finding.
* Every row keeps a :class:`SourceRef` (file, row, record id, file sha256).
* A manual correction is applied only when it carries author, reason, and
  evidence, and the applied correction is recorded next to the row it changed.
* When a source system is unavailable, only its retained snapshot is used and
  the last successful sync time is carried into the record set.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.fsma_validation import validate_gln, validate_sscc

from .labels import FindingType
from .records import (
    ContentsAssertion,
    Finding,
    LotRecord,
    ManualCorrection,
    Receipt,
    RecordSet,
    RepackRow,
    Shipment,
    SourceFile,
    SourceRef,
    finding_id_for,
)

# file name -> (source system, kind)
FILE_SPECS: Dict[str, Dict[str, str]] = {
    "mfg_lots.csv": {"source_system": "mfg_wms", "kind": "lots", "id_column": "lot_code"},
    "mfg_pallet_contents.csv": {"source_system": "mfg_wms", "kind": "contents", "id_column": "record_id"},
    "mfg_shipping.csv": {"source_system": "mfg_wms", "kind": "shipping", "id_column": "shipment_id"},
    "dc_receiving.csv": {"source_system": "dc_erp", "kind": "receiving", "id_column": "receipt_id"},
    "dc_repack.csv": {"source_system": "dc_erp", "kind": "repack", "id_column": "record_id"},
    "dc_shipping.csv": {"source_system": "dc_erp", "kind": "shipping", "id_column": "shipment_id"},
    "3pl_receiving.csv": {"source_system": "3pl_wms", "kind": "receiving", "id_column": "receipt_id"},
    "3pl_repack.csv": {"source_system": "3pl_wms", "kind": "repack", "id_column": "record_id"},
    "3pl_shipping.csv": {"source_system": "3pl_wms", "kind": "shipping", "id_column": "shipment_id"},
    "destination_receiving.csv": {
        "source_system": "destination_wms",
        "kind": "receiving",
        "id_column": "receipt_id",
    },
    "manual_corrections.csv": {"source_system": "recall_team", "kind": "corrections", "id_column": "correction_id"},
}

# Fields a manual correction is allowed to assert. Anything else is refused
# and recorded as not applied.
CORRECTABLE_FIELDS = {"receiving": {"shipment_ref"}, "contents": {"lot_code"}, "shipping": {"ship_to_gln"}}

CASES: Dict[str, Dict[str, Any]] = {
    "complete": {"description": "All source records available."},
    "missing_3pl_contents": {
        "description": "The 3PL's pallet-content (repack) record is not provided.",
        "drop_files": ["3pl_repack.csv"],
    },
    "erp_unavailable": {
        "description": "The DC ERP cannot be reached; only its retained snapshot is used.",
        "unavailable_sources": ["dc_erp"],
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _blank(value: Optional[str]) -> bool:
    return value is None or not str(value).strip()


def _float_or_none(value: Optional[str]) -> Optional[float]:
    if _blank(value):
        return None
    return float(str(value).strip())


class _Loader:
    def __init__(self, fixture_dir: Path, case: str) -> None:
        if case not in CASES:
            raise ValueError(f"unknown case {case!r}; expected one of {sorted(CASES)}")
        self.fixture_dir = fixture_dir
        self.case = case
        self.spec = CASES[case]
        self.manifest = json.loads((fixture_dir / "sync_manifest.json").read_text(encoding="utf-8"))
        self.rs = RecordSet(case=case, fixture_dir=str(fixture_dir), files={}, sync_manifest=self.manifest)
        # rows kept by (file, record_id) as (line_number, row) so corrections can target them
        self._rows: Dict[str, Dict[str, List[Tuple[int, Dict[str, str]]]]] = {}

    # -- findings -----------------------------------------------------------
    def _finding(
        self,
        ftype: FindingType,
        description: str,
        *,
        pallet_id: Optional[str] = None,
        lot_code: Optional[str] = None,
        refs: Optional[List[SourceRef]] = None,
        blocking: bool = True,
    ) -> Finding:
        finding = Finding(
            finding_id=finding_id_for(ftype, pallet_id, lot_code, description),
            type=ftype,
            pallet_id=pallet_id,
            lot_code=lot_code,
            description=description,
            blocking=blocking,
            source_refs=list(refs or []),
        )
        self.rs.load_findings.append(finding)
        return finding

    # -- file resolution ----------------------------------------------------
    def _resolve_file(self, name: str) -> SourceFile:
        spec = FILE_SPECS[name]
        source = spec["source_system"]
        manifest_entry = self.manifest.get("files", {}).get(name, {})
        synced_at = manifest_entry.get("synced_at")

        if name in self.spec.get("drop_files", []):
            return SourceFile(
                name=name,
                source_system=source,
                available=False,
                synced_at=synced_at,
                unavailable_reason="record not provided for this case",
            )

        if source in self.spec.get("unavailable_sources", []):
            cutoff = self.manifest.get("sources", {}).get(source, {}).get("last_successful_sync_at")
            if cutoff:
                self.rs.cutoffs[source] = cutoff
            retained = self.fixture_dir / "retained" / source / name
            if retained.exists():
                return SourceFile(
                    name=name,
                    source_system=source,
                    available=True,
                    path=str(retained),
                    sha256=sha256_file(retained),
                    synced_at=cutoff,
                    retained_from=f"retained/{source}/{name}",
                )
            return SourceFile(
                name=name,
                source_system=source,
                available=False,
                synced_at=None,
                unavailable_reason=(
                    f"source system {source} unavailable; no retained copy of {name} "
                    f"(last successful sync {cutoff or 'never'})"
                ),
            )

        live = self.fixture_dir / name
        if not live.exists():
            return SourceFile(
                name=name, source_system=source, available=False, unavailable_reason="file absent from fixture"
            )
        return SourceFile(
            name=name,
            source_system=source,
            available=True,
            path=str(live),
            sha256=sha256_file(live),
            synced_at=synced_at,
        )

    def _read_rows(self, sf: SourceFile) -> List[Dict[str, str]]:
        assert sf.path
        with open(sf.path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        sf.row_count = len(rows)
        return rows

    # -- validation helpers -------------------------------------------------
    def _check_gln(self, value: str, ref: SourceRef, field_name: str) -> None:
        result = validate_gln(value)
        if not result.is_valid:
            self._finding(
                FindingType.UNMATCHED_IDENTIFIER,
                f"{field_name} {value!r} is not a valid GLN-13: " + "; ".join(e.message for e in result.errors),
                refs=[ref],
            )

    def _check_sscc(self, value: str, ref: SourceRef, field_name: str) -> None:
        result = validate_sscc(value)
        if not result.is_valid:
            self._finding(
                FindingType.UNMATCHED_IDENTIFIER,
                f"{field_name} {value!r} is not a valid SSCC-18: " + "; ".join(e.message for e in result.errors),
                pallet_id=value,
                refs=[ref],
            )

    def _require(self, row: Dict[str, str], fields: List[str], ref: SourceRef) -> bool:
        missing = [f for f in fields if _blank(row.get(f))]
        if missing:
            self._finding(
                FindingType.UNMATCHED_IDENTIFIER,
                f"row is missing required field(s) {missing}; row not interpreted",
                pallet_id=row.get("pallet_id") or None,
                refs=[ref],
            )
            return False
        return True

    # -- loading ------------------------------------------------------------
    def load(self) -> RecordSet:
        # Corrections are read first so they can be applied while rows load.
        corrections_by_target: Dict[str, List[ManualCorrection]] = {}
        for name in FILE_SPECS:
            sf = self._resolve_file(name)
            self.rs.files[name] = sf
            if not sf.available:
                continue
            rows = self._read_rows(sf)
            self._rows[name] = {}
            for index, row in enumerate(rows, start=2):
                record_id = (row.get(FILE_SPECS[name]["id_column"]) or "").strip()
                self._rows[name].setdefault(record_id, []).append((index, row))
                if name == "manual_corrections.csv":
                    correction = self._load_correction(row, index, sf)
                    if correction is not None:
                        corrections_by_target.setdefault(
                            f"{correction.target_file}::{correction.target_record_id}", []
                        ).append(correction)

        for name, sf in self.rs.files.items():
            if not sf.available or name == "manual_corrections.csv":
                continue
            kind = FILE_SPECS[name]["kind"]
            for record_id, rows in self._rows[name].items():
                for line_number, row in rows:
                    ref = SourceRef(
                        file=name,
                        row_number=line_number,
                        record_id=record_id,
                        file_sha256=sf.sha256 or "",
                        source_system=sf.source_system,
                    )
                    applied = self._apply_corrections(
                        row, corrections_by_target.get(f"{name}::{record_id}", []), kind, ref
                    )
                    self._load_row(kind, row, ref, applied)

        # Corrections whose target file/row never loaded are recorded as not applied.
        for correction in self.rs.corrections:
            if not correction.applied and correction.not_applied_reason is None:
                target = self.rs.files.get(correction.target_file)
                if target is None or not target.available:
                    correction.not_applied_reason = f"target file {correction.target_file} not available"
                else:
                    correction.not_applied_reason = (
                        f"target record {correction.target_record_id} not found in {correction.target_file}"
                    )
        return self.rs

    def _load_correction(self, row: Dict[str, str], index: int, sf: SourceFile) -> Optional[ManualCorrection]:
        ref = SourceRef(
            file=sf.name,
            row_number=index,
            record_id=row.get("correction_id", ""),
            file_sha256=sf.sha256 or "",
            source_system=sf.source_system,
        )
        required = [
            "correction_id",
            "target_file",
            "target_record_id",
            "field",
            "value",
            "author",
            "reason",
            "evidence_ref",
            "asserted_at",
        ]
        if not self._require(row, required, ref):
            return None
        correction = ManualCorrection(
            correction_id=row["correction_id"].strip(),
            target_file=row["target_file"].strip(),
            target_record_id=row["target_record_id"].strip(),
            field=row["field"].strip(),
            value=row["value"].strip(),
            author=row["author"].strip(),
            reason=row["reason"].strip(),
            evidence_ref=row["evidence_ref"].strip(),
            asserted_at=parse_ts(row["asserted_at"]),
            source_ref=ref,
        )
        self.rs.corrections.append(correction)
        return correction

    def _apply_corrections(
        self, row: Dict[str, str], corrections: List[ManualCorrection], kind: str, ref: SourceRef
    ) -> List[ManualCorrection]:
        applied: List[ManualCorrection] = []
        for correction in corrections:
            allowed = CORRECTABLE_FIELDS.get(kind, set())
            if correction.field not in allowed:
                correction.not_applied_reason = f"field {correction.field!r} is not correctable on {kind} records"
                continue
            if not _blank(row.get(correction.field)) and row[correction.field].strip() != correction.value:
                correction.not_applied_reason = (
                    f"record already carries {correction.field}={row[correction.field]!r}; "
                    "a correction may fill a blank or confirm a value, not overwrite one"
                )
                continue
            row[correction.field] = correction.value
            correction.applied = True
            applied.append(correction)
        return applied

    def _load_row(self, kind: str, row: Dict[str, str], ref: SourceRef, applied: List[ManualCorrection]) -> None:
        if kind == "lots":
            if not self._require(row, ["lot_code", "gtin", "product_description", "produced_at", "location_gln"], ref):
                return
            self._check_gln(row["location_gln"], ref, "location_gln")
            self.rs.lots.append(
                LotRecord(
                    lot_code=row["lot_code"].strip(),
                    gtin=row["gtin"].strip(),
                    product_description=row["product_description"].strip(),
                    quantity=_float_or_none(row.get("quantity")),
                    unit_of_measure=row.get("unit_of_measure", "").strip(),
                    produced_at=parse_ts(row["produced_at"]),
                    location_gln=row["location_gln"].strip(),
                    location_name=row.get("location_name", "").strip(),
                    source_ref=ref,
                )
            )
        elif kind == "contents":
            if not self._require(row, ["record_id", "pallet_id", "lot_code", "recorded_at", "location_gln"], ref):
                return
            self._check_sscc(row["pallet_id"], ref, "pallet_id")
            self._check_gln(row["location_gln"], ref, "location_gln")
            quantity = _float_or_none(row.get("quantity"))
            if quantity is None:
                self._finding(
                    FindingType.QUANTITY_DISCREPANCY,
                    "pallet contents record has no quantity; quantity treated as unknown, not zero",
                    pallet_id=row["pallet_id"].strip(),
                    lot_code=row["lot_code"].strip(),
                    refs=[ref],
                )
            self.rs.contents.append(
                ContentsAssertion(
                    record_id=row["record_id"].strip(),
                    pallet_id=row["pallet_id"].strip(),
                    lot_code=row["lot_code"].strip(),
                    quantity=quantity,
                    unit_of_measure=row.get("unit_of_measure", "").strip(),
                    recorded_at=parse_ts(row["recorded_at"]),
                    location_gln=row["location_gln"].strip(),
                    location_name=row.get("location_name", "").strip(),
                    source_ref=ref,
                )
            )
        elif kind == "shipping":
            if not self._require(row, ["shipment_id", "pallet_id", "ship_from_gln", "ship_to_gln", "shipped_at"], ref):
                return
            self._check_sscc(row["pallet_id"], ref, "pallet_id")
            self._check_gln(row["ship_from_gln"], ref, "ship_from_gln")
            self._check_gln(row["ship_to_gln"], ref, "ship_to_gln")
            self.rs.shipments.append(
                Shipment(
                    shipment_id=row["shipment_id"].strip(),
                    pallet_id=row["pallet_id"].strip(),
                    from_gln=row["ship_from_gln"].strip(),
                    from_name=row.get("ship_from_name", "").strip(),
                    to_gln=row["ship_to_gln"].strip(),
                    to_name=row.get("ship_to_name", "").strip(),
                    shipped_at=parse_ts(row["shipped_at"]),
                    source_ref=ref,
                )
            )
        elif kind == "receiving":
            if not self._require(row, ["receipt_id", "pallet_id", "location_gln", "received_at"], ref):
                return
            self._check_sscc(row["pallet_id"], ref, "pallet_id")
            self._check_gln(row["location_gln"], ref, "location_gln")
            self.rs.receipts.append(
                Receipt(
                    receipt_id=row["receipt_id"].strip(),
                    shipment_ref=None if _blank(row.get("shipment_ref")) else row["shipment_ref"].strip(),
                    pallet_id=row["pallet_id"].strip(),
                    location_gln=row["location_gln"].strip(),
                    location_name=row.get("location_name", "").strip(),
                    received_at=parse_ts(row["received_at"]),
                    counted_quantity=_float_or_none(row.get("counted_quantity")),
                    unit_of_measure=row.get("unit_of_measure", "").strip(),
                    source_ref=ref,
                    corrections=list(applied),
                )
            )
        elif kind == "repack":
            if not self._require(
                row,
                ["record_id", "input_pallet_id", "output_pallet_id", "lot_code", "performed_at", "location_gln"],
                ref,
            ):
                return
            self._check_sscc(row["input_pallet_id"], ref, "input_pallet_id")
            self._check_sscc(row["output_pallet_id"], ref, "output_pallet_id")
            self._check_gln(row["location_gln"], ref, "location_gln")
            quantity = _float_or_none(row.get("quantity"))
            if quantity is None:
                self._finding(
                    FindingType.QUANTITY_DISCREPANCY,
                    "repack record has no quantity; quantity treated as unknown, not zero",
                    pallet_id=row["output_pallet_id"].strip(),
                    lot_code=row["lot_code"].strip(),
                    refs=[ref],
                )
            self.rs.repack_rows.append(
                RepackRow(
                    record_id=row["record_id"].strip(),
                    process_type=row.get("process_type", "").strip() or "repack",
                    input_pallet_id=row["input_pallet_id"].strip(),
                    output_pallet_id=row["output_pallet_id"].strip(),
                    lot_code=row["lot_code"].strip(),
                    quantity=quantity,
                    unit_of_measure=row.get("unit_of_measure", "").strip(),
                    performed_at=parse_ts(row["performed_at"]),
                    location_gln=row["location_gln"].strip(),
                    location_name=row.get("location_name", "").strip(),
                    source_ref=ref,
                )
            )
        else:  # pragma: no cover - guarded by FILE_SPECS
            raise ValueError(f"unknown record kind {kind}")


def load_fixture(fixture_dir: Path, case: str = "complete") -> RecordSet:
    """Load ``fixture_dir`` for ``case``. See :data:`CASES` for the variants."""
    return _Loader(Path(fixture_dir), case).load()
