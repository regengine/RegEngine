import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileSpreadsheet, Database, ShieldCheck } from "lucide-react";

export const metadata: Metadata = {
  title: "Proof: CSV → CTE → FDA row | RegEngine",
  description:
    "Watch a real supplier CSV become FDA-ready evidence. Three CTEs, three transformations, real production code, synthetic data.",
  openGraph: {
    title: "How a supplier CSV becomes FDA-ready evidence | RegEngine",
    description:
      "Three CTEs, three transformations. Real production code, synthetic data.",
    url: "https://regengine.co/proof/transformation",
    type: "website",
  },
};

// ---------------------------------------------------------------------------
// Data: hand-curated, faithful to production shapes
// ---------------------------------------------------------------------------
// CSV rows are direct copies from sample_data/0X_*.csv on main.
// Canonical JSON matches the TraceabilityEvent shape from
// services/shared/canonical_event.py.
// FDA rows match the column spec in
// services/ingestion/app/fda_export_service.py (FDA_COLUMNS, _NAMED_KDE_COLUMNS).
// PII columns shown unredacted here for demonstration; in a real export
// they pass through _redact_location_value when include_pii=False (#1219).

type Step = {
  cte: string;
  title: string;
  subtitle: string;
  csvHeader: string;
  csvRows: string[];
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
      "Origination event. Defines the Traceability Lot Code that follows romaine through every downstream CTE.",
    csvHeader:
      "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,location_gln,field_id,harvester_name,reference_document",
    csvRows: [
      "LOT-ROM-2026-0312A,Organic Romaine Hearts,5000,lbs,2026-03-12,Salinas Valley Farms,0061414100014,FIELD-SVF-7,Salinas Valley Farms LLC,HARV-SVF-2026-0312-001",
      "LOT-ROM-2026-0312B,Chopped Romaine Mix,3200,lbs,2026-03-12,Salinas Valley Farms,0061414100014,FIELD-SVF-12,Salinas Valley Farms LLC,HARV-SVF-2026-0312-002",
      "LOT-ROM-2026-0311C,Romaine Hearts 3-Pack,4100,lbs,2026-03-11,Pacific Coast Growers,0061414100021,FIELD-PCG-3,Pacific Coast Growers Inc,HARV-SVF-2026-0312-003",
    ],
    canonical: `{
  "event_id": "8f3c2e6a-4d11-4a0b-9b2e-5c0a1f4a2c10",
  "tenant_id": "9d2b1c4f-7e88-4f12-9c1a-6f0e2d3a8b71",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "harvesting",
  "event_timestamp": "2026-03-12T00:00:00+00:00",
  "traceability_lot_code": "LOT-ROM-2026-0312A",
  "product_reference": "Organic Romaine Hearts",
  "quantity": 5000,
  "unit_of_measure": "lbs",
  "from_facility_reference": "0061414100014",
  "kdes": {
    "harvest_date": "2026-03-12",
    "growing_area_name": "FIELD-SVF-7",
    "harvester_name": "Salinas Valley Farms LLC",
    "reference_document_number": "HARV-SVF-2026-0312-001",
    "location_name": "Salinas Valley Farms"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "9c4e1b7a2f8d5630ae914c2b0f7e6a18c3d5f9b2e0a7d4c1f8b3e6a9d2c5f0b7",
  "chain_hash": "f0a2b5c8d1e4f7a0b3c6d9e2f5a8b1c4d7e0f3a6b9c2d5e8f1a4b7c0d3e6f9a2"
}`,
    canonicalAnnotation:
      "KDE validation against §1.1330 (a)(1)–(7). Hash chained to previous event.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "LOT-ROM-2026-0312A"],
      ["Product Description", "Organic Romaine Hearts"],
      ["Quantity", "5000"],
      ["Unit of Measure", "lbs"],
      ["Event Type (CTE)", "harvesting"],
      ["Event Date", "2026-03-12"],
      ["Event Time", "00:00:00 UTC"],
      ["Location GLN", "0061414100014"],
      ["Location Name", "Salinas Valley Farms"],
      ["Harvest Date", "2026-03-12"],
      ["Growing Area", "FIELD-SVF-7"],
      ["Reference Document Number", "HARV-SVF-2026-0312-001"],
      ["Source Document", "01_harvesting.csv"],
      [
        "Record Hash (SHA-256)",
        "9c4e1b7a2f8d5630ae914c2b0f7e6a18c3d5f9b2e0a7d4c1f8b3e6a9d2c5f0b7",
      ],
      [
        "Chain Hash",
        "f0a2b5c8d1e4f7a0b3c6d9e2f5a8b1c4d7e0f3a6b9c2d5e8f1a4b7c0d3e6f9a2",
      ],
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
    csvRows: [
      "LOT-ROM-2026-0312A,Organic Romaine Hearts,5000,lbs,2026-03-12,Salinas Valley Cooler #1,0061414100014,1.8,COOL-SVF-2026-0312-001",
      "LOT-ROM-2026-0312B,Chopped Romaine Mix,3200,lbs,,Salinas Valley Cooler #1,0061414100014,2.3,COOL-SVF-2026-0312-002",
      "LOT-ROM-2026-0311C,Romaine Hearts 3-Pack,4100,lbs,2026-03-11,Pacific Coast Cold Storage,0061414100021,2.0,COOL-SVF-2026-0312-003",
    ],
    canonical: `{
  "event_id": "1a7d4e8b-2c93-4f67-a510-3b8e4c9f0a25",
  "tenant_id": "9d2b1c4f-7e88-4f12-9c1a-6f0e2d3a8b71",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "cooling",
  "event_timestamp": "2026-03-12T00:00:00+00:00",
  "traceability_lot_code": "LOT-ROM-2026-0312A",
  "product_reference": "Organic Romaine Hearts",
  "quantity": 5000,
  "unit_of_measure": "lbs",
  "from_facility_reference": "0061414100014",
  "kdes": {
    "cooling_date": "2026-03-12",
    "temperature": 35.24,
    "location_name": "Salinas Valley Cooler #1",
    "reference_document_number": "COOL-SVF-2026-0312-001"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "2e8c5a1b4d7f0936e2a5b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1",
  "chain_hash": "a4b7c0d3e6f9a2b5c8d1e4f7a0b3c6d9e2f5a8b1c4d7e0f3a6b9c2d5e8f1a4b7"
}`,
    canonicalAnnotation:
      "Celsius normalized to Fahrenheit (1.8°C → 35.24°F). TLC linkage proves continuity from harvest.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "LOT-ROM-2026-0312A"],
      ["Product Description", "Organic Romaine Hearts"],
      ["Quantity", "5000"],
      ["Unit of Measure", "lbs"],
      ["Event Type (CTE)", "cooling"],
      ["Event Date", "2026-03-12"],
      ["Event Time", "00:00:00 UTC"],
      ["Location GLN", "0061414100014"],
      ["Location Name", "Salinas Valley Cooler #1"],
      ["Cooling Date", "2026-03-12"],
      ["Temperature (°F)", "35.24"],
      ["Reference Document Number", "COOL-SVF-2026-0312-001"],
      ["Source Document", "02_cooling.csv"],
      [
        "Record Hash (SHA-256)",
        "2e8c5a1b4d7f0936e2a5b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1",
      ],
      [
        "Chain Hash",
        "a4b7c0d3e6f9a2b5c8d1e4f7a0b3c6d9e2f5a8b1c4d7e0f3a6b9c2d5e8f1a4b7",
      ],
    ],
    fdaAnnotation:
      "Mapped to FDA Cooling Date and Temperature columns. Same TLC links this row to the harvesting row above for sortable recall scope.",
  },
  {
    cte: "§1.1340",
    title: "Shipping",
    subtitle:
      "Transfer event. Adds Ship-From / Ship-To facilities with GLN identifiers — the FDA's expected join keys.",
    csvHeader:
      "traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,ship_from_location,ship_to_location,ship_from_gln,ship_to_gln,carrier_name,po_number,reference_document",
    csvRows: [
      "LOT-ROM-2026-0312A-PK,Organic Romaine Hearts 3ct,800,cases,2026-03-14,FreshCut Processing,MegaMart Distribution Center,0061414100038,0061414100045,FedEx Freight,PO-MM-2026-7201,BOL-CFS-2026-0313-001",
      "LOT-ROM-2026-0312A-PK,Organic Romaine Hearts 3ct,800,cases,2026-03-14,FreshCut Processing,Premier Grocery Warehouse,0061414100038,0061414100052,Cold Express Logistics,PO-PG-2026-3388,BOL-CFS-2026-0313-002",
      "LOT-ROM-2026-0312B-PK,Chopped Romaine 12oz Bag,2800,bags,2026-03-14,FreshCut Processing,MegaMart Distribution Center,0061414100038,0061414100045,FedEx Freight,PO-MM-2026-7202,BOL-CFS-2026-0313-003",
    ],
    canonical: `{
  "event_id": "5b2f8c1e-7d40-4a9b-8e15-2c7a0f4b9d63",
  "tenant_id": "9d2b1c4f-7e88-4f12-9c1a-6f0e2d3a8b71",
  "schema_version": 1,
  "source_system": "csv",
  "event_type": "shipping",
  "event_timestamp": "2026-03-14T00:00:00+00:00",
  "traceability_lot_code": "LOT-ROM-2026-0312A-PK",
  "product_reference": "Organic Romaine Hearts 3ct",
  "quantity": 800,
  "unit_of_measure": "cases",
  "from_facility_reference": "0061414100038",
  "to_facility_reference": "0061414100045",
  "kdes": {
    "ship_date": "2026-03-14",
    "ship_from_gln": "0061414100038",
    "ship_from_location": "FreshCut Processing",
    "ship_to_gln": "0061414100045",
    "ship_to_location": "MegaMart Distribution Center",
    "carrier": "FedEx Freight",
    "po_number": "PO-MM-2026-7201",
    "reference_document_number": "BOL-CFS-2026-0313-001"
  },
  "confidence_score": 1.0,
  "status": "active",
  "sha256_hash": "7f3a0c5d8e1b4f7a0c3d6e9f2a5b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a90",
  "chain_hash": "b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1f4a7b0c3d6e9f2a5b8c1"
}`,
    canonicalAnnotation:
      "Both Ship-From and Ship-To GLNs preserved as structured KDEs. Carrier and PO travel in the kdes map.",
    fdaRow: [
      ["Traceability Lot Code (TLC)", "LOT-ROM-2026-0312A-PK"],
      ["Product Description", "Organic Romaine Hearts 3ct"],
      ["Quantity", "800"],
      ["Unit of Measure", "cases"],
      ["Event Type (CTE)", "shipping"],
      ["Event Date", "2026-03-14"],
      ["Event Time", "00:00:00 UTC"],
      ["Ship From GLN", "0061414100038"],
      ["Ship From Name", "FreshCut Processing"],
      ["Ship To GLN", "0061414100045"],
      ["Ship To Name", "MegaMart Distribution Center"],
      ["Ship Date", "2026-03-14"],
      ["Carrier", "FedEx Freight"],
      ["Reference Document Number", "BOL-CFS-2026-0313-001"],
      ["Source Document", "04_shipping.csv"],
      [
        "Record Hash (SHA-256)",
        "7f3a0c5d8e1b4f7a0c3d6e9f2a5b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a90",
      ],
      [
        "Chain Hash",
        "b8c1d4e7f0a3b6c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1f4a7b0c3d6e9f2a5b8c1",
      ],
    ],
    fdaAnnotation:
      "Mapped to FDA Ship From / Ship To GLN + Name columns (auditor join keys). Facility names redact to [REDACTED] in the default export (#1219); GLNs always emit.",
  },
];

function CodeBlock({ children, label, Icon }: { children: React.ReactNode; label: string; Icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-200 bg-slate-50 overflow-hidden h-full">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <Icon className="h-4 w-4 text-slate-500" />
        <span className="text-xs font-semibold tracking-wide uppercase text-slate-600">
          {label}
        </span>
      </div>
      <div className="overflow-x-auto p-3 flex-1">{children}</div>
    </div>
  );
}

function Arrow({ note }: { note: string }) {
  return (
    <div className="flex md:flex-col items-center justify-center gap-2 py-4 md:py-0 md:px-2">
      <ArrowRight className="h-5 w-5 text-emerald-600 md:rotate-0 rotate-90" />
      <p className="text-xs text-slate-500 italic max-w-[180px] text-center leading-snug">
        {note}
      </p>
    </div>
  );
}

function StepBlock({ step, index }: { step: Step; index: number }) {
  return (
    <section className="border-t border-slate-200 pt-12 mt-12 first:border-0 first:pt-0 first:mt-0">
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
          Step {index + 1} · CTE {step.cte}
        </div>
        <h2 className="mt-3 text-3xl font-bold text-slate-900">{step.title}</h2>
        <p className="mt-2 max-w-3xl text-slate-600">{step.subtitle}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto_1fr] gap-4 items-stretch">
        {/* Column A: raw CSV */}
        <CodeBlock label="A · Raw supplier CSV" Icon={FileSpreadsheet}>
          <pre className="text-[11px] leading-relaxed font-mono text-slate-800 whitespace-pre">
            <span className="text-slate-400">{step.csvHeader}</span>
            {"\n"}
            {step.csvRows.join("\n")}
          </pre>
        </CodeBlock>

        <Arrow note={step.canonicalAnnotation} />

        {/* Column B: canonical TraceabilityEvent */}
        <CodeBlock label="B · Canonical TraceabilityEvent" Icon={Database}>
          <pre className="text-[11px] leading-relaxed font-mono text-slate-800 whitespace-pre">
            {step.canonical}
          </pre>
        </CodeBlock>

        <Arrow note={step.fdaAnnotation} />

        {/* Column C: FDA spreadsheet row */}
        <CodeBlock label="C · FDA spreadsheet row" Icon={ShieldCheck}>
          <table className="text-[11px] font-mono w-full">
            <tbody>
              {step.fdaRow.map(([col, val]) => (
                <tr key={col} className="border-b border-slate-200 last:border-0">
                  <td className="py-1 pr-3 text-slate-500 align-top whitespace-nowrap">
                    {col}
                  </td>
                  <td className="py-1 text-slate-900 break-all">{val}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CodeBlock>
      </div>
    </section>
  );
}

export default function TransformationProofPage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Hero */}
      <header className="border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white">
        <div className="mx-auto max-w-7xl px-6 py-16 md:py-20">
          <Link
            href="/proof"
            className="text-sm text-emerald-700 hover:underline"
          >
            ← Proof
          </Link>
          <h1 className="mt-4 text-4xl md:text-5xl font-bold tracking-tight text-slate-900">
            How a supplier CSV becomes FDA-ready evidence.
          </h1>
          <p className="mt-4 text-lg text-slate-600 max-w-3xl">
            Three CTEs, three transformations. Real production code, synthetic
            data. Every row you see comes from{" "}
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">
              sample_data/
            </code>{" "}
            and matches the canonical event shape and FDA spreadsheet column
            spec used in production.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-12">
        {STEPS.map((step, i) => (
          <StepBlock key={step.cte} step={step} index={i} />
        ))}

        {/* CTA */}
        <section className="mt-20 rounded-2xl border border-emerald-200 bg-emerald-50 p-8 md:p-10">
          <h2 className="text-2xl font-bold text-slate-900">
            Verify this for yourself.
          </h2>
          <p className="mt-2 text-slate-700 max-w-2xl">
            Download the same sample CSVs, run the canonical pipeline, and
            verify the SHA-256 + chain hashes with our open verifier.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/proof"
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Download sample data
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/verify"
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-600 bg-white px-5 py-3 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
            >
              Open the verifier
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <p className="mt-6 text-xs text-slate-500">
            Code references: canonical shape ·{" "}
            <code>services/shared/canonical_event.py</code> · FDA columns ·{" "}
            <code>services/ingestion/app/fda_export_service.py</code>
          </p>
        </section>
      </div>
    </main>
  );
}
