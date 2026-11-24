import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Download, ExternalLink, Mail } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { JSONLD } from "@/components/seo/json-ld";
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

/*
 * Buyer question this page answers (AI visibility capture, Nov 23 2026):
 * "How does a small retailer or supplier build the FSMA 204 sortable spreadsheet?"
 *
 * Every CTE and KDE below comes from two FDA sources only:
 *   FDA_TEMPLATE_URL: FDA's downloadable electronic sortable spreadsheet template (June 2024)
 *   FDA_SECG_URL: FDA's Small Entity Compliance Guide for the Food Traceability Rule
 * The downloadable workbook mirrors the template's column headers for the
 * seven CTE tabs. Its example rows are made up and marked EXAMPLE.
 */

const PAGE_URL = "https://regengine.co/fsma-204/sortable-spreadsheet";
const FDA_TEMPLATE_URL = "https://www.fda.gov/media/179616/download";
const FDA_SECG_URL = "https://www.fda.gov/media/168142/download";
const FDA_RULE_URL =
  "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods";
const EXAMPLE_FILE = "/downloads/fsma-204-sortable-spreadsheet-example.xlsx";
const CONTACT_EMAIL = "christopher@regengine.co";

const TITLE = "How to Build the FSMA 204 Sortable Spreadsheet";
const DESCRIPTION =
  "How a small retailer or supplier builds the FSMA 204 electronic sortable spreadsheet: one tab per Critical Tracking Event, one column per Key Data Element, based on FDA's template. Free example workbook.";

export const metadata: Metadata = {
  title: `${TITLE} | RegEngine`,
  description: DESCRIPTION,
  alternates: { canonical: PAGE_URL },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: PAGE_URL,
    type: "article",
  },
};

/* ------------------------------------------------------------------ */
/*  DATA (from FDA's template and Small Entity Compliance Guide)        */
/* ------------------------------------------------------------------ */

const LOCATION_PARTS =
  "Business name, phone number, street address or geographic coordinates, city, state or region, ZIP or postal code, country";
const PRODUCT_PARTS =
  "Product name, brand name (if applicable), commodity (if applicable), variety (if applicable), packaging size, packaging style";
const REFERENCE_PARTS =
  "Reference document type and number, plus a second type and number if needed";

interface KdeGroup {
  kde: string;
  columns: string;
}

interface CteTab {
  id: string;
  tab: string;
  cfr: string;
  who: string;
  kdes: KdeGroup[];
}

const CTE_TABS: CteTab[] = [
  {
    id: "harvesting",
    tab: "Harvesting",
    cfr: "21 CFR 1.1325(a)",
    who: "Farms that harvest a raw agricultural commodity on the Food Traceability List.",
    kdes: [
      { kde: "Location description for the immediate subsequent recipient (other than a transporter)", columns: LOCATION_PARTS },
      { kde: "Commodity and variety", columns: "Commodity; variety (if applicable)" },
      { kde: "Quantity and unit of measure", columns: "Quantity; unit of measure" },
      { kde: "Location description for the farm where the food was harvested", columns: LOCATION_PARTS },
      { kde: "Field or container name", columns: "For produce, the field or other growing area name; for aquacultured food, the container name (pond, pool, tank, cage)" },
      { kde: "Date of harvesting", columns: "Harvest date (mm/dd/yyyy)" },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "cooling",
    tab: "Cooling",
    cfr: "21 CFR 1.1325(b)",
    who: "Anyone who cools a raw agricultural commodity before it is initially packed.",
    kdes: [
      { kde: "Location description for the immediate subsequent recipient (other than a transporter)", columns: LOCATION_PARTS },
      { kde: "Commodity and variety", columns: "Commodity; variety (if applicable)" },
      { kde: "Quantity and unit of measure", columns: "Quantity; unit of measure" },
      { kde: "Location description for where the food was cooled", columns: LOCATION_PARTS },
      { kde: "Date of cooling", columns: "Cooling date (mm/dd/yyyy)" },
      { kde: "Location description for the farm where the food was harvested", columns: LOCATION_PARTS },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "initial-packing",
    tab: "Initial Packing",
    cfr: "21 CFR 1.1330(a)",
    who: "Packers who initially pack a raw agricultural commodity (other than food from a fishing vessel).",
    kdes: [
      { kde: "Food received", columns: "Commodity and variety of the food received; date you received it; quantity and unit of measure received" },
      { kde: "Location description for the farm where the food was harvested", columns: LOCATION_PARTS },
      { kde: "Field or container name", columns: "For produce, the field or other growing area name; for aquacultured food, the container name" },
      { kde: "Harvester", columns: "Harvester business name; harvester phone number; harvesting date" },
      { kde: "Cooling (if applicable)", columns: `Location description for where the food was cooled (${LOCATION_PARTS.toLowerCase()}); cooling date` },
      { kde: "Traceability lot code you assigned", columns: "Traceability lot code" },
      { kde: "Product description of the packed food", columns: PRODUCT_PARTS },
      { kde: "Quantity and unit of measure of the packed food", columns: "Quantity; unit of measure" },
      { kde: "Location description for where you initially packed the food (the traceability lot code source)", columns: `${LOCATION_PARTS}; traceability lot code source reference (if applicable)` },
      { kde: "Date of initial packing", columns: "Initial packing date (mm/dd/yyyy)" },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "first-land-based-receiving",
    tab: "First Land-Based Receiving",
    cfr: "21 CFR 1.1335",
    who: "The first person to take possession of a food on land directly from a fishing vessel.",
    kdes: [
      { kde: "Traceability lot code you assigned", columns: "Traceability lot code" },
      { kde: "Species or product description", columns: `Species and/or acceptable market name if the food is unpackaged; if packaged: ${PRODUCT_PARTS.toLowerCase()}` },
      { kde: "Quantity and unit of measure", columns: "Quantity; unit of measure" },
      { kde: "Harvest dates and locations for the trip", columns: "Harvest date start; harvest date end; harvest locations for the trip" },
      { kde: "Location description for the first land-based receiver (the traceability lot code source)", columns: `${LOCATION_PARTS}; traceability lot code source reference (if applicable)` },
      { kde: "Date the food was landed", columns: "Landing date (mm/dd/yyyy)" },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "shipping",
    tab: "Shipping",
    cfr: "21 CFR 1.1340",
    who: "Anyone who ships a food on the Food Traceability List (after initial packing, for raw agricultural commodities).",
    kdes: [
      { kde: "Traceability lot code", columns: "Traceability lot code assigned by the initial packer, first land-based receiver, or the person who transformed the food" },
      { kde: "Quantity and unit of measure", columns: "Quantity; unit of measure" },
      { kde: "Product description", columns: PRODUCT_PARTS },
      { kde: "Location description for the immediate subsequent recipient (other than a transporter)", columns: LOCATION_PARTS },
      { kde: "Location description for the location from which you shipped the food", columns: LOCATION_PARTS },
      { kde: "Date you shipped the food", columns: "Shipping date (mm/dd/yyyy)" },
      { kde: "Traceability lot code source", columns: `Location description for the traceability lot code source (${LOCATION_PARTS.toLowerCase()}), or a traceability lot code source reference instead` },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "receiving",
    tab: "Receiving",
    cfr: "21 CFR 1.1345(a)",
    who: "Anyone who receives a food on the Food Traceability List, including a retail food establishment.",
    kdes: [
      { kde: "Traceability lot code", columns: "Traceability lot code assigned by the initial packer, first land-based receiver, or the person who transformed the food" },
      { kde: "Quantity and unit of measure", columns: "Quantity; unit of measure" },
      { kde: "Product description", columns: PRODUCT_PARTS },
      { kde: "Location description for the immediate previous source (other than a transporter)", columns: LOCATION_PARTS },
      { kde: "Location description for where the food was received", columns: LOCATION_PARTS },
      { kde: "Date you received the food", columns: "Receive date (mm/dd/yyyy)" },
      { kde: "Traceability lot code source", columns: `Location description for the traceability lot code source (${LOCATION_PARTS.toLowerCase()}), or a traceability lot code source reference instead` },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
  {
    id: "transformation",
    tab: "Transformation",
    cfr: "21 CFR 1.1350",
    who: "Anyone who transforms a food on the Food Traceability List, for example by cutting, mixing, or processing it into a new product.",
    kdes: [
      { kde: "Food used in transformation", columns: `Traceability lot code of the food used; product description (${PRODUCT_PARTS.toLowerCase()}); quantity and unit of measure used from that lot` },
      { kde: "New traceability lot code you assigned", columns: "New traceability lot code for the food produced" },
      { kde: "Location description for where you transformed the food (the traceability lot code source)", columns: `${LOCATION_PARTS}; traceability lot code source reference (if applicable)` },
      { kde: "Date transformation was completed", columns: "Transformation completion date (mm/dd/yyyy)" },
      { kde: "Food produced through transformation", columns: `Product description (${PRODUCT_PARTS.toLowerCase()}); quantity and unit of measure produced` },
      { kde: "Reference document type and number", columns: REFERENCE_PARTS },
    ],
  },
];

const STEPS = [
  {
    num: 1,
    title: "List the events you perform for foods on the Food Traceability List.",
    desc: "FDA's template has a tab for every Critical Tracking Event, but you only fill the tabs for the events you perform for the food FDA asks about. A small retailer that only buys and sells covered foods usually needs the Receiving tab. A supplier that packs and ships needs Initial Packing and Shipping.",
  },
  {
    num: 2,
    title: "Start from FDA's template or our example workbook.",
    desc: "FDA publishes a downloadable electronic sortable spreadsheet template with one tab per Critical Tracking Event. FDA says the template is illustrative and you are not required to use it. Our example workbook copies the column layout for the seven events below and adds made up example rows.",
  },
  {
    num: 3,
    title: "Give each Key Data Element its own column.",
    desc: "In FDA's template each column header is one Key Data Element. Elements with several parts are split: a location description becomes seven columns (business name, phone number, street address or geographic coordinates, city, state or region, ZIP or postal code, country) and a product description becomes six.",
  },
  {
    num: 4,
    title: "Add one row per event record and keep every value in its own cell.",
    desc: "Enter one row for each record of an event, such as one row for each traceability lot you receive in a shipment. Keep a single header row, no merged cells, and one date format (FDA's template uses mm/dd/yyyy) so the sheet can be sorted and filtered.",
  },
  {
    num: 5,
    title: "Link each row to its reference document.",
    desc: "Every event tab has columns for the reference document type and number, such as a bill of lading, invoice, advance shipping notice, or production log. FDA's template adds a second pair of columns if you need one.",
  },
  {
    num: 6,
    title: "Be ready to send it within 24 hours of an FDA request.",
    desc: "When FDA requests records during an outbreak, recall, or other public health threat, you must provide the information within 24 hours (or a reasonable time FDA agrees to), in an electronic sortable spreadsheet for the foods and date ranges or traceability lot codes in the request (21 CFR 1.1455(c)(3)).",
  },
];

const FAQS = [
  {
    q: "Do I have to use FDA's sortable spreadsheet template?",
    a: "No. FDA says its template is presented for illustrative purposes and that you are not required to use that specific template. What matters is that the required Key Data Elements for each Critical Tracking Event are in an electronic, sortable spreadsheet when FDA asks for it.",
  },
  {
    q: "Do I fill in every tab?",
    a: "No. FDA's template includes a tab for every Critical Tracking Event in the rule, but you complete only the tabs for the events you perform that relate to FDA's request.",
  },
  {
    q: "What does a small retailer usually record?",
    a: "Most small retailers receive covered foods and sell them to consumers, so the Receiving tab is the core of their sheet. FDA's Small Entity Compliance Guide says retail food establishments and restaurants do not have to keep transformation records for foods they do not ship, such as food they sell directly to consumers.",
  },
  {
    q: "Does every business have to send the spreadsheet format?",
    a: "No. Under 21 CFR 1.1455(c)(3)(iii), certain smaller farms, retail food establishments, restaurants, and other businesses below sales thresholds set in the rule may provide the requested information in a form other than an electronic sortable spreadsheet. Some very small retail food establishments and restaurants are exempt from the rule entirely. Check the thresholds and exemptions in FDA's Small Entity Compliance Guide.",
  },
  {
    q: "How long do I keep the records?",
    a: "FDA's Small Entity Compliance Guide says to keep the required records for 2 years from the date you created or obtained them.",
  },
  {
    q: "When does FDA start enforcing the Food Traceability Rule?",
    a: "FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Check FDA's Food Traceability Rule page for the current status.",
  },
  {
    q: "Is the example workbook an FDA form?",
    a: "No. It is an example made by RegEngine. Its column headers follow FDA's template for seven Critical Tracking Events, and every example row is made up and marked EXAMPLE. Delete those rows before you enter your own records.",
  },
];

const FAQ_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQS.map((faq) => ({
    "@type": "Question",
    name: faq.q,
    acceptedAnswer: { "@type": "Answer", text: faq.a },
  })),
};

const LINK_CLASS =
  "text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand";

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function SortableSpreadsheetGuidePage() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={FAQ_JSON_LD} />

      {/* - HERO - */}
      <Container width="marketing" className="pt-12 sm:pt-16">
        <PageHeader
          size="hero"
          eyebrow="FSMA 204 Guide"
          title="How does a small retailer or supplier build the FSMA 204 sortable spreadsheet?"
          description={
            <>
              <span className="block">
                Make one tab for each Critical Tracking Event you perform and one column for each Key Data Element FDA lists for that event. Add one row per record, keep dates and lot codes in their own cells, and be ready to send the sheet within 24 hours of an FDA request.
              </span>
              <span className="mt-3 block text-small text-re-text-muted">
                Based on FDA&apos;s sortable spreadsheet template and Small Entity Compliance Guide.
              </span>
            </>
          }
          primaryAction={
            <Button asChild size="lg">
              <a href={EXAMPLE_FILE} download>
                Download the example workbook (.xlsx)
                <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </a>
            </Button>
          }
          secondaryActions={
            <Button asChild variant="secondary" size="lg">
              <a href={FDA_TEMPLATE_URL} target="_blank" rel="noopener noreferrer">
                FDA&apos;s template
                <ExternalLink className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </a>
            </Button>
          }
          className="border-b-0 pb-0"
        />
      </Container>

      {/* - SHORT ANSWER - */}
      <Section width="marketing" flush title="The short answer">
        <div className="max-w-[68ch] space-y-4 text-body text-re-text-secondary">
          <p>
            FDA&apos;s Food Traceability Rule (FSMA 204) says that when FDA asks for traceability records during an outbreak or recall, you provide them as an <strong className="font-medium text-re-text-primary">electronic sortable spreadsheet within 24 hours</strong>. FDA publishes a{" "}
            <a href={FDA_TEMPLATE_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              downloadable sortable spreadsheet template
            </a>{" "}
            in which each tab is a Critical Tracking Event (CTE) and each column header is a required Key Data Element (KDE).
          </p>
          <p>
            To build yours, copy that layout for the events you perform, fill one row per record, and keep it current. FDA&apos;s{" "}
            <a href={FDA_SECG_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              Small Entity Compliance Guide
            </a>{" "}
            explains which records each type of business keeps.
          </p>
        </div>
        <Callout tone="info" className="mt-8 max-w-[68ch]">
          <p>
            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. See{" "}
            <a href={FDA_RULE_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              FDA&apos;s Food Traceability Rule page
            </a>{" "}
            for the current status.
          </p>
        </Callout>
      </Section>

      {/* - STEPS - */}
      <Section
        id="steps"
        width="marketing"
        eyebrow="Step by step"
        title="How to build the sortable spreadsheet in six steps"
      >
        <ol className="space-y-4">
          {STEPS.map((step) => (
            <li key={step.num}>
              <Card padding="compact" className="flex gap-5">
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-re-border font-mono text-ui tabular-nums text-re-text-muted"
                >
                  {step.num}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-subheading text-re-text-primary">{step.title}</h3>
                  <p className="mt-2 text-ui text-re-text-secondary">{step.desc}</p>
                </div>
              </Card>
            </li>
          ))}
        </ol>
      </Section>

      {/* - TABS AND COLUMNS - */}
      <Section
        id="tabs"
        width="marketing"
        eyebrow="Tabs and columns"
        title="One tab per Critical Tracking Event, with its Key Data Element columns"
        description="These are the seven event tabs in FDA's template and the columns each one holds. FDA's template also has tabs for sprouts, food received from or packed for exempt entities, and certain retail and institution purchases from farms."
      >
        <nav aria-label="Critical Tracking Event tabs" className="mb-8 flex flex-wrap gap-2">
          {CTE_TABS.map((cte) => (
            <a
              key={cte.id}
              href={`#${cte.id}`}
              className="inline-flex items-center rounded-md border border-re-border px-4 py-2 text-ui text-re-text-secondary transition-colors duration-120 hover:border-re-border-strong hover:text-re-text-primary motion-reduce:transition-none"
            >
              {cte.tab}
            </a>
          ))}
        </nav>

        <div className="space-y-12">
          {CTE_TABS.map((cte) => (
            <div key={cte.id} id={cte.id} className="scroll-mt-24">
              <h3 className="text-heading text-re-text-primary">{cte.tab} tab</h3>
              <p className="mt-1 font-mono text-label text-re-text-muted">{cte.cfr}</p>
              <p className="mt-2 max-w-[68ch] text-ui text-re-text-secondary">{cte.who}</p>
              <div className="mt-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Key Data Element</TableHead>
                      <TableHead>Columns in the sheet</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cte.kdes.map((row) => (
                      <TableRow key={row.kde}>
                        <TableCell className="align-top">{row.kde}</TableCell>
                        <TableCell className="align-top text-re-text-tertiary">{row.columns}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* - EXAMPLE WORKBOOK - */}
      <Section
        id="example"
        width="marketing"
        eyebrow="Free download"
        title="Example workbook"
      >
        <Card padding="compact" className="max-w-[68ch]">
          <p className="text-ui text-re-text-secondary">
            One tab per Critical Tracking Event above, with FDA&apos;s Key Data Element column headers and one or two made up rows per tab. Every example business, address, phone number, lot code, and document number is invented and marked EXAMPLE. It is not an FDA form. Delete the example rows, then add your own records.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button asChild>
              <a href={EXAMPLE_FILE} download>
                Download the example workbook (.xlsx)
                <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </a>
            </Button>
            <Button asChild variant="secondary">
              <a href={FDA_TEMPLATE_URL} target="_blank" rel="noopener noreferrer">
                FDA&apos;s template (PDF)
                <ExternalLink className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </a>
            </Button>
          </div>
        </Card>
      </Section>

      {/* - FAQ - */}
      <Section width="marketing" title="Common questions">
        <div className="max-w-[68ch] space-y-8">
          {FAQS.map((faq) => (
            <div key={faq.q}>
              <h3 className="text-subheading text-re-text-primary">{faq.q}</h3>
              <p className="mt-2 text-ui text-re-text-secondary">{faq.a}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* - SOURCES - */}
      <Section width="marketing" title="FDA sources">
        <ul className="max-w-[68ch] space-y-3 text-ui text-re-text-secondary">
          <li>
            <a href={FDA_TEMPLATE_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              FDA FSMA Food Traceability Rule: downloadable, electronic, sortable spreadsheet template
            </a>
          </li>
          <li>
            <a href={FDA_SECG_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              Requirements for Additional Traceability Records for Certain Foods: Small Entity Compliance Guide
            </a>
          </li>
          <li>
            <a href={FDA_RULE_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              FSMA Final Rule on Requirements for Additional Traceability Records for Certain Foods
            </a>
          </li>
        </ul>
      </Section>

      {/* - REGENGINE - */}
      <Section width="marketing" tone="inset">
        <div className="mx-auto max-w-[640px] text-center">
          <p className="font-mono text-label uppercase text-re-text-muted">RegEngine (Beta)</p>
          <h2 className="mt-4 font-display text-heading-lg text-re-text-primary">
            Keeping these records in one place
          </h2>
          <p className="mx-auto mt-4 max-w-[500px] text-body text-re-text-secondary">
            RegEngine is in Beta and helps teams organize traceability records for FSMA 204. You can upload records as CSV today. Questions about your sheet are welcome by email.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <a href={`mailto:${CONTACT_EMAIL}`}>
                <Mail className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                {CONTACT_EMAIL}
              </a>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/fsma-204">
                FSMA 204 guide
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
          </div>
        </div>
      </Section>
    </div>
  );
}
