import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileSpreadsheet, Database, ShieldCheck, type LucideIcon } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Proof: CSV → CTE → FDA row | RegEngine",
  description:
    "How a supplier CSV becomes an FDA-oriented sortable record. Three CTEs, three transformations, real production code.",
  openGraph: {
    title: "How a supplier CSV becomes an FDA-oriented sortable record | RegEngine",
    description:
      "Three CTEs, three transformations. Real production code.",
    url: "https://regengine.co/proof/transformation",
    type: "website",
  },
};

// ---------------------------------------------------------------------------
// Structural walkthrough — no records, only shapes and field mappings
// ---------------------------------------------------------------------------
// CSV headers match the column spec the ingestion pipeline accepts.
// Canonical JSON shows the TraceabilityEvent shape from
// services/shared/canonical_event.py with field-level placeholders, not values.
// FDA rows name the column spec in
// services/ingestion/app/fda_export_service.py (FDA_COLUMNS, _NAMED_KDE_COLUMNS)
// and note where each column's value comes from. PII columns pass through
// _redact_location_value when include_pii=False (#1219).

type Step = {
  cte: string;
  title: string;
  subtitle: string;
  csvHeader: string;
  csvNote: string;
  canonical: string;
  canonicalAnnotation: string;
  fdaRow: Array<[string, string]>;
  fdaAnnotation: string;
};

const STEPS: Step[] = [
  {
    cte: "§1.1330",
    title: "Harvesting",
    subtitle:
      "Origination event. Defines the Traceability Lot Code that follows the product through every downstream CTE.",
    csvHeader:
      "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,location_gln,field_id,harvester_name,reference_document",
    csvNote:
      "One row per harvesting event. Your values populate these columns; nothing is pre-filled.",
    canonical: `{
  "event_id": "<uuid, generated on ingest>",
  "tenant_id": "<your tenant id>",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "harvesting",
  "event_timestamp": "<harvest_date, ISO 8601>",
  "traceability_lot_code": "<traceability_lot_code>",
  "product_reference": "<product_description>",
  "quantity": <quantity>,
  "unit_of_measure": "<unit_of_measure>",
  "from_facility_reference": "<location_gln>",
  "kdes": {
    "harvest_date": "<harvest_date>",
    "growing_area_name": "<field_id>",
    "harvester_name": "<harvester_name>",
    "reference_document_number": "<reference_document>",
    "location_name": "<location_name>"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "<SHA-256 of the canonical record>",
  "chain_hash": "<hash chained to the previous event>"
}`,
    canonicalAnnotation:
      "KDE validation against §1.1330 (a)(1) through (a)(7). Hash chained to previous event.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "← traceability_lot_code"],
      ["Product Description", "← product_description"],
      ["Quantity", "← quantity"],
      ["Unit of Measure", "← unit_of_measure"],
      ["Event Type (CTE)", "harvesting"],
      ["Event Date", "← harvest_date"],
      ["Event Time", "from event_timestamp"],
      ["Location GLN", "← location_gln"],
      ["Location Name", "← location_name"],
      ["Harvest Date", "← harvest_date"],
      ["Growing Area", "← field_id"],
      ["Reference Document Number", "← reference_document"],
      ["Source Document", "your uploaded file name"],
      ["Record Hash (SHA-256)", "computed from the canonical record"],
      ["Chain Hash", "chains this record to the previous one"],
    ],
    fdaAnnotation:
      "Mapped to FDA harvesting columns (TLC, Harvest Date, Growing Area). Cells pass through sanitize_cell to neutralize spreadsheet-formula injection (#1081).",
  },
  {
    cte: "§1.1325",
    title: "Cooling",
    subtitle:
      "Pre-shipment temperature event. Carries the same TLC. Adds the cooling KDE the FDA requires for produce.",
    csvHeader:
      "traceability_lot_code,product_description,quantity,unit_of_measure,cooling_date,location_name,location_gln,temperature_celsius,reference_document",
    csvNote:
      "One row per cooling event. The TLC column links each row back to its harvesting event.",
    canonical: `{
  "event_id": "<uuid, generated on ingest>",
  "tenant_id": "<your tenant id>",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "cooling",
  "event_timestamp": "<cooling_date, ISO 8601>",
  "traceability_lot_code": "<traceability_lot_code>",
  "product_reference": "<product_description>",
  "quantity": <quantity>,
  "unit_of_measure": "<unit_of_measure>",
  "from_facility_reference": "<location_gln>",
  "kdes": {
    "cooling_date": "<cooling_date>",
    "temperature": "<temperature_celsius, normalized to °F>",
    "location_name": "<location_name>",
    "reference_document_number": "<reference_document>"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "<SHA-256 of the canonical record>",
  "chain_hash": "<hash chained to the previous event>"
}`,
    canonicalAnnotation:
      "Celsius normalized to Fahrenheit. TLC linkage proves continuity from harvest.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "← traceability_lot_code"],
      ["Product Description", "← product_description"],
      ["Quantity", "← quantity"],
      ["Unit of Measure", "← unit_of_measure"],
      ["Event Type (CTE)", "cooling"],
      ["Event Date", "← cooling_date"],
      ["Event Time", "from event_timestamp"],
      ["Location GLN", "← location_gln"],
      ["Location Name", "← location_name"],
      ["Cooling Date", "← cooling_date"],
      ["Temperature (°F)", "← temperature_celsius, normalized"],
      ["Reference Document Number", "← reference_document"],
      ["Source Document", "your uploaded file name"],
      ["Record Hash (SHA-256)", "computed from the canonical record"],
      ["Chain Hash", "chains this record to the previous one"],
    ],
    fdaAnnotation:
      "Mapped to FDA Cooling Date and Temperature columns. The shared TLC links this row to the harvesting row above for sortable recall scope.",
  },
  {
    cte: "§1.1340",
    title: "Shipping",
    subtitle:
      "Transfer event. Adds Ship-From / Ship-To facilities with GLN identifiers, the FDA's expected join keys.",
    csvHeader:
      "traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,ship_from_location,ship_to_location,ship_from_gln,ship_to_gln,carrier_name,po_number,reference_document",
    csvNote:
      "One row per shipment. Ship-from and ship-to GLNs are the join keys an auditor uses to follow the lot.",
    canonical: `{
  "event_id": "<uuid, generated on ingest>",
  "tenant_id": "<your tenant id>",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "shipping",
  "event_timestamp": "<ship_date, ISO 8601>",
  "traceability_lot_code": "<traceability_lot_code>",
  "product_reference": "<product_description>",
  "quantity": <quantity>,
  "unit_of_measure": "<unit_of_measure>",
  "from_facility_reference": "<ship_from_gln>",
  "to_facility_reference": "<ship_to_gln>",
  "kdes": {
    "ship_date": "<ship_date>",
    "ship_from_gln": "<ship_from_gln>",
    "ship_from_location": "<ship_from_location>",
    "ship_to_gln": "<ship_to_gln>",
    "ship_to_location": "<ship_to_location>",
    "carrier": "<carrier_name>",
    "po_number": "<po_number>",
    "reference_document_number": "<reference_document>"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "<SHA-256 of the canonical record>",
  "chain_hash": "<hash chained to the previous event>"
}`,
    canonicalAnnotation:
      "Both Ship-From and Ship-To GLNs preserved as structured KDEs. Carrier and PO travel in the kdes map.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "← traceability_lot_code"],
      ["Product Description", "← product_description"],
      ["Quantity", "← quantity"],
      ["Unit of Measure", "← unit_of_measure"],
      ["Event Type (CTE)", "shipping"],
      ["Event Date", "← ship_date"],
      ["Event Time", "from event_timestamp"],
      ["Ship From GLN", "← ship_from_gln"],
      ["Ship From Name", "← ship_from_location"],
      ["Ship To GLN", "← ship_to_gln"],
      ["Ship To Name", "← ship_to_location"],
      ["Ship Date", "← ship_date"],
      ["Carrier", "← carrier_name"],
      ["Reference Document Number", "← reference_document"],
      ["Source Document", "your uploaded file name"],
      ["Record Hash (SHA-256)", "computed from the canonical record"],
      ["Chain Hash", "chains this record to the previous one"],
    ],
    fdaAnnotation:
      "Mapped to FDA Ship From / Ship To GLN + Name columns (auditor join keys). Facility names redact to [REDACTED] in the default export (#1219); GLNs always emit.",
  },
];

function Pane({ children, label, Icon }: { children: React.ReactNode; label: string; Icon: LucideIcon }) {
  return (
    <Card variant="inset" className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-re-border-subtle bg-re-surface-card px-3 py-2">
        <Icon className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
        <span className="text-label text-re-text-tertiary">{label}</span>
      </div>
      <div className="flex-1 overflow-x-auto p-3">{children}</div>
    </Card>
  );
}

function Arrow({ note }: { note: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-4 md:flex-col md:px-2 md:py-0">
      <ArrowRight className="h-5 w-5 rotate-90 text-re-text-muted md:rotate-0" strokeWidth={1.75} aria-hidden="true" />
      <p className="max-w-[180px] text-center text-small text-re-text-tertiary">
        {note}
      </p>
    </div>
  );
}

function StepBlock({ step, index }: { step: Step; index: number }) {
  return (
    <Section
      width="docs"
      flush={index === 0}
      eyebrow={<span className="font-mono uppercase">{`Step ${index + 1} · CTE ${step.cte}`}</span>}
      title={step.title}
      description={step.subtitle}
    >
      <div className="grid grid-cols-1 items-stretch gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
        {/* Column A: raw CSV */}
        <Pane label="A · Raw supplier CSV" Icon={FileSpreadsheet}>
          <pre className="whitespace-pre font-mono text-small leading-5 text-re-text-secondary">
            <span className="text-re-text-muted">{step.csvHeader}</span>
          </pre>
          <p className="mt-2 text-small text-re-text-tertiary">{step.csvNote}</p>
        </Pane>

        <Arrow note={step.canonicalAnnotation} />

        {/* Column B: canonical TraceabilityEvent */}
        <Pane label="B · Canonical TraceabilityEvent" Icon={Database}>
          <pre className="whitespace-pre font-mono text-small leading-5 text-re-text-secondary">
            {step.canonical}
          </pre>
        </Pane>

        <Arrow note={step.fdaAnnotation} />

        {/* Column C: FDA spreadsheet row */}
        <Pane label="C · FDA spreadsheet row" Icon={ShieldCheck}>
          <dl className="w-full">
            {step.fdaRow.map(([col, val]) => (
              <div key={col} className="border-b border-re-border-subtle py-1.5 last:border-0">
                <dt className="font-mono text-label uppercase text-re-text-muted">{col}</dt>
                <dd className="mt-0.5 break-all font-mono text-small text-re-text-primary">{val}</dd>
              </div>
            ))}
          </dl>
        </Pane>
      </div>
    </Section>
  );
}

export default function TransformationProofPage() {
  return (
    <div className="re-page min-h-screen">
      {/* Hero */}
      <header className="border-b border-re-border-subtle">
        <Container width="docs" className="py-16 md:py-20">
          <Link
            href="/proof"
            className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
          >
            ← Proof
          </Link>
          <PageHeader
            size="hero"
            title="How a supplier CSV becomes an FDA-oriented sortable record."
            className="mb-0 mt-4 border-b-0 pb-0"
          />
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Three CTEs, three transformations, running on real production code.
            Each step shows the CSV column spec, the canonical event shape from{" "}
            <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem]">
              services/shared/canonical_event.py
            </code>
            , and the FDA spreadsheet column mapping used in production. Your
            records supply the values; the pipeline supplies the structure.
          </p>
        </Container>
      </header>

      {STEPS.map((step, i) => (
        <StepBlock key={step.cte} step={step} index={i} />
      ))}

      {/* CTA */}
      <Section width="docs">
        <Card className="p-8 md:p-10">
          <h2 className="text-heading text-re-text-primary">
            Verify this for yourself.
          </h2>
          <p className="mt-2 max-w-[68ch] text-body text-re-text-secondary">
            Upload your own supplier CSV, run it through the canonical
            pipeline, and verify the SHA-256 and chain hashes with our open
            verifier.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/proof">
                Explore the proof library
                <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/verify">
                Open the verifier
                <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
          </div>
          <p className="mt-6 text-small text-re-text-tertiary">
            Code references: canonical shape ·{" "}
            <code className="font-mono">services/shared/canonical_event.py</code> · FDA columns ·{" "}
            <code className="font-mono">services/ingestion/app/fda_export_service.py</code>
          </p>
        </Card>
      </Section>
    </div>
  );
}
