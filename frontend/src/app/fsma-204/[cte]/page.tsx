import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  Leaf,
  Snowflake,
  Package,
  Truck,
  Download,
  Repeat2,
  Anchor,
  ClipboardList,
  Users,
  ShieldCheck,
  Zap,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  CTE DATA                                                           */
/* ------------------------------------------------------------------ */

interface KDE {
  field: string;
  description: string;
  example: string;
}

interface CTEData {
  slug: string;
  name: string;
  cfr: string;
  description: string;
  whoNeedsThis: string[];
  kdes: KDE[];
  commonMistakes: string[];
  howRegEngineHelps: string[];
}

const CTE_DATA: Record<string, CTEData> = {
  harvesting: {
    slug: "harvesting",
    name: "Harvesting",
    cfr: "21 CFR 1.1325",
    description:
      "The first critical tracking event in the supply chain. Harvesting captures when and where food was picked, cut, or collected from the field.",
    whoNeedsThis: ["Farms", "Growers", "Field harvesters"],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Unique identifier assigned to the harvested lot", example: "LOT-2026-04-15-BLU-001" },
      { field: "Product Description", description: "FDA-standard description of the commodity", example: "Blueberries, fresh, conventional" },
      { field: "Quantity", description: "Amount harvested in this lot", example: "1,200" },
      { field: "Unit of Measure", description: "UOM for the quantity", example: "lbs" },
      { field: "Location", description: "Address or GLN of the harvest site", example: "Sunny Acres Farm, Salinas, CA" },
      { field: "Harvest Date", description: "Date the product was harvested", example: "2026-04-15" },
      { field: "Field / Growing Area", description: "Specific field, block, or greenhouse identifier", example: "Field B-12 North" },
      { field: "Harvester Business Name", description: "Legal name of the entity that harvested", example: "Sunny Acres Farm LLC" },
    ],
    commonMistakes: [
      "Missing field or growing area — the FDA requires this, not just the farm address. Each field needs a distinct identifier.",
      "Inconsistent lot code formats — mixing formats like LOT-001, Lot001, and lot_001 across seasons or crews breaks traceability.",
      "Date format chaos — switching between MM/DD/YYYY and DD/MM/YYYY within the same file. The FDA expects a consistent, unambiguous format.",
    ],
    howRegEngineHelps: [
      "Validates that every required KDE is present before you submit — no more surprise gaps during an audit.",
      "Flags inconsistent lot code formats and suggests standardized alternatives.",
      "Catches date format mismatches and normalizes them to ISO 8601 (YYYY-MM-DD).",
      "Checks that field/growing area is populated — the most commonly missed KDE for harvesting events.",
    ],
  },
  cooling: {
    slug: "cooling",
    name: "Cooling",
    cfr: "21 CFR 1.1330",
    description:
      "Records when harvested product was cooled to safe storage temperature. Critical for cold chain integrity and shelf life documentation.",
    whoNeedsThis: ["Pre-coolers", "Cold storage facilities", "Farms with on-site cooling"],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code of the product being cooled", example: "LOT-2026-04-15-BLU-001" },
      { field: "Product Description", description: "FDA-standard description of the commodity", example: "Blueberries, fresh, conventional" },
      { field: "Quantity", description: "Amount cooled", example: "1,200" },
      { field: "Unit of Measure", description: "UOM for the quantity", example: "lbs" },
      { field: "Location", description: "Address or GLN of the cooling facility", example: "CoolCo Pre-Cool, Salinas, CA" },
      { field: "Cooling Date", description: "Date the product was cooled", example: "2026-04-15" },
      { field: "Temperature", description: "Temperature the product was cooled to", example: "34°F" },
    ],
    commonMistakes: [
      "Missing cooling date — data entry delays mean the cooling event is recorded hours or days late, often without the actual date.",
      "Temperature not recorded — the cooler logs it but the traceability spreadsheet doesn't capture the value.",
      "Facility name inconsistency — using 'CoolCo', 'Cool Co LLC', and 'CoolCo Pre-Cool' interchangeably across records.",
    ],
    howRegEngineHelps: [
      "Flags missing cooling dates and prompts for the actual date, not the upload date.",
      "Validates that temperature is present and within a plausible range for the commodity.",
      "Detects facility name variations and suggests a canonical name for consistency.",
      "Cross-references the TLC against harvesting events to ensure the chain is unbroken.",
    ],
  },
  initial_packing: {
    slug: "initial_packing",
    name: "Initial Packing",
    cfr: "21 CFR 1.1335",
    description:
      "Records when harvested product is first packed into containers for sale. This is where lot codes often multiply and traceability chains are most likely to break.",
    whoNeedsThis: ["Packhouses", "Fresh-cut processors", "Co-packers"],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "New lot code assigned during packing", example: "PKG-2026-04-16-BLU-A01" },
      { field: "Product Description", description: "FDA-standard description of the packed product", example: "Blueberries, fresh, 6oz clamshell" },
      { field: "Quantity", description: "Number of units packed", example: "2,400" },
      { field: "Unit of Measure", description: "UOM for the packed quantity", example: "clamshells" },
      { field: "Location", description: "Address or GLN of the packing facility", example: "Valley Pack LLC, Watsonville, CA" },
      { field: "Packing Date", description: "Date the product was packed", example: "2026-04-16" },
      { field: "Input Lot Codes", description: "TLCs of the harvested lots that went into this pack run", example: "LOT-2026-04-15-BLU-001, LOT-2026-04-15-BLU-002" },
    ],
    commonMistakes: [
      "Missing input lot codes — this is the single most common packing error. Without input TLCs, the traceability chain breaks at the packhouse.",
      "Duplicate rows from ERP exports — many ERP systems export one row per case rather than one row per lot, creating thousands of duplicate CTE records.",
      "CTE type aliases — some systems label this event as 'packing', 'pack', 'IP', or 'initial pack'. Mixed labels cause mapping failures.",
    ],
    howRegEngineHelps: [
      "Requires input lot codes and blocks submission if they are missing — preventing the most common traceability break.",
      "Deduplicates rows automatically when it detects ERP-style per-case exports.",
      "Normalizes CTE type labels so 'packing', 'pack', and 'initial_packing' all map correctly.",
      "Validates that input TLCs reference real harvesting or cooling events in your data.",
    ],
  },
  shipping: {
    slug: "shipping",
    name: "Shipping",
    cfr: "21 CFR 1.1340",
    description:
      "Records when product leaves a facility. Every entity in the supply chain that moves food on the FTL must record shipping events.",
    whoNeedsThis: ["Distributors", "Shippers", "3PLs", "Any entity that moves food"],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code of the product being shipped", example: "PKG-2026-04-16-BLU-A01" },
      { field: "Product Description", description: "FDA-standard description of the product", example: "Blueberries, fresh, 6oz clamshell" },
      { field: "Quantity", description: "Amount shipped", example: "480" },
      { field: "Unit of Measure", description: "UOM for the shipped quantity", example: "cases" },
      { field: "Location", description: "Address or GLN of the shipping facility", example: "Valley Pack LLC, Watsonville, CA" },
      { field: "Ship Date", description: "Date the product was shipped", example: "2026-04-17" },
      { field: "Ship-From", description: "Origin facility name and address", example: "Valley Pack LLC, Watsonville, CA" },
      { field: "Ship-To", description: "Destination facility name and address", example: "FreshMart DC, Tracy, CA" },
      { field: "Carrier", description: "Name of the transportation company", example: "Pacific Cold Freight" },
      { field: "Bill of Lading (BOL)", description: "Unique shipping document reference number", example: "BOL-78234" },
    ],
    commonMistakes: [
      "Missing destination (ship-to) — WMS systems often omit the full destination address, recording only a customer code.",
      "Abbreviated headers from WMS — column names like 'SHP_DT', 'DEST_CD', or 'QTY_CS' don't map to FDA-required field names.",
      "Carrier name inconsistency — the same carrier appearing as 'Pacific Cold', 'Pacific Cold Freight', and 'PCF Logistics'.",
    ],
    howRegEngineHelps: [
      "Validates that ship-to includes a full address or GLN, not just a customer code.",
      "Auto-maps common WMS column abbreviations to FDA-standard KDE field names.",
      "Detects carrier name variations and flags them for normalization.",
      "Cross-references shipping events against receiving events to detect gaps in the chain.",
    ],
  },
  receiving: {
    slug: "receiving",
    name: "Receiving",
    cfr: "21 CFR 1.1345",
    description:
      "Records when product arrives at a facility. Receiving is the mirror of shipping and completes each link in the traceability chain.",
    whoNeedsThis: [
      "Distribution centers",
      "Retailers",
      "Restaurants",
      "Any entity that receives food on the FTL",
    ],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code of the product received", example: "PKG-2026-04-16-BLU-A01" },
      { field: "Product Description", description: "FDA-standard description of the product", example: "Blueberries, fresh, 6oz clamshell" },
      { field: "Quantity", description: "Amount received", example: "480" },
      { field: "Unit of Measure", description: "UOM for the received quantity", example: "cases" },
      { field: "Location", description: "Address or GLN of the receiving facility", example: "FreshMart DC, Tracy, CA" },
      { field: "Receive Date", description: "Date the product was received", example: "2026-04-18" },
      { field: "Receiving Location", description: "Specific dock or bay at the receiving facility", example: "Dock 7, Bay B" },
      { field: "Immediate Previous Source", description: "Business name and address of the shipper", example: "Valley Pack LLC, Watsonville, CA" },
      { field: "TLC Source Reference", description: "Reference linking this TLC to the shipper's records", example: "BOL-78234" },
      { field: "Reference Document", description: "BOL, PO, or ASN number associated with the shipment", example: "PO-44210" },
    ],
    commonMistakes: [
      "Missing immediate previous source — receivers often record what arrived but not who sent it, breaking the trace-back chain.",
      "Product name mismatch vs. shipped — the shipper calls it 'Blueberries 6oz' and the receiver logs 'Fresh Blueberry Clamshell'. The FDA sees two different products.",
      "Missing reference document — without a BOL or PO number, there is no way to link the receiving event to the corresponding shipping event.",
    ],
    howRegEngineHelps: [
      "Requires immediate previous source and blocks submission when it is missing.",
      "Fuzzy-matches product descriptions between shipping and receiving events to flag mismatches before they become audit findings.",
      "Validates that a reference document (BOL, PO, or ASN) is present and cross-references it against shipping records.",
      "Highlights quantity discrepancies between what was shipped and what was received.",
    ],
  },
  transformation: {
    slug: "transformation",
    name: "Transformation",
    cfr: "21 CFR 1.1350",
    description:
      "Records when existing products are combined, processed, or converted into new products. This is where input lots become output lots and mass balance matters.",
    whoNeedsThis: [
      "Processors",
      "Manufacturers",
      "Fresh-cut operations",
      "Anyone who creates new products from FTL ingredients",
    ],
    kdes: [
      { field: "Traceability Lot Code (TLC) — New", description: "New lot code assigned to the output product", example: "TFM-2026-04-18-MIX-001" },
      { field: "Product Description", description: "FDA-standard description of the output product", example: "Spring Mix, 5oz bag" },
      { field: "Quantity", description: "Amount of the output product", example: "6,000" },
      { field: "Unit of Measure", description: "UOM for the output quantity", example: "bags" },
      { field: "Location", description: "Address or GLN of the processing facility", example: "GreenLeaf Processing, Salinas, CA" },
      { field: "Transformation Date", description: "Date the transformation occurred", example: "2026-04-18" },
      { field: "Input TLCs", description: "All lot codes of ingredients that went into this product", example: "LOT-ROM-042, LOT-SPN-038, LOT-KAL-019" },
    ],
    commonMistakes: [
      "Missing input TLCs — this is the most critical transformation error. Without input lot codes, trace-back stops at the processor.",
      "Mass balance violations — 100 lbs of inputs producing 120 lbs of output. The math must add up (minus documented waste/trim).",
      "No transformation date — the system records when the data was entered, not when the transformation actually occurred.",
    ],
    howRegEngineHelps: [
      "Requires input TLCs and validates that each one references a real lot in the system.",
      "Runs mass balance checks and flags output quantities that exceed input quantities beyond a configurable waste tolerance.",
      "Distinguishes between data entry date and actual transformation date, prompting for the correct value.",
      "Maps the full input-to-output lineage so you can trace any finished product back to its raw ingredients.",
    ],
  },
  first_land_based_receiving: {
    slug: "first_land_based_receiving",
    name: "First Land-Based Receiving",
    cfr: "21 CFR 1.1355",
    description:
      "Records when food first arrives on U.S. soil from a vessel or from outside the United States. This is the entry point for imported food into the domestic traceability chain.",
    whoNeedsThis: [
      "Seafood docks",
      "First receivers of imported food",
      "Port facilities",
    ],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code assigned at first land-based receipt", example: "FLBR-2026-04-18-TUNA-01" },
      { field: "Product Description", description: "FDA-standard description of the commodity", example: "Yellowfin Tuna, fresh, whole" },
      { field: "Quantity", description: "Amount received", example: "8,000" },
      { field: "Unit of Measure", description: "UOM for the received quantity", example: "lbs" },
      { field: "Location", description: "Address or GLN of the receiving facility", example: "Port of Long Beach, Terminal 4" },
      { field: "Landing Date", description: "Date the product first arrived on U.S. soil", example: "2026-04-18" },
      { field: "Immediate Previous Source", description: "Vessel name or foreign shipper information", example: "F/V Ocean Harvest, Fiji registry" },
    ],
    commonMistakes: [
      "Handwritten dock logs — many port facilities still use paper logs, leading to transcription errors and illegible records.",
      "Unparseable dates — international date formats (18/04/2026 vs 04/18/2026) and handwritten dates create ambiguity.",
      "Vessel name inconsistency — the same vessel logged as 'Ocean Harvest', 'F/V OCEAN HARVEST', and 'OceanHarvest-FJ'.",
      "Missing everything — first land-based receiving has the lowest data quality of any CTE because dock operations are fast-paced and often paper-based.",
    ],
    howRegEngineHelps: [
      "Accepts scanned or typed dock logs and validates that all required KDEs are present.",
      "Normalizes international date formats and flags ambiguous dates for manual review.",
      "Detects vessel name variations and maintains a canonical vessel registry.",
      "Provides a pre-formatted template designed for dock operations — fast to fill out, impossible to miss a required field.",
    ],
  },
};

const CTE_SLUGS = Object.keys(CTE_DATA);

const CTE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  harvesting: Leaf,
  cooling: Snowflake,
  initial_packing: Package,
  shipping: Truck,
  receiving: Download,
  transformation: Repeat2,
  first_land_based_receiving: Anchor,
};

/* ------------------------------------------------------------------ */
/*  STATIC PARAMS + METADATA                                           */
/* ------------------------------------------------------------------ */

export function generateStaticParams() {
  return CTE_SLUGS.map((cte) => ({ cte }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ cte: string }>;
}): Promise<Metadata> {
  const { cte } = await params;
  const data = CTE_DATA[cte];
  if (!data) return {};

  return {
    title: `${data.name} CTE — FSMA 204 ${data.cfr} Compliance | RegEngine`,
    description: `Everything you need to know about the ${data.name} Critical Tracking Event under FSMA 204 (${data.cfr}). Required KDEs, common mistakes, and how to validate your data.`,
  };
}

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default async function CTELandingPage({
  params,
}: {
  params: Promise<{ cte: string }>;
}) {
  const { cte: cteSlug } = await params;
  const data = CTE_DATA[cteSlug];
  if (!data) notFound();

  const Icon = CTE_ICONS[cteSlug] ?? ClipboardList;

  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* — HERO — */}
      <section className="max-w-4xl mx-auto px-6 pt-20 pb-16">
        <Link
          href="/fsma-204"
          className="inline-flex items-center gap-1.5 text-[0.82rem] text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors mb-6"
        >
          <ArrowRight className="h-3.5 w-3.5 rotate-180" />
          Back to FSMA 204 Guide
        </Link>

        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 rounded-xl bg-[var(--re-brand-muted)] flex items-center justify-center flex-shrink-0">
            <Icon className="h-6 w-6 text-[var(--re-brand)]" />
          </div>
          <div>
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-2">
              Critical Tracking Event
            </p>
            <h1 className="font-serif text-[clamp(2rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight">
              {data.name}
            </h1>
          </div>
        </div>

        <p className="font-mono text-[0.8rem] text-[var(--re-text-muted)] mb-4">
          {data.cfr}
        </p>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed max-w-[600px]">
          {data.description}
        </p>
      </section>

      {/* — WHO NEEDS THIS — */}
      <div className="max-w-4xl mx-auto px-6 pb-12">
        <div className="p-5 rounded-xl border border-[rgba(16,163,74,0.2)] bg-[rgba(16,163,74,0.03)]">
          <div className="flex items-start gap-3">
            <Users className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-[var(--re-text-primary)] mb-1">
                Who needs to record this CTE
              </p>
              <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                {data.whoNeedsThis.join(" \u00B7 ")}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* — REQUIRED KDEs TABLE — */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-16 px-6">
        <div className="max-w-4xl mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            Required Data Elements
          </p>
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
            Key Data Elements (KDEs)
          </h2>
          <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[600px]">
            The FDA requires each {data.name.toLowerCase()} event to include
            these {data.kdes.length} data points. Every field is mandatory.
          </p>

          <div className="overflow-x-auto rounded-xl border border-[var(--re-surface-border)]">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
                  <th className="px-5 py-3 text-[0.75rem] font-mono font-medium text-[var(--re-text-muted)] uppercase tracking-[0.06em]">
                    Field
                  </th>
                  <th className="px-5 py-3 text-[0.75rem] font-mono font-medium text-[var(--re-text-muted)] uppercase tracking-[0.06em]">
                    Description
                  </th>
                  <th className="px-5 py-3 text-[0.75rem] font-mono font-medium text-[var(--re-text-muted)] uppercase tracking-[0.06em]">
                    Example
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.kdes.map((kde, i) => (
                  <tr
                    key={kde.field}
                    className={
                      i < data.kdes.length - 1
                        ? "border-b border-[var(--re-surface-border)]"
                        : ""
                    }
                  >
                    <td className="px-5 py-3.5 text-[0.88rem] font-medium text-[var(--re-text-primary)] whitespace-nowrap">
                      {kde.field}
                    </td>
                    <td className="px-5 py-3.5 text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
                      {kde.description}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[0.8rem] text-[var(--re-text-muted)]">
                      {kde.example}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* — COMMON DATA QUALITY ISSUES — */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-danger,#dc2626)] uppercase tracking-[0.08em] mb-4">
          Watch out for these
        </p>
        <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
          Common Data Quality Issues
        </h2>
        <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[600px]">
          These are the mistakes we see most often in {data.name.toLowerCase()}{" "}
          data. Each one can cause an audit finding or break the traceability
          chain.
        </p>

        <div className="space-y-4 max-w-[680px]">
          {data.commonMistakes.map((mistake, i) => (
            <div
              key={i}
              className="flex gap-4 p-5 rounded-xl border border-[rgba(234,179,8,0.25)] bg-[rgba(234,179,8,0.04)]"
            >
              <AlertTriangle className="h-5 w-5 text-re-warning flex-shrink-0 mt-0.5" />
              <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                {mistake}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* — HOW REGENGINE HELPS — */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-16 px-6">
        <div className="max-w-4xl mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            Automated validation
          </p>
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
            How RegEngine Helps
          </h2>
          <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[600px]">
            Upload your {data.name.toLowerCase()} data to the sandbox and
            RegEngine catches these issues automatically — before the FDA does.
          </p>

          <div className="space-y-3 max-w-[680px]">
            {data.howRegEngineHelps.map((item, i) => (
              <div
                key={i}
                className="flex gap-3 p-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]"
              >
                {i === 0 ? (
                  <ShieldCheck className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                ) : i === 1 ? (
                  <Zap className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle2 className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                )}
                <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                  {item}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* — CTA — */}
      <section className="max-w-4xl mx-auto px-6 py-20">
        <div className="text-center">
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-4">
            See it in action.
          </h2>
          <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[500px] mx-auto">
            Upload a sample {data.name.toLowerCase()} file to the RegEngine
            sandbox and get an instant validation report — free, no signup
            required.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              href="/#sandbox"
              className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-lg text-[0.95rem] font-semibold hover:bg-[var(--re-brand-dark)] transition-all hover:-translate-y-0.5"
            >
              Try it now — free
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/fsma-204"
              className="inline-flex items-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-lg text-[0.95rem] font-medium hover:border-[var(--re-text-muted)] transition-all"
            >
              Full FSMA 204 Guide
            </Link>
          </div>
        </div>
      </section>

      {/* — OTHER CTEs NAV — */}
      <section className="bg-[var(--re-surface-card)] border-t border-[var(--re-surface-border)] py-12 px-6">
        <div className="max-w-4xl mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-text-muted)] uppercase tracking-[0.08em] mb-5 text-center">
            Other Critical Tracking Events
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {CTE_SLUGS.filter((s) => s !== cteSlug).map((s) => {
              const other = CTE_DATA[s];
              return (
                <Link
                  key={s}
                  href={`/fsma-204/${s}`}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--re-surface-border)] text-[0.82rem] text-[var(--re-text-secondary)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-all"
                >
                  {other.name}
                </Link>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
