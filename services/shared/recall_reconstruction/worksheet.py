"""Turn a custody model into the reviewer worksheet.

One row per (terminal pallet, lot). A terminal pallet is one no repack record
has consumed. Each row carries exactly one :class:`LinkLabel`, the records
that support it, and the records that would resolve it.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .chain import CustodyModel, PalletTimeline
from .labels import LinkLabel
from .records import RecordSet, SourceRef


@dataclass
class WorksheetRow:
    pallet_id: str
    lot_code: Optional[str]
    product_description: Optional[str]
    gtin: Optional[str]
    quantity_asserted: Optional[float]
    unit_of_measure: Optional[str]
    quantity_counted_at_last_receipt: Optional[float]
    last_record_type: Optional[str]
    last_recorded_at: Optional[str]
    last_recorded_location: Optional[str]
    last_recorded_location_gln: Optional[str]
    destination: Optional[str]
    destination_gln: Optional[str]
    label: LinkLabel
    co_palletized_with_implicated_lot: bool
    lineage_includes_implicated_lot: bool
    lineage: List[str]
    supporting_records: List[SourceRef]
    finding_ids: List[str]
    unresolved_questions: List[str]
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        data = {
            "pallet_id": self.pallet_id,
            "lot_code": self.lot_code,
            "product_description": self.product_description,
            "gtin": self.gtin,
            "quantity_asserted": self.quantity_asserted,
            "unit_of_measure": self.unit_of_measure,
            "quantity_counted_at_last_receipt": self.quantity_counted_at_last_receipt,
            "last_record_type": self.last_record_type,
            "last_recorded_at": self.last_recorded_at,
            "last_recorded_location": self.last_recorded_location,
            "last_recorded_location_gln": self.last_recorded_location_gln,
            "destination": self.destination,
            "destination_gln": self.destination_gln,
            "label": self.label.value,
            "co_palletized_with_implicated_lot": self.co_palletized_with_implicated_lot,
            "lineage_includes_implicated_lot": self.lineage_includes_implicated_lot,
            "lineage": list(self.lineage),
            "supporting_records": [ref.as_dict() for ref in self.supporting_records],
            "finding_ids": list(self.finding_ids),
            "unresolved_questions": list(self.unresolved_questions),
            "notes": list(self.notes),
        }
        return data


CSV_COLUMNS = [
    "label",
    "lot_code",
    "pallet_id",
    "product_description",
    "gtin",
    "quantity_asserted",
    "unit_of_measure",
    "quantity_counted_at_last_receipt",
    "last_record_type",
    "last_recorded_at",
    "last_recorded_location",
    "last_recorded_location_gln",
    "destination",
    "destination_gln",
    "co_palletized_with_implicated_lot",
    "lineage_includes_implicated_lot",
    "lineage",
    "supporting_records",
    "finding_ids",
    "unresolved_questions",
    "notes",
]


@dataclass
class Worksheet:
    implicated_lot: str
    case: str
    rows: List[WorksheetRow]

    def summary(self) -> Dict[str, Any]:
        by_label: Dict[str, int] = {label.value: 0 for label in LinkLabel}
        linked_by_destination: Dict[str, Dict[str, float]] = {}
        unresolved_quantity_by_lot: Dict[str, float] = {}
        unresolved_pallets: List[str] = []
        for row in self.rows:
            by_label[row.label.value] += 1
            if row.label is LinkLabel.LINKED and row.lot_code and row.quantity_asserted is not None:
                dest = row.destination_gln or "no destination recorded"
                linked_by_destination.setdefault(row.lot_code, {})
                linked_by_destination[row.lot_code][dest] = (
                    linked_by_destination[row.lot_code].get(dest, 0.0) + row.quantity_asserted
                )
            if row.label is LinkLabel.UNRESOLVED:
                if row.pallet_id not in unresolved_pallets:
                    unresolved_pallets.append(row.pallet_id)
                if row.lot_code and row.quantity_asserted is not None:
                    unresolved_quantity_by_lot[row.lot_code] = (
                        unresolved_quantity_by_lot.get(row.lot_code, 0.0) + row.quantity_asserted
                    )
        return {
            "implicated_lot": self.implicated_lot,
            "case": self.case,
            "rows": len(self.rows),
            "rows_by_label": by_label,
            "linked_quantity_by_lot_and_destination": linked_by_destination,
            "unresolved_quantity_by_lot": unresolved_quantity_by_lot,
            "unresolved_pallets": unresolved_pallets,
            "statement": (
                "Labels describe the reviewed evidence only. 'no_link_established' is not a finding that product "
                "is safe, and 'unresolved' quantities must be treated as potentially implicated until the named "
                "record is obtained. Recall scope is a practitioner decision."
            ),
        }

    def to_json(self) -> str:
        return json.dumps(
            {"summary": self.summary(), "rows": [r.as_dict() for r in self.rows]}, indent=2, sort_keys=True
        )

    def to_csv(self) -> str:
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in self.rows:
            data = row.as_dict()
            data["lineage"] = " > ".join(row.lineage)
            data["supporting_records"] = " | ".join(ref.short() for ref in row.supporting_records)
            data["finding_ids"] = " ".join(row.finding_ids)
            data["unresolved_questions"] = " || ".join(row.unresolved_questions)
            data["notes"] = " || ".join(row.notes)
            writer.writerow({col: data[col] for col in CSV_COLUMNS})
        return out.getvalue()


def _supporting_records(custody: CustodyModel, tl: PalletTimeline) -> List[SourceRef]:
    refs: List[SourceRef] = []

    def add(ref: SourceRef) -> None:
        if ref not in refs:
            refs.append(ref)

    for pid in [tl.pallet_id] + custody.ancestors(tl.pallet_id):
        other = custody.timelines[pid]
        for group in other.contents_groups:
            for ref in group.refs:
                add(ref)
        for event in other.events:
            add(event.ref)
            record = event.record
            for correction in getattr(record, "corrections", []) or []:
                add(correction.source_ref)
    return refs


def build_worksheet(rs: RecordSet, custody: CustodyModel, implicated_lot: str) -> Worksheet:
    products = rs.product_by_lot
    rows: List[WorksheetRow] = []

    for pallet_id in sorted(custody.timelines):
        tl = custody.timelines[pallet_id]
        if not tl.is_terminal:
            continue
        last = tl.last_event
        group = tl.latest_contents
        blocking = custody.blocking_findings_for(pallet_id)
        all_findings = custody.findings_for(pallet_id)
        lineage = custody.ancestors(pallet_id)
        lineage_lots = custody.lineage_lots(pallet_id)
        supporting = _supporting_records(custody, tl)

        last_receipt_count: Optional[float] = None
        for event in reversed(tl.events):
            if event.kind == "received":
                last_receipt_count = event.record.counted_quantity
                break

        destination: Optional[str] = None
        destination_gln: Optional[str] = None
        notes: List[str] = []
        if last is not None and last.kind == "received":
            destination, destination_gln = last.location_name, last.location_gln
        elif last is not None and last.kind == "shipped":
            destination = f"{last.record.to_name} (receipt not recorded)"
            destination_gln = last.record.to_gln
        elif last is not None:
            notes.append("no shipment or receipt recorded for this pallet")

        questions: List[str] = []
        for finding in blocking:
            text = finding.required_record.sentence() if finding.required_record else finding.description
            if text not in questions:
                questions.append(text)
        for finding in all_findings:
            if not finding.blocking and finding.description not in notes:
                notes.append(finding.description)
        for correction in [c for c in rs.corrections if c.applied and c.source_ref in supporting]:
            note = (
                f"manual correction {correction.correction_id} applied to {correction.target_record_id}."
                f"{correction.field}={correction.value!r} by {correction.author}: {correction.reason} "
                f"[evidence: {correction.evidence_ref}]"
            )
            if note not in notes:
                notes.append(note)

        common = dict(
            pallet_id=pallet_id,
            last_record_type=last.kind if last else None,
            last_recorded_at=last.at.isoformat() if last else None,
            last_recorded_location=last.location_name if last else None,
            last_recorded_location_gln=last.location_gln if last else None,
            destination=destination,
            destination_gln=destination_gln,
            lineage=lineage,
            supporting_records=supporting,
            finding_ids=[f.finding_id for f in all_findings],
            unresolved_questions=questions,
            notes=notes,
            quantity_counted_at_last_receipt=last_receipt_count,
        )

        if group is None:
            rows.append(
                WorksheetRow(
                    lot_code=None,
                    product_description=None,
                    gtin=None,
                    quantity_asserted=None,
                    unit_of_measure=None,
                    label=LinkLabel.UNRESOLVED,
                    co_palletized_with_implicated_lot=False,
                    lineage_includes_implicated_lot=implicated_lot in lineage_lots,
                    **common,
                )
            )
            continue

        for lot_code, quantity in sorted(group.lots.items()):
            product = products.get(lot_code)
            if blocking:
                label = LinkLabel.UNRESOLVED
            elif lot_code == implicated_lot:
                label = LinkLabel.LINKED
            else:
                label = LinkLabel.NO_LINK_ESTABLISHED
            rows.append(
                WorksheetRow(
                    lot_code=lot_code,
                    product_description=product.product_description if product else None,
                    gtin=product.gtin if product else None,
                    quantity_asserted=quantity,
                    unit_of_measure=group.unit_of_measure,
                    label=label,
                    co_palletized_with_implicated_lot=(lot_code != implicated_lot and implicated_lot in group.lots),
                    lineage_includes_implicated_lot=(lot_code != implicated_lot and implicated_lot in lineage_lots),
                    **common,
                )
            )

    return Worksheet(implicated_lot=implicated_lot, case=rs.case, rows=rows)
