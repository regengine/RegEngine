import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Leaf,
  Snowflake,
  Package,
  Truck,
  Download,
  Repeat2,
  Anchor,
  ClipboardList,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { sandboxCta } from "@/lib/sandbox-cta";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
      "Missing field or growing area: the FDA requires this, not just the farm address. Each field needs a distinct identifier.",
      "Inconsistent lot code formats: mixing formats like LOT-001, Lot001, and lot_001 across seasons or crews breaks traceability.",
      "Date format chaos: switching between MM/DD/YYYY and DD/MM/YYYY within the same file. The FDA expects a consistent, unambiguous format.",
    ],
    howRegEngineHelps: [
      "Validates that every required KDE is present before you submit. No more surprise gaps during an audit.",
      "Flags inconsistent lot code formats and suggests standardized alternatives.",
      "Catches date format mismatches and normalizes them to ISO 8601 (YYYY-MM-DD).",
      "Checks that field/growing area is populated. It is the most commonly missed KDE for harvesting events.",
    ],
  },
  cooling: {
    slug: "cooling",
    name: "Cooling",
    cfr: "21 CFR 1.1325",
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
      { field: "Temperature (recommended)", description: "Temperature the product was cooled to. Recommended for cold-chain practice; not required by §1.1325.", example: "34°F" },
    ],
    commonMistakes: [
      "Missing cooling date: data entry delays mean the cooling event is recorded hours or days late, often without the actual date.",
      "Temperature not captured: temperature isn't required by FSMA 204, but most cooling-chain audits expect it.",
      "Facility name inconsistency: using 'CoolCo', 'Cool Co LLC', and 'CoolCo Pre-Cool' interchangeably across records.",
    ],
    howRegEngineHelps: [
      "Flags missing cooling dates and prompts for the actual date, not the upload date.",
      "Captures temperature when present and validates plausibility against the commodity (audit-readiness aid; not a regulatory check).",
      "Detects facility name variations and suggests a canonical name for consistency.",
      "Cross-references the TLC against harvesting events to ensure the chain is unbroken.",
    ],
  },
  "initial-packing": {
    slug: "initial-packing",
    name: "Initial Packing",
    cfr: "21 CFR 1.1330",
    description:
      "Records the initial packing of a raw agricultural commodity (other than food obtained from a fishing vessel) under 21 CFR 1.1330. This is where a Traceability Lot Code is often assigned for packed product and where harvest-to-pack links are most likely to break if TLC source fields are incomplete.",
    whoNeedsThis: ["Packhouses", "Fresh-cut processors packing RACs", "Co-packers packing RACs other than seafood from a vessel"],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code for the initially packed product", example: "PKG-2026-04-16-BLU-A01" },
      { field: "Commodity and variety", description: "Product description for the packed RAC", example: "Blueberries, fresh, conventional" },
      { field: "Quantity / Unit of Measure", description: "Amount packed and its unit", example: "2,400 clamshells" },
      { field: "Date of initial packing", description: "Date the product was initially packed", example: "2026-04-16" },
      { field: "Location description of the initial packer", description: "Address or GLN of the packing location", example: "Valley Pack LLC, Watsonville, CA" },
      { field: "Location description for the TLC source", description: "Farm, growing area, or container that is the TLC source", example: "Sunny Acres Farm, Field B-12 North" },
      { field: "TLC source reference", description: "Reference that links the packed lot to its TLC source", example: "HARVEST-REF-2026-04-15-BLU" },
      { field: "Harvest date range of the lot", description: "Harvest date or date range for the lot being packed", example: "2026-04-15" },
      { field: "Reference Document Type and Number", description: "Document type and number that identifies the packing event", example: "Pack ticket PT-44102" },
    ],
    commonMistakes: [
      "Missing TLC source fields: without the TLC source location and reference, the packed lot cannot be tied back to harvest under §1.1330.",
      "Harvest date range omitted or replaced with the pack date: the rule asks for the harvest date range of the lot, not only when packing happened.",
      "CTE type aliases: some systems label this event as 'packing', 'pack', 'IP', or 'initial pack'. Mixed labels cause mapping failures.",
      "Duplicate rows from ERP exports: many ERP systems export one row per case rather than one row per lot.",
    ],
    howRegEngineHelps: [
      "RegEngine (Beta, pre-revenue) checks uploaded packing rows for the §1.1330 KDE fields listed above before you build an export package.",
      "Flags missing TLC source location, TLC source reference, and harvest date range so you can fix gaps in your CSV or JSON events.",
      "Maps common packing CTE label aliases toward initial packing so mixed ERP vocabularies are easier to review.",
      "Does not decide covered-person status and does not guarantee compliance. Confirm final records against 21 CFR 1.1330.",
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
      "Missing destination (ship-to): WMS systems often omit the full destination address, recording only a customer code.",
      "Abbreviated headers from WMS: column names like 'SHP_DT', 'DEST_CD', or 'QTY_CS' may not map cleanly to FDA-oriented field names.",
      "Carrier name inconsistency: the same carrier appearing as 'Pacific Cold', 'Pacific Cold Freight', and 'PCF Logistics'.",
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
      "Wholesalers",
      "Foodservice distributors that receive (but do not sell directly to) consumers",
      "Any entity receiving food on the FTL, subject to the §1.1305 exemptions",
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
      "Missing immediate previous source: receivers often record what arrived but not who sent it, breaking the trace-back chain.",
      "Product name mismatch vs. shipped: the shipper calls it 'Blueberries 6oz' and the receiver logs 'Fresh Blueberry Clamshell'. The FDA sees two different products.",
      "Missing reference document: without a BOL or PO number, there is no way to link the receiving event to the corresponding shipping event.",
    ],
    howRegEngineHelps: [
      "Requires immediate previous source before an export can build.",
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
      { field: "New Traceability Lot Code (TLC)", description: "New lot code assigned to the output product", example: "TFM-2026-04-18-MIX-001" },
      { field: "Product Description", description: "FDA-standard description of the output product", example: "Spring Mix, 5oz bag" },
      { field: "Quantity", description: "Amount of the output product", example: "6,000" },
      { field: "Unit of Measure", description: "UOM for the output quantity", example: "bags" },
      { field: "Location", description: "Address or GLN of the processing facility", example: "GreenLeaf Processing, Salinas, CA" },
      { field: "Transformation Date", description: "Date the transformation occurred", example: "2026-04-18" },
      { field: "Input TLCs", description: "All lot codes of ingredients that went into this product", example: "Every input TLC, one per ingredient lot" },
    ],
    commonMistakes: [
      "Missing input TLCs: this is the most critical transformation error. Without input lot codes, trace-back stops at the processor.",
      "Mass balance violations: 100 lbs of inputs producing 120 lbs of output. The math must add up (minus documented waste/trim).",
      "No transformation date: the system records when the data was entered, not when the transformation actually occurred.",
    ],
    howRegEngineHelps: [
      "Requires input TLCs and validates that each one references a real lot in the system.",
      "Runs mass balance checks and flags output quantities that exceed input quantities beyond a configurable waste tolerance.",
      "Distinguishes between data entry date and actual transformation date, prompting for the correct value.",
      "Maps the full input-to-output lineage so you can trace any finished product back to its raw ingredients.",
    ],
  },
  "first-land-based-receiving": {
    slug: "first-land-based-receiving",
    name: "First Land-Based Receiving",
    cfr: "21 CFR 1.1335",
    description:
      "Records the first land-based receiving of food obtained from a fishing vessel under 21 CFR 1.1335: the point at which that seafood lands and enters the domestic traceability chain. This CTE applies only to food obtained from a fishing vessel; generic imported food entry is covered by ordinary Receiving (§1.1345).",
    whoNeedsThis: [
      "Seafood docks and first receivers landing fish from vessels",
      "Processors receiving food directly from a fishing vessel",
    ],
    kdes: [
      { field: "Traceability Lot Code (TLC)", description: "Lot code assigned at first land-based receiving", example: "FLBR-2026-04-18-TUNA-01" },
      { field: "Species / commodity", description: "Product description for the landed food", example: "Yellowfin Tuna, fresh, whole" },
      { field: "Harvest date range", description: "Harvest date or date range for the lot", example: "2026-04-10 to 2026-04-17" },
      { field: "Location description for the harvest area", description: "NMFS area or equivalent harvest-area description", example: "NMFS statistical area 17" },
      { field: "Quantity / Unit of Measure", description: "Amount received and its unit", example: "8,000 lbs" },
      { field: "Name and address of the harvest vessel", description: "Vessel identity for the fishing vessel source", example: "F/V Ocean Harvest, Fiji registry" },
      { field: "Date of landing", description: "Date of first land-based receiving", example: "2026-04-18" },
      { field: "Location description of the first land-based receiver", description: "Address or GLN of the receiving facility", example: "Port of Long Beach, Terminal 4" },
      { field: "Reference Document Type and Number", description: "Document type and number that identifies the landing event", example: "Landing ticket LT-90821" },
    ],
    commonMistakes: [
      "Handwritten dock logs: many port facilities still use paper logs, leading to transcription errors and illegible records.",
      "Harvest area or vessel identity missing: §1.1335 expects harvest-area location description and the harvest vessel name and address.",
      "Unparseable dates: international date formats (18/04/2026 vs 04/18/2026) and handwritten dates create ambiguity.",
      "Confusing this CTE with ordinary Receiving (§1.1345): first land-based receiving applies only to food obtained from a fishing vessel.",
    ],
    howRegEngineHelps: [
      "RegEngine (Beta, pre-revenue) checks uploaded first land-based receiving rows for the §1.1335 KDE fields listed above.",
      "Flags missing vessel identity, harvest area, landing date, and reference document fields so you can repair CSV or JSON events.",
      "Helps operators review dock-origin records before packaging an export; it does not replace your own dock log process.",
      "Does not decide covered-person status and does not guarantee compliance. Confirm final records against 21 CFR 1.1335.",
    ],
  },
};

const CTE_SLUGS = Object.keys(CTE_DATA);

const CTE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  harvesting: Leaf,
  cooling: Snowflake,
  "initial-packing": Package,
  shipping: Truck,
  receiving: Download,
  transformation: Repeat2,
  "first-land-based-receiving": Anchor,
};

/* ------------------------------------------------------------------ */
/*  STATIC PARAMS + METADATA                                           */
/* ------------------------------------------------------------------ */

/** Canonical marketing slugs use hyphens. Underscore aliases still resolve. */
function resolveCteSlug(raw: string): string {
  const normalized = raw.replaceAll("_", "-");
  return CTE_DATA[normalized] ? normalized : raw;
}

export function generateStaticParams() {
  return CTE_SLUGS.map((cte) => ({ cte }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ cte: string }>;
}): Promise<Metadata> {
  const { cte } = await params;
  const data = CTE_DATA[resolveCteSlug(cte)];
  if (!data) return {};

  const path = `/fsma-204/${cte}`;
  const title = `${data.name} CTE: FSMA 204 ${data.cfr} Compliance | RegEngine`;
  const description = `Everything you need to know about the ${data.name} Critical Tracking Event under FSMA 204 (${data.cfr}). Required KDEs, common mistakes, and how to validate your data.`;
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: path,
      type: 'website',
    },
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
  const { cte: cteParam } = await params;
  const cteSlug = resolveCteSlug(cteParam);
  const data = CTE_DATA[cteSlug];
  if (!data) notFound();

  const Icon = CTE_ICONS[cteSlug] ?? ClipboardList;
  const cta = sandboxCta();

  return (
    <div className="bg-re-surface-base">
      {/* - HERO - */}
      <Container width="marketing" className="pt-12 sm:pt-16">
        <Link
          href="/fsma-204"
          className="mb-6 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          <ArrowRight className="h-3.5 w-3.5 rotate-180" strokeWidth={1.75} aria-hidden="true" />
          Back to FSMA 204 Guide
        </Link>

        <PageHeader
          size="hero"
          eyebrow={
            <span className="inline-flex items-center gap-1.5 font-mono uppercase">
              <Icon className="h-3.5 w-3.5 text-re-text-tertiary" aria-hidden="true" />
              Critical Tracking Event
            </span>
          }
          title={data.name}
          description={
            <>
              <span className="block font-mono text-small text-re-text-muted">{data.cfr}</span>
              <span className="mt-3 block">{data.description}</span>
            </>
          }
          className="border-b-0 pb-0"
        />

        {/* - WHO NEEDS THIS - */}
        <Callout tone="neutral" className="mt-8 max-w-[68ch]">
          <p className="font-medium text-re-text-primary">
            Who needs to record this CTE
          </p>
          <p className="mt-1">{data.whoNeedsThis.join(" \u00B7 ")}</p>
        </Callout>
      </Container>

      {/* - REQUIRED KDEs TABLE - */}
      <Section
        width="marketing"
        eyebrow={<span className="font-mono uppercase">Required Data Elements</span>}
        title="Key Data Elements (KDEs)"
        description={
          <>
            The FDA requires each {data.name.toLowerCase()} event to include
            these {data.kdes.length} data points. Every field is mandatory.
          </>
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Example</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.kdes.map((kde) => (
              <TableRow key={kde.field}>
                <TableCell className="whitespace-nowrap">{kde.field}</TableCell>
                <TableCell>{kde.description}</TableCell>
                <TableCell className="font-mono text-[0.8125rem] text-re-text-tertiary">
                  {kde.example}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      {/* - COMMON DATA QUALITY ISSUES - */}
      <Section
        width="marketing"
        eyebrow={<span className="font-mono uppercase">Watch out for these</span>}
        title="Common Data Quality Issues"
        description={
          <>
            These are the mistakes we see most often in {data.name.toLowerCase()}{" "}
            data. Each one can cause an audit finding or break the traceability
            chain.
          </>
        }
      >
        <div className="max-w-[68ch] space-y-3">
          {data.commonMistakes.map((mistake, i) => (
            <Callout key={i} tone="warning">
              <p>{mistake}</p>
            </Callout>
          ))}
        </div>
      </Section>

      {/* - HOW REGENGINE HELPS - */}
      <Section
        width="marketing"
        eyebrow={<span className="font-mono uppercase">Beta recordkeeping checks</span>}
        title="How RegEngine Helps"
        description={
          <>
            Upload your {data.name.toLowerCase()} data to{" "}
            <Link href="/ingest?tab=file" className="text-re-brand underline underline-offset-[3px]">RegEngine</Link> and
            RegEngine surfaces these issues before they become audit findings during a §1.1455 records request.
          </>
        }
      >
        <ul className="max-w-[68ch] space-y-3">
          {data.howRegEngineHelps.map((item, i) => (
            <li key={i}>
              <Card variant="inset" padding="compact" className="flex gap-3">
                {i === 0 ? (
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                ) : i === 1 ? (
                  <Zap className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                )}
                <p className="text-ui text-re-text-secondary">{item}</p>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      {/* - CTA - */}
      <Section width="marketing" tone="inset">
        <div className="mx-auto max-w-[640px] text-center">
          <h2 className="font-display text-heading-lg text-re-text-primary">
            See it in action.
          </h2>
          {/* #2757 - copy and destination resolve together so the blurb can never
              promise a CSV sandbox that this deployment does not serve. */}
          <p className="mx-auto mt-4 max-w-[500px] text-body text-re-text-secondary">
            {cta.blurb}
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <Link href={cta.href}>
                {cta.label}
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/fsma-204">Full FSMA 204 Guide</Link>
            </Button>
          </div>
        </div>
      </Section>

      {/* - OTHER CTEs NAV - */}
      <Section width="marketing" className="py-12 sm:py-12">
        <p className="mb-5 text-center font-mono text-label uppercase text-re-text-muted">
          Other Critical Tracking Events
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {CTE_SLUGS.filter((s) => s !== cteSlug).map((s) => {
            const other = CTE_DATA[s];
            return (
              <Link
                key={s}
                href={`/fsma-204/${s}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-re-border px-4 py-2 text-ui text-re-text-secondary transition-colors duration-120 hover:border-re-border-strong hover:text-re-text-primary motion-reduce:transition-none"
              >
                {other.name}
              </Link>
            );
          })}
        </div>
      </Section>
    </div>
  );
}
