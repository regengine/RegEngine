"""Build per-pallet custody timelines and detect every gap the evidence leaves.

The unit of custody is the pallet (SSCC). A pallet's contents are only ever
what a record asserts: a manufacturer pallet-build record, or the output side
of a repack record. Contents are never inferred from a shipment, a receipt, or
a quantity count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from .labels import FindingType
from .loader import parse_ts
from .records import ContentsAssertion, Finding, RecordSet, RepackRow, RequiredRecord, SourceRef, finding_id_for

_KIND_ORDER = {"contents": 0, "repack_out": 1, "received": 2, "shipped": 3, "repack_in": 4}


@dataclass
class PalletEvent:
    kind: str  # contents | repack_out | received | shipped | repack_in
    at: datetime
    location_gln: str
    location_name: str
    ref: SourceRef
    record: Any
    shipment_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "at": self.at.isoformat(),
            "location_gln": self.location_gln,
            "location_name": self.location_name,
            "shipment_id": self.shipment_id,
            "source_ref": self.ref.as_dict(),
        }


@dataclass
class ContentsGroup:
    """All lot rows asserted by one record for one pallet."""

    record_id: str
    recorded_at: datetime
    location_gln: str
    location_name: str
    lots: Dict[str, Optional[float]]
    unit_of_measure: str
    refs: List[SourceRef]
    derived_from: Tuple[str, ...] = ()
    process_type: Optional[str] = None

    @property
    def total(self) -> Optional[float]:
        if any(q is None for q in self.lots.values()):
            return None
        return float(sum(self.lots.values()))


@dataclass
class RepackOp:
    record_id: str
    process_type: str
    performed_at: datetime
    location_gln: str
    location_name: str
    inputs: List[str]
    outputs: Dict[str, Dict[str, Optional[float]]]
    unit_of_measure: str
    refs: List[SourceRef]


@dataclass
class PalletTimeline:
    pallet_id: str
    events: List[PalletEvent] = field(default_factory=list)
    contents_groups: List[ContentsGroup] = field(default_factory=list)
    parents: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    consumed_at: Optional[datetime] = None
    consumed_by_record: Optional[str] = None

    def sort(self) -> None:
        self.events.sort(key=lambda e: (e.at, _KIND_ORDER.get(e.kind, 9)))
        self.contents_groups.sort(key=lambda g: g.recorded_at)

    def contents_at(self, when: datetime) -> Optional[ContentsGroup]:
        latest: Optional[ContentsGroup] = None
        for group in self.contents_groups:
            if group.recorded_at <= when:
                latest = group
        return latest

    @property
    def latest_contents(self) -> Optional[ContentsGroup]:
        return self.contents_groups[-1] if self.contents_groups else None

    @property
    def movements(self) -> List[PalletEvent]:
        return [e for e in self.events if e.kind in ("shipped", "received")]

    @property
    def last_event(self) -> Optional[PalletEvent]:
        return self.events[-1] if self.events else None

    @property
    def is_terminal(self) -> bool:
        return self.consumed_at is None

    def last_location_before(self, when: datetime) -> Optional[PalletEvent]:
        chosen: Optional[PalletEvent] = None
        for event in self.events:
            if event.at < when:
                chosen = event
        return chosen


@dataclass
class CustodyModel:
    timelines: Dict[str, PalletTimeline]
    repack_ops: Dict[str, RepackOp]
    findings: List[Finding]

    def ancestors(self, pallet_id: str) -> List[str]:
        seen: List[str] = []
        stack = list(self.timelines[pallet_id].parents) if pallet_id in self.timelines else []
        while stack:
            current = stack.pop(0)
            if current in seen:
                continue
            seen.append(current)
            stack.extend(self.timelines[current].parents if current in self.timelines else [])
        return seen

    def findings_for(self, pallet_id: str, *, include_ancestors: bool = True) -> List[Finding]:
        scope = [pallet_id] + (self.ancestors(pallet_id) if include_ancestors else [])
        return [f for f in self.findings if f.pallet_id in scope or any(p in scope for p in f.related_pallet_ids)]

    def blocking_findings_for(self, pallet_id: str) -> List[Finding]:
        return [f for f in self.findings_for(pallet_id) if f.blocking]

    def lineage_lots(self, pallet_id: str) -> Set[str]:
        lots: Set[str] = set()
        for pid in [pallet_id] + self.ancestors(pallet_id):
            for group in self.timelines[pid].contents_groups:
                lots.update(group.lots.keys())
        return lots


class _Builder:
    def __init__(self, rs: RecordSet) -> None:
        self.rs = rs
        self.timelines: Dict[str, PalletTimeline] = {}
        self.repack_ops: Dict[str, RepackOp] = {}
        self.findings: List[Finding] = list(rs.load_findings)

    # -- helpers ------------------------------------------------------------
    def _tl(self, pallet_id: str) -> PalletTimeline:
        if pallet_id not in self.timelines:
            self.timelines[pallet_id] = PalletTimeline(pallet_id=pallet_id)
        return self.timelines[pallet_id]

    def _finding(
        self,
        ftype: FindingType,
        description: str,
        *,
        pallet_id: Optional[str] = None,
        lot_code: Optional[str] = None,
        refs: Optional[List[SourceRef]] = None,
        blocking: bool = True,
        required: Optional[RequiredRecord] = None,
        cutoff: Optional[Dict[str, str]] = None,
        related: Optional[List[str]] = None,
    ) -> Finding:
        finding = Finding(
            finding_id=finding_id_for(ftype, pallet_id, lot_code, description),
            type=ftype,
            pallet_id=pallet_id,
            lot_code=lot_code,
            description=description,
            blocking=blocking,
            source_refs=list(refs or []),
            required_record=required,
            attributed_to_cutoff=cutoff,
            related_pallet_ids=list(related or []),
        )
        self.findings.append(finding)
        return finding

    def _cutoff_before(self, when: datetime) -> Optional[Dict[str, str]]:
        """Return the unavailable source whose last sync precedes ``when``, if any."""
        for source, cutoff in sorted(self.rs.cutoffs.items()):
            if parse_ts(cutoff) < when:
                return {"source_system": source, "last_successful_sync_at": cutoff}
        return None

    # -- build steps --------------------------------------------------------
    def build(self) -> CustodyModel:
        self._add_contents_assertions()
        self._add_repacks()
        self._add_movements()
        for tl in self.timelines.values():
            tl.sort()
        self._check_handoffs()
        self._check_missing_contents()
        self._check_conflicting_contents()
        self._check_receipt_counts()
        self._note_cutoffs()
        return CustodyModel(timelines=self.timelines, repack_ops=self.repack_ops, findings=self.findings)

    def _add_contents_assertions(self) -> None:
        grouped: Dict[Tuple[str, str], List[ContentsAssertion]] = {}
        for assertion in self.rs.contents:
            grouped.setdefault((assertion.pallet_id, assertion.record_id), []).append(assertion)
        for (pallet_id, record_id), rows in grouped.items():
            first = rows[0]
            group = ContentsGroup(
                record_id=record_id,
                recorded_at=min(r.recorded_at for r in rows),
                location_gln=first.location_gln,
                location_name=first.location_name,
                lots={r.lot_code: (None if r.quantity is None else float(r.quantity)) for r in rows},
                unit_of_measure=first.unit_of_measure,
                refs=[r.source_ref for r in rows],
            )
            tl = self._tl(pallet_id)
            tl.contents_groups.append(group)
            tl.events.append(
                PalletEvent(
                    kind="contents",
                    at=group.recorded_at,
                    location_gln=group.location_gln,
                    location_name=group.location_name,
                    ref=group.refs[0],
                    record=group,
                )
            )

    def _add_repacks(self) -> None:
        by_record: Dict[str, List[RepackRow]] = {}
        for row in self.rs.repack_rows:
            by_record.setdefault(row.record_id, []).append(row)

        for record_id, rows in sorted(by_record.items(), key=lambda kv: min(r.performed_at for r in kv[1])):
            first = rows[0]
            op = RepackOp(
                record_id=record_id,
                process_type=first.process_type,
                performed_at=min(r.performed_at for r in rows),
                location_gln=first.location_gln,
                location_name=first.location_name,
                inputs=sorted({r.input_pallet_id for r in rows}),
                outputs={},
                unit_of_measure=first.unit_of_measure,
                refs=[r.source_ref for r in rows],
            )
            for row in rows:
                op.outputs.setdefault(row.output_pallet_id, {})
                lots = op.outputs[row.output_pallet_id]
                quantity = None if row.quantity is None else float(row.quantity)
                if row.lot_code in lots and lots[row.lot_code] is not None and quantity is not None:
                    lots[row.lot_code] = lots[row.lot_code] + quantity
                else:
                    lots[row.lot_code] = quantity
            self.repack_ops[record_id] = op

            # Consume inputs and reconcile per-lot quantities.
            input_totals: Dict[str, Optional[float]] = {}
            unknown_inputs: List[str] = []
            for pallet_id in op.inputs:
                tl = self._tl(pallet_id)
                if not tl.events and not tl.contents_groups:
                    self._finding(
                        FindingType.UNMATCHED_IDENTIFIER,
                        f"repack {record_id} names input pallet {pallet_id} that appears in no other record",
                        pallet_id=pallet_id,
                        refs=op.refs,
                        related=list(op.outputs),
                    )
                group = tl.contents_at(op.performed_at)
                if group is None:
                    unknown_inputs.append(pallet_id)
                    self._finding(
                        FindingType.MISSING_PALLET_CONTENTS,
                        f"repack {record_id} consumed pallet {pallet_id} but no record states what was on it",
                        pallet_id=pallet_id,
                        refs=op.refs,
                        related=list(op.outputs),
                        required=RequiredRecord(
                            "pallet contents record",
                            op.location_name,
                            op.location_gln,
                            None,
                            op.performed_at,
                            f"contents of pallet {pallet_id} before repack {record_id}",
                        ),
                    )
                else:
                    for lot, qty in group.lots.items():
                        if lot in input_totals and input_totals[lot] is not None and qty is not None:
                            input_totals[lot] = input_totals[lot] + qty
                        elif lot in input_totals and (input_totals[lot] is None or qty is None):
                            input_totals[lot] = None
                        else:
                            input_totals[lot] = qty
                tl.consumed_at = op.performed_at
                tl.consumed_by_record = record_id
                tl.children.extend(p for p in op.outputs if p not in tl.children)
                tl.events.append(
                    PalletEvent(
                        kind="repack_in",
                        at=op.performed_at,
                        location_gln=op.location_gln,
                        location_name=op.location_name,
                        ref=op.refs[0],
                        record=op,
                    )
                )

            output_totals: Dict[str, Optional[float]] = {}
            for pallet_id, lots in op.outputs.items():
                tl = self._tl(pallet_id)
                group = ContentsGroup(
                    record_id=record_id,
                    recorded_at=op.performed_at,
                    location_gln=op.location_gln,
                    location_name=op.location_name,
                    lots=dict(lots),
                    unit_of_measure=op.unit_of_measure,
                    refs=[r.source_ref for r in rows if r.output_pallet_id == pallet_id],
                    derived_from=tuple(op.inputs),
                    process_type=op.process_type,
                )
                tl.contents_groups.append(group)
                tl.parents.extend(p for p in op.inputs if p not in tl.parents)
                tl.events.append(
                    PalletEvent(
                        kind="repack_out",
                        at=op.performed_at,
                        location_gln=op.location_gln,
                        location_name=op.location_name,
                        ref=group.refs[0],
                        record=op,
                    )
                )
                for lot, qty in lots.items():
                    if lot in output_totals and output_totals[lot] is not None and qty is not None:
                        output_totals[lot] = output_totals[lot] + qty
                    elif lot in output_totals:
                        output_totals[lot] = None
                    else:
                        output_totals[lot] = qty

            if not unknown_inputs:
                mismatches = []
                for lot in sorted(set(input_totals) | set(output_totals)):
                    inp, out = input_totals.get(lot), output_totals.get(lot)
                    if inp is None or out is None or abs(inp - out) > 1e-9:
                        mismatches.append(f"{lot}: in={inp} out={out}")
                if mismatches:
                    self._finding(
                        FindingType.QUANTITY_DISCREPANCY,
                        f"repack {record_id} does not reconcile per lot ({'; '.join(mismatches)}); "
                        "output contents are recorded as asserted, not adjusted",
                        refs=op.refs,
                        related=op.inputs + list(op.outputs),
                    )

    def _add_movements(self) -> None:
        for shipment in self.rs.shipments:
            self._tl(shipment.pallet_id).events.append(
                PalletEvent(
                    kind="shipped",
                    at=shipment.shipped_at,
                    location_gln=shipment.from_gln,
                    location_name=shipment.from_name,
                    ref=shipment.source_ref,
                    record=shipment,
                    shipment_id=shipment.shipment_id,
                )
            )
        for receipt in self.rs.receipts:
            self._tl(receipt.pallet_id).events.append(
                PalletEvent(
                    kind="received",
                    at=receipt.received_at,
                    location_gln=receipt.location_gln,
                    location_name=receipt.location_name,
                    ref=receipt.source_ref,
                    record=receipt,
                    shipment_id=receipt.shipment_ref,
                )
            )

    def _check_handoffs(self) -> None:
        receipts_by_key = {(r.shipment_ref, r.pallet_id): r for r in self.rs.receipts if r.shipment_ref}
        shipments_by_key = {(s.shipment_id, s.pallet_id): s for s in self.rs.shipments}

        for (shipment_id, pallet_id), shipment in sorted(shipments_by_key.items()):
            if (shipment_id, pallet_id) in receipts_by_key:
                continue
            cutoff = self._cutoff_before(shipment.shipped_at)
            self._finding(
                FindingType.MISSING_HANDOFF_RECEIVING,
                f"shipment {shipment_id} shows pallet {pallet_id} leaving {shipment.from_name} for "
                f"{shipment.to_name}; no receiving record for that pallet references this shipment",
                pallet_id=pallet_id,
                refs=[shipment.source_ref],
                cutoff=cutoff,
                required=RequiredRecord(
                    "receiving record",
                    shipment.to_name,
                    shipment.to_gln,
                    shipment.shipped_at,
                    None,
                    f"receipt of pallet {pallet_id} against shipment {shipment_id}",
                ),
            )

        for receipt in sorted(self.rs.receipts, key=lambda r: (r.received_at, r.receipt_id)):
            tl = self.timelines[receipt.pallet_id]
            prior = tl.last_location_before(receipt.received_at)
            custodian = (prior.location_name, prior.location_gln) if prior else ("unknown shipper", "")
            if receipt.shipment_ref is None:
                self._finding(
                    FindingType.MISSING_HANDOFF_SHIPPING,
                    f"receipt {receipt.receipt_id} of pallet {receipt.pallet_id} at {receipt.location_name} "
                    "carries no shipment reference",
                    pallet_id=receipt.pallet_id,
                    refs=[receipt.source_ref],
                    required=RequiredRecord(
                        "shipping record",
                        custodian[0],
                        custodian[1],
                        None,
                        receipt.received_at,
                        f"shipment that delivered pallet {receipt.pallet_id} to "
                        f"{receipt.location_name}, or an attested correction naming it",
                    ),
                )
                continue
            if (receipt.shipment_ref, receipt.pallet_id) in shipments_by_key:
                continue
            cutoff = self._cutoff_before(receipt.received_at)
            if cutoff:
                self._finding(
                    FindingType.MISSING_HANDOFF_SHIPPING,
                    f"receipt {receipt.receipt_id} references shipment {receipt.shipment_ref} for pallet "
                    f"{receipt.pallet_id}; that shipping record is not in the reviewed evidence because "
                    f"{cutoff['source_system']} was last synchronized at {cutoff['last_successful_sync_at']}",
                    pallet_id=receipt.pallet_id,
                    refs=[receipt.source_ref],
                    cutoff=cutoff,
                    required=RequiredRecord(
                        "shipping record",
                        custodian[0],
                        custodian[1],
                        parse_ts(cutoff["last_successful_sync_at"]),
                        receipt.received_at,
                        f"shipment {receipt.shipment_ref} for pallet {receipt.pallet_id} "
                        f"(re-synchronize {cutoff['source_system']} or obtain the signed document)",
                    ),
                )
            else:
                self._finding(
                    FindingType.UNMATCHED_IDENTIFIER,
                    f"receipt {receipt.receipt_id} references shipment {receipt.shipment_ref} for pallet "
                    f"{receipt.pallet_id}, which no shipping record in the reviewed evidence contains",
                    pallet_id=receipt.pallet_id,
                    refs=[receipt.source_ref],
                    required=RequiredRecord(
                        "shipping record",
                        custodian[0],
                        custodian[1],
                        None,
                        receipt.received_at,
                        f"shipment {receipt.shipment_ref} listing pallet {receipt.pallet_id}",
                    ),
                )

    def _check_missing_contents(self) -> None:
        for pallet_id, tl in sorted(self.timelines.items()):
            movements = tl.movements
            if not movements or tl.contents_at(movements[0].at) is not None:
                continue
            first = movements[0]
            # Candidates: pallets last seen received at the same location, not consumed,
            # with no record after that receipt and before this pallet's first movement.
            candidates: List[PalletTimeline] = []
            for other in self.timelines.values():
                if other.pallet_id == pallet_id or not other.is_terminal:
                    continue
                last = other.last_event
                if last and last.kind == "received" and last.location_gln == first.location_gln and last.at < first.at:
                    candidates.append(other)
            after = max((c.last_event.at for c in candidates), default=None)
            candidate_text = (
                "; ".join(
                    f"{c.pallet_id} ({', '.join(f'{lot} {qty}' for lot, qty in (c.latest_contents.lots.items() if c.latest_contents else []))})"
                    for c in candidates
                )
                or "none identified"
            )
            required = RequiredRecord(
                "pallet contents or repack record",
                first.location_name,
                first.location_gln,
                after,
                first.at,
                f"what was on pallet {pallet_id} when it left {first.location_name}; pallets received there "
                f"with no subsequent record and therefore possible inputs: {candidate_text}",
            )
            self._finding(
                FindingType.MISSING_PALLET_CONTENTS,
                f"pallet {pallet_id} was moved ({first.kind} at {first.at.isoformat()} from {first.location_name}) "
                "but no record states its contents",
                pallet_id=pallet_id,
                refs=[first.ref],
                required=required,
                related=[c.pallet_id for c in candidates],
            )
            for candidate in candidates:
                last = candidate.last_event
                assert last is not None
                self._finding(
                    FindingType.MISSING_PALLET_CONTENTS,
                    f"pallet {candidate.pallet_id} was received at {last.location_name} and has no later record; "
                    f"it is a possible input to pallet {pallet_id}, whose contents are unrecorded",
                    pallet_id=candidate.pallet_id,
                    refs=[last.ref],
                    required=required,
                    related=[pallet_id],
                )

    def _check_conflicting_contents(self) -> None:
        for pallet_id, tl in sorted(self.timelines.items()):
            groups = tl.contents_groups
            for previous, current in zip(groups, groups[1:]):
                if current.derived_from:
                    continue  # a repack legitimately restates contents
                if previous.lots != current.lots:
                    self._finding(
                        FindingType.CONFLICTING_PALLET_CONTENTS,
                        f"records {previous.record_id} and {current.record_id} disagree about pallet {pallet_id}: "
                        f"{previous.lots} vs {current.lots}; neither is preferred",
                        pallet_id=pallet_id,
                        refs=previous.refs + current.refs,
                        required=RequiredRecord(
                            "pallet contents record",
                            current.location_name,
                            current.location_gln,
                            previous.recorded_at,
                            current.recorded_at,
                            f"a record that reconciles the two statements of pallet {pallet_id}",
                        ),
                    )

    def _check_receipt_counts(self) -> None:
        for receipt in self.rs.receipts:
            group = self.timelines[receipt.pallet_id].contents_at(receipt.received_at)
            if group is None:
                continue  # already a missing-contents finding
            asserted = group.total
            if receipt.counted_quantity is None:
                self._finding(
                    FindingType.QUANTITY_DISCREPANCY,
                    f"receipt {receipt.receipt_id} records no count for pallet {receipt.pallet_id}",
                    pallet_id=receipt.pallet_id,
                    refs=[receipt.source_ref],
                    blocking=False,
                )
            elif asserted is not None and abs(asserted - receipt.counted_quantity) > 1e-9:
                delta = receipt.counted_quantity - asserted
                self._finding(
                    FindingType.QUANTITY_DISCREPANCY,
                    f"receipt {receipt.receipt_id} counted {receipt.counted_quantity:g} on pallet {receipt.pallet_id}; "
                    f"records assert {asserted:g} (delta {delta:+g})",
                    pallet_id=receipt.pallet_id,
                    refs=[receipt.source_ref] + group.refs,
                    blocking=False,
                )

    def _note_cutoffs(self) -> None:
        for source, cutoff in sorted(self.rs.cutoffs.items()):
            retained = [f.name for f in self.rs.files.values() if f.source_system == source and f.available]
            missing = [f.name for f in self.rs.files.values() if f.source_system == source and not f.available]
            self._finding(
                FindingType.SOURCE_UNAVAILABLE_AFTER_CUTOFF,
                f"source {source} unavailable; last successful synchronization {cutoff}; retained files used: "
                f"{retained or 'none'}; not available: {missing or 'none'}. Movements recorded by {source} after "
                f"{cutoff} cannot be established from this package",
                blocking=False,
            )


def build_custody(rs: RecordSet) -> CustodyModel:
    return _Builder(rs).build()
