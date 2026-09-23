import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, Code, Database, Zap, BarChart3 } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { JSONLD } from '@/components/seo/json-ld';
import { blogPostingJsonLd } from '@/lib/blog-jsonld';

export const metadata: Metadata = {
  title: 'CTEs and KDEs Explained | FSMA 204 Data Requirements Guide | RegEngine',
  description: 'Deep dive into the 7 Critical Tracking Events (CTEs) and Key Data Elements (KDEs) your system needs to capture. Technical implementation details, data mapping, and EPCIS 2.0 formats.',
  openGraph: {
    url: 'https://regengine.co/blog/fsma-204-cte-kde-guide',
    siteName: 'RegEngine',
    title: 'CTEs and KDEs Explained | FSMA 204 Data Requirements',
    description: 'Understand the 7 Critical Tracking Events and Key Data Elements required by FDA FSMA 204 rules. Technical guide with data mapping and implementation examples.',
    type: 'article',
  },
};

export default function CTEKDEGuidePage() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={blogPostingJsonLd('fsma-204-cte-kde-guide', 'Deep dive into the 7 Critical Tracking Events (CTEs) and Key Data Elements (KDEs) your system needs to capture. Technical implementation details, data mapping, and EPCIS 2.0 formats.')} />
      <Container as="article" width="prose" className="py-12 sm:py-16">
        {/* Back to Blog Link */}
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-2 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          <ArrowRight className="h-4 w-4 rotate-180" strokeWidth={1.75} aria-hidden="true" />
          Back to Blog
        </Link>

        <PageHeader
          eyebrow="FSMA 204 Technical Guide"
          title="CTEs and KDEs Explained"
          description="A practical guide to the 7 Critical Tracking Events and Key Data Elements your system must capture for FDA FSMA 204 compliance."
          meta={
            <>
              <span>April 2026</span>
              <span>12 min read</span>
            </>
          }
        />

        <div>
          {/* Overview */}
          <Card variant="inset" padding="spacious" className="mb-10">
            <h2 className="text-heading text-re-text-primary mb-3 flex items-center gap-3">
              <Database className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              What Are CTEs and KDEs?
            </h2>
            <p className="text-re-text-secondary mb-4">
              The FDA FSMA 204 rule requires food businesses to capture and maintain specific data at critical moments in their supply chain. The rule defines two essential components:
            </p>
            <ul className="space-y-2">
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Critical Tracking Events (CTEs):</strong> Seven specific supply chain events where you must capture and record traceability data</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Key Data Elements (KDEs):</strong> The specific fields of information required at each CTE</span>
              </li>
            </ul>
          </Card>

          {/* The 7 CTEs */}
          <h2 className="text-heading text-re-text-primary mb-8 mt-12">The 7 Critical Tracking Events</h2>
          <p className="text-re-text-secondary mb-8">
            The FDA identifies seven specific points in the supply chain where traceability data must be captured. Your system must be configured to capture a specific set of Key Data Elements at each CTE.
          </p>

          {/* CTE 1: Harvesting */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">1</span>
              Harvesting
            </h3>
            <p className="text-re-text-secondary mb-4">
              For raw agricultural commodities (produce, grains, etc.), the point where the commodity is harvested from the growing environment.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Traceability Lot Code
• Product Description
• Harvest Date & Location
• Quantity & Unit of Measure
• Grower Information`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> Capture harvest location using GPS coordinates or facility identifier. Lot code must be traceable to specific field/lot/planting date combinations.
            </p>
          </Card>

          {/* CTE 2: Initial Cooling */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">2</span>
              Initial Cooling
            </h3>
            <p className="text-re-text-secondary mb-4">
              If applicable, the first cooling step applied to produce (hydrocooling, air cooling, etc.) before further processing.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Traceability Lot Code (from Harvesting)
• Cooling Date & Time
• Cooling Location
• Cooling Method
• Lot Code After Cooling`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> Link to harvest lot code via traceability lot code. Record facility temperature controls and cooling duration for audit readiness.
            </p>
          </Card>

          {/* CTE 3: Initial Packing */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">3</span>
              Initial Packing
            </h3>
            <p className="text-re-text-secondary mb-4">
              The first packing operation for raw agricultural commodities or first use of a traceability lot code for all food categories.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Traceability Lot Code
• Product Description
• Quantity & Unit of Measure
• Packing Date & Time
• Packing Location
• Packaging Information`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> This is often the first CTE for processed foods. Assign unique traceability lot code if not inherited from harvest.
            </p>
          </Card>

          {/* CTE 4: Transformation */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">4</span>
              Transformation
            </h3>
            <p className="text-re-text-secondary mb-4">
              Processing that changes the identity or characteristics of food, such as cooking, mixing, drying, fermentation, or any value-added process.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Source Traceability Lot Codes (input ingredients)
• Input Ingredient Details
• Transformation Date & Location
• Processing Method
• New Traceability Lot Code (output)
• Output Product Description & Quantity`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> Record all input ingredients with their original lot codes. Map transformation recipe/process to new lot code. Critical for backward traceability.
            </p>
          </Card>

          {/* CTE 5: Shipping */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">5</span>
              Shipping
            </h3>
            <p className="text-re-text-secondary mb-4">
              The point where you transfer food to a recipient (customer, distributor, retailer). This includes both outbound shipments and inter-facility transfers.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Traceability Lot Code
• Shipped Quantity & Unit
• Ship Date & Time
• Shipping Location (from)
• Receiving Location (to)
• Recipient Information
• Shipping Container ID (optional but recommended)`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> Capture recipient name, address, and contact info. This is critical for the 24-hour recall response requirement.
            </p>
          </Card>

          {/* CTE 6: Receiving */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">6</span>
              Receiving
            </h3>
            <p className="text-re-text-secondary mb-4">
              When you receive food from your suppliers. All food received (whether from suppliers or in-house transfers) must be tracked at receipt.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs:
• Traceability Lot Code (from supplier)
• Product Description
• Quantity Received & Unit
• Receive Date & Time
• Receiving Location
• Supplier Information
• Condition Upon Receipt (optional but recommended)`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> Match received lot codes to supplier traceability lot codes. Flag discrepancies. This is your first point of control for incoming food safety.
            </p>
          </Card>

          {/* CTE 7: First Land-Based Receiving */}
          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-3 flex items-center gap-3">
              <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-ui tabular-nums text-re-text-muted">7</span>
              First Land-Based Receiving
            </h3>
            <p className="text-re-text-secondary mb-4">
              Per §1.1335, this CTE applies <strong>only</strong> to food obtained from a fishing vessel — the first land-based receiver of seafood landed by a vessel. Non-seafood imports follow the §1.1345 Receiving CTE instead, not this one.
            </p>
            <div className="mb-4 overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-small text-re-text-secondary">
              <code>{`Required KDEs (per §1.1335):
• Traceability Lot Code (assigned at first land-based receiving)
• Species and harvest date range
• NMFS Ocean Geographic Area of harvest
• Vessel name (and unique vessel ID, if applicable)
• Date of landing
• Quantity and unit of measure
• Reference Document Type and Number`}</code>
            </div>
            <p className="text-ui text-re-text-secondary">
              <strong>Implementation note:</strong> If you are an importer of non-seafood Food Traceability List items, your obligation is §1.1345 Receiving (subject to the §1.1305(j) restaurant/RFE exemption when selling food directly to consumers) — not §1.1335.
            </p>
          </Card>

          {/* KDE Requirements Overview */}
          <h2 className="text-heading text-re-text-primary mb-8 mt-12 flex items-center gap-3">
            <BarChart3 className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Understanding Key Data Elements
          </h2>

          <Card variant="inset" padding="spacious" className="mb-8">
            <h3 className="text-subheading text-re-text-primary mb-4">Common KDEs across CTEs</h3>
            <p className="text-re-text-secondary mb-6">
              These KDEs recur across most CTEs, though the exact set required at each event differs by §§1.1325–1.1350. Confirm the specific KDE list against the section that governs the event at your operation:
            </p>
            <ul className="space-y-3">
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Traceability Lot Code:</strong> Unique identifier for the traceable food lot. Must link all CTEs in the supply chain.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Product Description:</strong> Name of food, including brand, form (fresh/processed), variety, and other identifiers.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Quantity and Unit of Measure:</strong> Amount and unit (cases, pounds, units, etc.).</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Location Name/ID:</strong> Facility name and address or identifier where the event occurred.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Event Type:</strong> The CTE name (Harvesting, Packing, Receiving, etc.).</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Event Date/Time:</strong> When the CTE occurred (ISO 8601 format: 2026-02-05T08:30:00Z).</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Supplier/Recipient Information:</strong> Name and contact for the entity providing or receiving the food.</span>
              </li>
            </ul>
          </Card>

          {/* Data Format & Technical Implementation */}
          <h2 className="text-heading text-re-text-primary mb-8 mt-12 flex items-center gap-3">
            <Code className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            EPCIS 2.0 Data Format
          </h2>

          <p className="text-re-text-secondary mb-6">
            EPCIS 2.0 can support trading-partner interoperability, and some buyers may request it. FDA records requests may require records, including an electronic sortable spreadsheet under 21 CFR 1.1455(c)(3), unless an exemption or agreed alternative applies. Here is a simplified EPCIS-style example:
          </p>

          <Card variant="inset" className="mb-8 overflow-hidden">
            <div className="border-b border-re-border-subtle px-4 py-2">
              <span className="font-mono text-label uppercase text-re-text-muted">EPCIS 2.0 Event Example (JSON-LD)</span>
            </div>
            <pre className="m-0 overflow-x-auto p-5 font-mono text-small leading-relaxed text-re-text-secondary">
              <code>{`{
  "@context": "https://ref.gs1.org/standards/epcis",
  "type": "EPCISDocument",
  "version": "2.0",
  "events": [{
    "type": "ObjectEvent",
    "eventID": "urn:uuid:a1b2c3d4-...",
    "eventTime": "2026-02-05T08:30:00Z",
    "eventTimeZoneOffset": "-08:00",
    "action": "RECEIVE",
    "bizLocation": "urn:epc:id:sgln:00012345.00001.0",
    "readPoint": "urn:epc:id:sgln:00012345.00001.1",
    "epcList": [
      "urn:epc:id:sgtin:00012345.00001.LOT-2026-001"
    ],
    "quantityList": [{
      "epcClass": "urn:epc:class:sgtin:00012345.00001.1",
      "quantity": 500,
      "uom": "case"
    }],
    "bizTransactionList": [{
      "type": "po",
      "bizTransaction": "urn:epc:id:biz:po:supplier123"
    }],
    "extension": {
      "traceabilityLotCode": "00012345678901-LOT-2026-001",
      "productDescription": "Romaine Lettuce",
      "receivingLocation": "Distribution Center #4"
    }
  }]
}`}</code>
            </pre>
          </Card>

          <p className="text-re-text-secondary mb-8">
            <strong>Note:</strong> Your system should generate EPCIS-compliant events automatically from CTE capture forms. The key is ensuring all required KDEs are captured and properly formatted.
          </p>

          {/* System Architecture */}
          <h2 className="text-heading text-re-text-primary mb-8 mt-12 flex items-center gap-3">
            <Zap className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Building Your CTE/KDE System
          </h2>

          <div className="space-y-6 mb-8">
            <Card variant="inset" padding="spacious">
              <h3 className="text-subheading text-re-text-primary mb-3">Step 1: Map Your CTEs</h3>
              <p className="text-re-text-secondary mb-4">
                Identify which of the 7 CTEs apply to your business. Most food businesses won't need all 7:
              </p>
              <ul className="list-disc space-y-2 pl-5 text-body text-re-text-secondary marker:text-re-text-tertiary">
                <li>Growers: Harvesting + Cooling + Initial Packing + Shipping</li>
                <li>Processors: Initial Packing + Transformation + Shipping</li>
                <li>Distributors: Receiving + Shipping (+ optional Transformation if repackaging)</li>
                <li>Importers: First Land-Based Receiving + optional downstream CTEs</li>
              </ul>
            </Card>

            <Card variant="inset" padding="spacious">
              <h3 className="text-subheading text-re-text-primary mb-3">Step 2: Design Data Capture Forms</h3>
              <p className="text-re-text-secondary">
                Create forms for each CTE that capture required KDEs. Build validation rules (lot code format, date format, required fields, etc.). Integrate with your ERP or inventory system to auto-populate supplier/location data.
              </p>
            </Card>

            <Card variant="inset" padding="spacious">
              <h3 className="text-subheading text-re-text-primary mb-3">Step 3: Implement Lot Code Tracking</h3>
              <p className="text-re-text-secondary mb-3">
                Design your traceability lot code format. It should be:
              </p>
              <ul className="list-disc space-y-2 pl-5 text-body text-re-text-secondary marker:text-re-text-tertiary">
                <li><strong>Unique:</strong> No two lots can have the same code</li>
                <li><strong>Traceable:</strong> Code must be linkable across all CTEs</li>
                <li><strong>Consistent:</strong> Format stays the same throughout supply chain (or mapped clearly)</li>
              </ul>
            </Card>

            <Card variant="inset" padding="spacious">
              <h3 className="text-subheading text-re-text-primary mb-3">Step 4: Build Backward/Forward Traceability Queries</h3>
              <p className="text-re-text-secondary">
                Your system must be able to answer: "What suppliers provided ingredients in this lot?" (backward) and "What customers received this lot?" (forward). Test these queries monthly.
              </p>
            </Card>

            <Card variant="inset" padding="spacious">
              <h3 className="text-subheading text-re-text-primary mb-3">Step 5: Establish 24-Hour Response Protocol</h3>
              <p className="text-re-text-secondary">
                Document your process for responding to FDA requests within 24 hours. You must be able to identify affected lots, notify customers, and provide traceability records rapidly.
              </p>
            </Card>
          </div>

          {/* Key Takeaways */}
          <Card variant="inset" padding="spacious" className="mb-10">
            <h3 className="text-subheading text-re-text-primary mb-4 flex items-center gap-3">
              <CheckCircle2 className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              Key Takeaways
            </h3>
            <ul className="space-y-3">
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>The 7 CTEs are fixed by regulation. Your job is identifying which apply to your business and capturing KDEs at each one.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>KDEs are the actual data fields (lot code, date, location, etc.). You must capture all 7 universal KDEs at every CTE.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Traceability lot code is the thread linking all CTEs. If you can't trace a lot through harvest → receiving → shipping → customer, your system is incomplete.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>EPCIS 2.0 can support trading-partner interoperability; confirm buyer and retailer format requirements directly.</span>
              </li>
              <li className="flex items-start gap-3 text-re-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Your 24-hour response time depends on real-time traceability queries. Test your backward/forward traceability monthly.</span>
              </li>
            </ul>
          </Card>

          {/* Next Steps */}
          <h2 className="text-heading text-re-text-primary mb-6 mt-12">Next Steps</h2>
          <p className="text-re-text-secondary mb-8">
            Understanding CTEs and KDEs is foundational, but implementation is where traceability work becomes operational. Start by mapping your CTEs, then build data capture workflows that integrate with your existing systems. RegEngine helps capture and review FSMA 204 traceability data in minutes instead of months.
          </p>

          <Card variant="inset" padding="spacious" className="mb-8">
            <p className="text-re-text-secondary mb-4">
              Ready to implement FSMA 204 traceability in your business? See how RegEngine handles CTE/KDE capture, validation, and EPCIS-oriented export workflows.
            </p>
            <div className="flex flex-col flex-wrap gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/retailer-readiness">
                  <span>Get Your Readiness Score</span>
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/fsma-204">Read FSMA 204 Overview</Link>
              </Button>
            </div>
          </Card>

          <p className="text-ui text-re-text-muted mb-4">
            Questions? <a href="mailto:support@regengine.co" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">Contact our team</a> for technical guidance on CTE/KDE implementation.
          </p>
        </div>
      </Container>
    </div>
  );
}
