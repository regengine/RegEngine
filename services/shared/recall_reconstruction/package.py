"""Write the evidence package for one case and reconcile it against the answer key."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.canonical_event import CTEType, IngestionSource, ProvenanceMetadata, TraceabilityEvent
from shared.cte_persistence import compute_chain_hash

from .chain import CustodyModel, build_custody
from .labels import FindingType, LinkLabel
from .loader import CASES, load_fixture
from .records import RecordSet
from .worksheet import Worksheet, build_worksheet

ENGINE_VERSION = "0.1.0"
TENANT_ID = UUID("00000000-0000-0000-0000-00000000c0de")
RUN_STARTED_AT = datetime(2026, 8, 20, 18, 0, 0, tzinfo=timezone.utc)
_EVENT_NAMESPACE = uuid.UUID("6f1c2f1e-7d2a-4d8e-9c31-2b8a2b6a1a11")


def _canonical_events(rs: RecordSet, custody: CustodyModel) -> Dict[str, Any]:
    """Canonicalize every movement whose contents are known into the production event model.

    A movement of a pallet with unrecorded contents cannot be expressed as a
    lot-keyed event without inventing a lot code, so it is listed under
    ``not_canonicalized`` with the reason instead.
    """
    events: List[TraceabilityEvent] = []
    skipped: List[Dict[str, Any]] = []
    products = rs.product_by_lot

    def make(
        event_type: CTEType,
        ref,
        lot: str,
        quantity: Optional[float],
        uom: str,
        when: datetime,
        from_gln: Optional[str],
        from_name: Optional[str],
        to_gln: Optional[str],
        to_name: Optional[str],
        kdes: Dict[str, Any],
    ) -> None:
        if quantity is None:
            skipped.append(
                {
                    "source_ref": ref.as_dict(),
                    "lot_code": lot,
                    "reason": "quantity unknown; canonical event requires a quantity",
                }
            )
            return
        product = products.get(lot)
        events.append(
            TraceabilityEvent(
                # Content-addressed: the same source row yields the same event id in every
                # case and every run, so evidence captured before a sync cutoff reproduces
                # byte-for-byte (ids, hashes, chain) from the retained snapshot.
                event_id=uuid.uuid5(_EVENT_NAMESPACE, f"{ref.file_sha256}|{ref.short()}|{lot}|{event_type.value}"),
                tenant_id=TENANT_ID,
                source_system=IngestionSource.CSV_UPLOAD,
                source_record_id=ref.short(),
                event_type=event_type,
                event_timestamp=when,
                product_reference=product.product_description if product else None,
                lot_reference=lot,
                traceability_lot_code=lot,
                quantity=float(quantity),
                unit_of_measure=uom or "cases",
                from_entity_reference=from_name,
                to_entity_reference=to_name,
                from_facility_reference=from_gln,
                to_facility_reference=to_gln,
                kdes=kdes,
                raw_payload={"source_ref": ref.as_dict()},
                provenance_metadata=ProvenanceMetadata(
                    source_file_hash=ref.file_sha256,
                    source_file_name=ref.file,
                    mapper_name="recall_reconstruction",
                    mapper_version=ENGINE_VERSION,
                    original_format="csv",
                    ingestion_timestamp=RUN_STARTED_AT.isoformat(),
                ),
                ingested_at=RUN_STARTED_AT,
                created_at=RUN_STARTED_AT,
            )
        )

    for shipment in rs.shipments:
        group = custody.timelines[shipment.pallet_id].contents_at(shipment.shipped_at)
        if group is None:
            skipped.append(
                {
                    "source_ref": shipment.source_ref.as_dict(),
                    "pallet_id": shipment.pallet_id,
                    "reason": "pallet contents unrecorded at time of shipment",
                }
            )
            continue
        for lot, qty in group.lots.items():
            make(
                CTEType.SHIPPING,
                shipment.source_ref,
                lot,
                qty,
                group.unit_of_measure,
                shipment.shipped_at,
                shipment.from_gln,
                shipment.from_name,
                shipment.to_gln,
                shipment.to_name,
                {
                    "pallet_id": shipment.pallet_id,
                    "shipment_id": shipment.shipment_id,
                    "ship_from_gln": shipment.from_gln,
                    "ship_to_gln": shipment.to_gln,
                    "ship_date": shipment.shipped_at.date().isoformat(),
                    "reference_document": shipment.shipment_id,
                    "reference_document_number": shipment.shipment_id,
                },
            )
    for receipt in rs.receipts:
        group = custody.timelines[receipt.pallet_id].contents_at(receipt.received_at)
        if group is None:
            skipped.append(
                {
                    "source_ref": receipt.source_ref.as_dict(),
                    "pallet_id": receipt.pallet_id,
                    "reason": "pallet contents unrecorded at time of receipt",
                }
            )
            continue
        prior = custody.timelines[receipt.pallet_id].last_location_before(receipt.received_at)
        for lot, qty in group.lots.items():
            make(
                CTEType.RECEIVING,
                receipt.source_ref,
                lot,
                qty,
                group.unit_of_measure,
                receipt.received_at,
                prior.location_gln if prior else None,
                prior.location_name if prior else None,
                receipt.location_gln,
                receipt.location_name,
                {
                    "pallet_id": receipt.pallet_id,
                    "receipt_id": receipt.receipt_id,
                    "shipment_ref": receipt.shipment_ref,
                    "counted_quantity": receipt.counted_quantity,
                    "receive_date": receipt.received_at.date().isoformat(),
                    "receiving_location": receipt.location_name,
                    "immediate_previous_source": prior.location_name if prior else None,
                    "reference_document": receipt.receipt_id,
                    "reference_document_number": receipt.receipt_id,
                    "corrections_applied": [c.correction_id for c in receipt.corrections],
                },
            )
    for row in rs.repack_rows:
        make(
            CTEType.TRANSFORMATION,
            row.source_ref,
            row.lot_code,
            row.quantity,
            row.unit_of_measure,
            row.performed_at,
            row.location_gln,
            row.location_name,
            row.location_gln,
            row.location_name,
            {
                "pallet_id": row.output_pallet_id,
                "input_pallet_id": row.input_pallet_id,
                "process_type": row.process_type,
                "input_lot_codes": [row.lot_code],
                "input_traceability_lot_codes": [row.lot_code],
                "transformation_date": row.performed_at.date().isoformat(),
                "reference_document": row.record_id,
                "reference_document_number": row.record_id,
            },
        )

    events.sort(key=lambda e: (e.event_timestamp, e.source_record_id or "", e.traceability_lot_code))
    previous: Optional[str] = None
    for event in events:
        event.prepare_for_persistence()
        assert event.sha256_hash
        event.chain_hash = compute_chain_hash(event.sha256_hash, previous)
        previous = event.chain_hash
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "not_canonicalized": skipped,
        "last_chain_hash": previous,
    }


def reconcile(worksheet: Worksheet, custody: CustodyModel, rs: RecordSet, answer_key: Dict[str, Any]) -> Dict[str, Any]:
    """Check the worksheet against the answer key's expectations for this case."""
    checks: List[Dict[str, Any]] = []
    expectations = answer_key.get("case_expectations", {}).get(rs.case, {})
    rows_by_key = {f"{r.pallet_id}|{r.lot_code or ''}": r for r in worksheet.rows}
    finding_types = {f.type.value for f in custody.findings}

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    for key, expected in expectations.get("expected_labels", {}).items():
        row = rows_by_key.get(key)
        check(
            f"label:{key}",
            row is not None and row.label.value == expected,
            f"expected {expected}, got {row.label.value if row else 'no row'}",
        )

    for forbidden in expectations.get("forbidden_labels", []):
        offenders = [k for k, r in rows_by_key.items() if r.label.value == forbidden]
        check(f"no_rows_labelled:{forbidden}", not offenders, f"rows: {offenders or 'none'}")

    summary = worksheet.summary()
    for lot, by_dest in expectations.get("linked_totals_by_destination", {}).items():
        actual = summary["linked_quantity_by_lot_and_destination"].get(lot, {})
        check(
            f"linked_totals:{lot}",
            actual == {k: float(v) for k, v in by_dest.items()},
            f"expected {by_dest}, got {actual}",
        )

    for ftype in expectations.get("expected_finding_types", []):
        check(f"finding_present:{ftype}", ftype in finding_types, f"findings: {sorted(finding_types)}")
    for ftype in expectations.get("forbidden_finding_types", []):
        check(f"finding_absent:{ftype}", ftype not in finding_types, f"findings: {sorted(finding_types)}")

    for pallet_id in expectations.get("unresolved_pallets", []):
        rows = [r for r in worksheet.rows if r.pallet_id == pallet_id]
        check(
            f"unresolved:{pallet_id}",
            bool(rows) and all(r.label is LinkLabel.UNRESOLVED for r in rows),
            f"labels: {[r.label.value for r in rows]}",
        )

    for pallet_id, mentions in expectations.get("required_record_mentions", {}).items():
        sentences = [
            f.required_record.sentence() for f in custody.findings if f.pallet_id == pallet_id and f.required_record
        ]
        for mention in mentions:
            check(
                f"required_record_mentions:{pallet_id}:{mention}",
                any(mention in s for s in sentences),
                f"sentences: {sentences}",
            )

    for source, cutoff in expectations.get("cutoffs", {}).items():
        check(f"cutoff:{source}", rs.cutoffs.get(source) == cutoff, f"cutoffs: {rs.cutoffs}")

    for correction_id in expectations.get("corrections_applied", []):
        applied = any(c.correction_id == correction_id and c.applied for c in rs.corrections)
        check(
            f"correction_applied:{correction_id}",
            applied,
            f"corrections: {[(c.correction_id, c.applied, c.not_applied_reason) for c in rs.corrections]}",
        )

    truth = answer_key.get("ground_truth", {})
    if expectations.get("verify_ground_truth_totals"):
        for lot, lot_truth in truth.get("lots", {}).items():
            for dest_gln, dest_truth in lot_truth.get("by_destination", {}).items():
                actual = summary["linked_quantity_by_lot_and_destination"].get(lot, {}).get(dest_gln)
                if lot == worksheet.implicated_lot:
                    check(
                        f"ground_truth:{lot}:{dest_gln}",
                        actual == float(dest_truth["shipped"]),
                        f"answer key says {dest_truth['shipped']} shipped; linked rows total {actual}",
                    )

    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def build_package(
    rs: RecordSet,
    custody: CustodyModel,
    worksheet: Worksheet,
    output_dir: Path,
    answer_key: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}

    def write(name: str, text: str) -> None:
        path = output_dir / name
        path.write_text(text, encoding="utf-8")
        files[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    write("worksheet.csv", worksheet.to_csv())
    write("worksheet.json", worksheet.to_json())
    write("findings.json", json.dumps([f.as_dict() for f in custody.findings], indent=2, sort_keys=True))
    write("corrections.json", json.dumps([c.as_dict() for c in rs.corrections], indent=2, sort_keys=True))
    canonical = _canonical_events(rs, custody)
    write("canonical_events.json", json.dumps(canonical, indent=2, sort_keys=True))
    write(
        "custody.json",
        json.dumps(
            {
                pid: {
                    "events": [e.as_dict() for e in tl.events],
                    "contents": [
                        {
                            "record_id": g.record_id,
                            "recorded_at": g.recorded_at.isoformat(),
                            "lots": g.lots,
                            "unit_of_measure": g.unit_of_measure,
                            "derived_from": list(g.derived_from),
                            "process_type": g.process_type,
                            "source_refs": [r.as_dict() for r in g.refs],
                        }
                        for g in tl.contents_groups
                    ],
                    "parents": tl.parents,
                    "children": tl.children,
                    "consumed_at": tl.consumed_at.isoformat() if tl.consumed_at else None,
                    "consumed_by_record": tl.consumed_by_record,
                }
                for pid, tl in sorted(custody.timelines.items())
            },
            indent=2,
            sort_keys=True,
        ),
    )

    reconciliation = reconcile(worksheet, custody, rs, answer_key) if answer_key else None
    if reconciliation is not None:
        write("answer_key_reconciliation.json", json.dumps(reconciliation, indent=2, sort_keys=True))

    manifest: Dict[str, Any] = {
        "engine": {"name": "recall_reconstruction", "version": ENGINE_VERSION},
        "case": rs.case,
        "case_description": CASES[rs.case]["description"],
        "generated_at": RUN_STARTED_AT.isoformat(),
        "tenant_id": str(TENANT_ID),
        "implicated_lot": worksheet.implicated_lot,
        "fixture_dir": rs.fixture_dir,
        "sources": {name: sf.as_dict() for name, sf in sorted(rs.files.items())},
        "last_successful_sync_by_source": {
            source: rs.sync_manifest.get("sources", {}).get(source, {}).get("last_successful_sync_at")
            for source in sorted(rs.sync_manifest.get("sources", {}))
        },
        "unavailable_sources": {
            source: {
                "last_successful_sync_at": cutoff,
                "statement": f"{source} was not reachable; records are reproduced from the retained copy "
                f"synchronized at {cutoff}. Movements recorded by {source} after that time are "
                "not in this package.",
            }
            for source, cutoff in sorted(rs.cutoffs.items())
        },
        "corrections_applied": [c.as_dict() for c in rs.corrections if c.applied],
        "corrections_not_applied": [c.as_dict() for c in rs.corrections if not c.applied],
        "findings_by_type": {ftype.value: sum(1 for f in custody.findings if f.type is ftype) for ftype in FindingType},
        "blocking_findings": sum(1 for f in custody.findings if f.blocking),
        "worksheet_summary": worksheet.summary(),
        "canonical_events": {
            "count": len(canonical["events"]),
            "not_canonicalized": len(canonical["not_canonicalized"]),
            "last_chain_hash": canonical["last_chain_hash"],
        },
        "reconciliation": reconciliation,
        "files": files,
    }
    manifest["package_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return manifest


def run_case(fixture_dir: Path, case: str, output_dir: Path, implicated_lot: Optional[str] = None) -> Dict[str, Any]:
    """Load, reconstruct, package, and reconcile one case. Returns the manifest."""
    fixture_dir = Path(fixture_dir)
    answer_key_path = fixture_dir / "answer_key.json"
    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8")) if answer_key_path.exists() else None
    lot = implicated_lot or (answer_key or {}).get("implicated_lot")
    if not lot:
        raise ValueError("implicated_lot must be given or present in answer_key.json")
    rs = load_fixture(fixture_dir, case)
    custody = build_custody(rs)
    worksheet = build_worksheet(rs, custody, lot)
    return build_package(rs, custody, worksheet, Path(output_dir), answer_key)
