"""Typed source records. Every record carries the file, row, and hash it came from."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .labels import FindingType


def finding_id_for(ftype: FindingType, pallet_id: Optional[str], lot_code: Optional[str], description: str) -> str:
    """Stable id derived from content, so the same gap gets the same id in every run and case."""
    digest = hashlib.sha256(f"{ftype.value}|{pallet_id or ''}|{lot_code or ''}|{description}".encode("utf-8"))
    return f"F-{digest.hexdigest()[:10]}"


@dataclass(frozen=True)
class SourceRef:
    file: str
    row_number: int
    record_id: str
    file_sha256: str
    source_system: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def short(self) -> str:
        return f"{self.file}#row{self.row_number}({self.record_id})"


@dataclass
class SourceFile:
    name: str
    source_system: str
    available: bool
    path: Optional[str] = None
    sha256: Optional[str] = None
    synced_at: Optional[str] = None
    retained_from: Optional[str] = None
    unavailable_reason: Optional[str] = None
    row_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LotRecord:
    lot_code: str
    gtin: str
    product_description: str
    quantity: Optional[float]
    unit_of_measure: str
    produced_at: datetime
    location_gln: str
    location_name: str
    source_ref: SourceRef


@dataclass
class ContentsAssertion:
    """A claim that ``quantity`` of ``lot_code`` was on ``pallet_id`` at ``recorded_at``."""

    record_id: str
    pallet_id: str
    lot_code: str
    quantity: Optional[float]
    unit_of_measure: str
    recorded_at: datetime
    location_gln: str
    location_name: str
    source_ref: SourceRef
    derived_from: Tuple[str, ...] = ()
    process_type: Optional[str] = None


@dataclass
class Shipment:
    shipment_id: str
    pallet_id: str
    from_gln: str
    from_name: str
    to_gln: str
    to_name: str
    shipped_at: datetime
    source_ref: SourceRef


@dataclass
class Receipt:
    receipt_id: str
    shipment_ref: Optional[str]
    pallet_id: str
    location_gln: str
    location_name: str
    received_at: datetime
    counted_quantity: Optional[float]
    unit_of_measure: str
    source_ref: SourceRef
    corrections: List["ManualCorrection"] = field(default_factory=list)


@dataclass
class RepackRow:
    record_id: str
    process_type: str
    input_pallet_id: str
    output_pallet_id: str
    lot_code: str
    quantity: Optional[float]
    unit_of_measure: str
    performed_at: datetime
    location_gln: str
    location_name: str
    source_ref: SourceRef


@dataclass
class ManualCorrection:
    correction_id: str
    target_file: str
    target_record_id: str
    field: str
    value: str
    author: str
    reason: str
    evidence_ref: str
    asserted_at: datetime
    source_ref: SourceRef
    applied: bool = False
    not_applied_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["asserted_at"] = self.asserted_at.isoformat()
        return data


@dataclass
class RequiredRecord:
    """The precise record that would resolve a finding."""

    record_type: str
    custodian: str
    location_gln: str
    after: Optional[datetime]
    before: Optional[datetime]
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "record_type": self.record_type,
            "custodian": self.custodian,
            "location_gln": self.location_gln,
            "after": self.after.isoformat() if self.after else None,
            "before": self.before.isoformat() if self.before else None,
            "detail": self.detail,
        }

    def sentence(self) -> str:
        window = ""
        if self.after and self.before:
            window = f" between {self.after.isoformat()} and {self.before.isoformat()}"
        elif self.after:
            window = f" after {self.after.isoformat()}"
        elif self.before:
            window = f" before {self.before.isoformat()}"
        return f"{self.record_type} from {self.custodian} (GLN {self.location_gln}){window}: {self.detail}"


@dataclass
class Finding:
    finding_id: str
    type: FindingType
    pallet_id: Optional[str]
    lot_code: Optional[str]
    description: str
    blocking: bool
    source_refs: List[SourceRef] = field(default_factory=list)
    required_record: Optional[RequiredRecord] = None
    attributed_to_cutoff: Optional[Dict[str, str]] = None
    related_pallet_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "type": self.type.value,
            "pallet_id": self.pallet_id,
            "lot_code": self.lot_code,
            "description": self.description,
            "blocking": self.blocking,
            "source_refs": [ref.as_dict() for ref in self.source_refs],
            "required_record": self.required_record.as_dict() if self.required_record else None,
            "attributed_to_cutoff": self.attributed_to_cutoff,
            "related_pallet_ids": list(self.related_pallet_ids),
        }


@dataclass
class RecordSet:
    case: str
    fixture_dir: str
    files: Dict[str, SourceFile]
    lots: List[LotRecord] = field(default_factory=list)
    contents: List[ContentsAssertion] = field(default_factory=list)
    shipments: List[Shipment] = field(default_factory=list)
    receipts: List[Receipt] = field(default_factory=list)
    repack_rows: List[RepackRow] = field(default_factory=list)
    corrections: List[ManualCorrection] = field(default_factory=list)
    load_findings: List[Finding] = field(default_factory=list)
    cutoffs: Dict[str, str] = field(default_factory=dict)
    sync_manifest: Dict[str, Any] = field(default_factory=dict)

    @property
    def product_by_lot(self) -> Dict[str, LotRecord]:
        return {lot.lot_code: lot for lot in self.lots}
