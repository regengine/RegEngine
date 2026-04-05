import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, Code, Database, Zap, BarChart3, FileText } from 'lucide-react';

export const metadata: Metadata = {
  title: 'CTEs and KDEs Explained | FSMA 204 Data Requirements Guide | RegEngine',
  description: 'Deep dive into the 7 Critical Tracking Events (CTEs) and Key Data Elements (KDEs) your system needs to capture. Technical implementation details, data mapping, and EPCIS 2.0 formats.',
  openGraph: {
    title: 'CTEs and KDEs Explained | FSMA 204 Data Requirements',
    description: 'Understand the 7 Critical Tracking Events and Key Data Elements required by FDA FSMA 204 rules. Technical guide with data mapping and implementation examples.',
    type: 'article',
  },
};

export default function CTEKDEGuidePage() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* Back to Blog Link */}
      <div className="max-w-[800px] mx-auto px-4 sm:px-6 pt-8 pb-4">
        <Link href="/blog" className="inline-flex items-center gap-2 text-[var(--re-text-secondary)] hover:text-[var(--re-brand)] transition-colors">
          <ArrowRight className="w-4 h-4 rotate-180" />
          Back to Blog
        </Link>
      </div>

      {/* Hero Section */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          FSMA 204 Technical Guide
        </p>
        <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-4">
          CTEs and KDEs Explained
        </h1>
        <p className="text-lg text-[var(--re-text-secondary)] leading-relaxed mb-6">
          A practical guide to the 7 Critical Tracking Events and Key Data Elements your system must capture for FDA FSMA 204 compliance.
        </p>
        <div className="flex items-center gap-6 text-sm text-[var(--re-text-muted)]">
          <span>April 2026</span>
          <span>12 min read</span>
        </div>
      </section>

      {/* Main Article */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
        <article className="prose prose-invert max-w-none">
          {/* Overview */}
          <div className="mb-10 p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
            <h2 className="text-[var(--re-text-primary)] font-bold text-xl mb-3 flex items-center gap-3">
              <Database className="w-6 h-6 text-[var(--re-brand)]" />
              What Are CTEs and KDEs?
            </h2>
            <p className="text-[var(--re-text-secondary)] mb-4">
              The FDA FSMA 204 rule requires food businesses to capture and maintain specific data at critical moments in their supply chain. The rule defines two essential components:
            </p>
            <ul className="space-y-2">
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Critical Tracking Events (CTEs):</strong> Seven specific supply chain events where you must capture and record traceability data</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Key Data Elements (KDEs):</strong> The specific fields of information required at each CTE</span>
              </li>
            </ul>
          </div>

          {/* The 7 CTEs */}
          <h2 className="text-[var(--re-text-primary)] font-serif text-2xl font-bold mb-8 mt-12">The 7 Critical Tracking Events</h2>
          <p className="text-[var(--re-text-secondary)] mb-8">
            The FDA identifies seven specific points in the supply chain where traceability data must be captured. Your system must be configured to capture a specific set of Key Data Elements at each CTE.
          </p>

          {/* CTE 1: Harvesting */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">1</span>
              Harvesting
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              For raw agricultural commodities (produce, grains, etc.), the point where the commodity is harvested from the growing environment.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Traceability Lot Code
• Product Description
• Harvest Date & Location
• Quantity & Unit of Measure
• Grower Information`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Capture harvest location using GPS coordinates or facility identifier. Lot code must be traceable to specific field/lot/planting date combinations.
            </p>
          </div>

          {/* CTE 2: Initial Cooling */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">2</span>
              Initial Cooling
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              If applicable, the first cooling step applied to produce (hydrocooling, air cooling, etc.) before further processing.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Traceability Lot Code (from Harvesting)
• Cooling Date & Time
• Cooling Location
• Cooling Method
• Lot Code After Cooling`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Link to harvest lot code via traceability lot code. Record facility temperature controls and cooling duration for audit readiness.
            </p>
          </div>

          {/* CTE 3: Initial Packing */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">3</span>
              Initial Packing
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              The first packing operation for raw agricultural commodities or first use of a traceability lot code for all food categories.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Traceability Lot Code
• Product Description
• Quantity & Unit of Measure
• Packing Date & Time
• Packing Location
• Packaging Information`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> This is often the first CTE for processed foods. Assign unique traceability lot code if not inherited from harvest.
            </p>
          </div>

          {/* CTE 4: Transformation */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">4</span>
              Transformation
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              Processing that changes the identity or characteristics of food, such as cooking, mixing, drying, fermentation, or any value-added process.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Source Traceability Lot Codes (input ingredients)
• Input Ingredient Details
• Transformation Date & Location
• Processing Method
• New Traceability Lot Code (output)
• Output Product Description & Quantity`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Record all input ingredients with their original lot codes. Map transformation recipe/process to new lot code. Critical for backward traceability.
            </p>
          </div>

          {/* CTE 5: Shipping */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">5</span>
              Shipping
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              The point where you transfer food to a recipient (customer, distributor, retailer). This includes both outbound shipments and inter-facility transfers.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Traceability Lot Code
• Shipped Quantity & Unit
• Ship Date & Time
• Shipping Location (from)
• Receiving Location (to)
• Recipient Information
• Shipping Container ID (optional but recommended)`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Capture recipient name, address, and contact info. This is critical for the 24-hour recall response requirement.
            </p>
          </div>

          {/* CTE 6: Receiving */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">6</span>
              Receiving
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              When you receive food from your suppliers. All food received (whether from suppliers or in-house transfers) must be tracked at receipt.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Traceability Lot Code (from supplier)
• Product Description
• Quantity Received & Unit
• Receive Date & Time
• Receiving Location
• Supplier Information
• Condition Upon Receipt (optional but recommended)`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Match received lot codes to supplier traceability lot codes. Flag discrepancies. This is your first point of control for incoming food safety.
            </p>
          </div>

          {/* CTE 7: First Land-Based Receiving */}
          <div className="mb-8 p-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-sm font-semibold">7</span>
              First Land-Based Receiving
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-4">
              Specific to imported foods. The first receipt of food at a U.S. port of entry or facility. Required for seafood and produce imported from outside the U.S.
            </p>
            <div className="bg-black/30 rounded p-4 mb-4 font-mono text-xs text-[var(--re-text-tertiary)] overflow-x-auto">
              <code>{`Required KDEs:
• Foreign Traceability Lot Code
• Product Description
• Quantity Received
• Import Receipt Date & Location
• U.S. Lot Code (if assigned)
• Port of Entry
• Importer/Receiving Facility Info`}</code>
            </div>
            <p className="text-[var(--re-text-secondary)] text-sm">
              <strong>Implementation note:</strong> Maintain documentation of foreign supplier information and original lot codes. Link to U.S. assigned lot code if re-lotting occurs.
            </p>
          </div>

          {/* KDE Requirements Overview */}
          <h2 className="text-[var(--re-text-primary)] font-serif text-2xl font-bold mb-8 mt-12 flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-[var(--re-brand)]" />
            Understanding Key Data Elements
          </h2>

          <div className="mb-8 p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-4">The 7 Universal KDEs</h3>
            <p className="text-[var(--re-text-secondary)] mb-6">
              These KDEs are required at every CTE regardless of food category:
            </p>
            <ul className="space-y-3">
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Traceability Lot Code:</strong> Unique identifier for the traceable food lot. Must link all CTEs in the supply chain.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Product Description:</strong> Name of food, including brand, form (fresh/processed), variety, and other identifiers.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Quantity and Unit of Measure:</strong> Amount and unit (cases, pounds, units, etc.).</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Location Name/ID:</strong> Facility name and address or identifier where the event occurred.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Event Type:</strong> The CTE name (Harvesting, Packing, Receiving, etc.).</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Event Date/Time:</strong> When the CTE occurred (ISO 8601 format: 2026-02-05T08:30:00Z).</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Supplier/Recipient Information:</strong> Name and contact for the entity providing or receiving the food.</span>
              </li>
            </ul>
          </div>

          {/* Data Format & Technical Implementation */}
          <h2 className="text-[var(--re-text-primary)] font-serif text-2xl font-bold mb-8 mt-12 flex items-center gap-3">
            <Code className="w-7 h-7 text-[var(--re-brand)]" />
            EPCIS 2.0 Data Format
          </h2>

          <p className="text-[var(--re-text-secondary)] mb-6">
            The FDA recommends (and many retailers require) the EPCIS 2.0 standard for submitting traceability data. Here's a simplified example:
          </p>

          <div className="bg-black/60 rounded-lg overflow-hidden border border-[var(--re-surface-border)] mb-8">
            <div className="bg-white/5 px-4 py-2 border-b border-[var(--re-surface-border)]">
              <span className="text-xs text-[var(--re-text-muted)">EPCIS 2.0 Event Example (JSON-LD)</span>
            </div>
            <pre className="p-5 m-0 text-xs leading-relaxed overflow-x-auto text-[var(--re-text-primary)]">
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
          </div>

          <p className="text-[var(--re-text-secondary)] mb-8">
            <strong>Note:</strong> Your system should generate EPCIS-compliant events automatically from CTE capture forms. The key is ensuring all required KDEs are captured and properly formatted.
          </p>

          {/* System Architecture */}
          <h2 className="text-[var(--re-text-primary)] font-serif text-2xl font-bold mb-8 mt-12 flex items-center gap-3">
            <Zap className="w-7 h-7 text-[var(--re-brand)]" />
            Building Your CTE/KDE System
          </h2>

          <div className="space-y-6 mb-8">
            <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
              <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3">Step 1: Map Your CTEs</h3>
              <p className="text-[var(--re-text-secondary)] mb-4">
                Identify which of the 7 CTEs apply to your business. Most food businesses won't need all 7:
              </p>
              <ul className="space-y-2 text-[var(--re-text-secondary)]">
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span>Growers: Harvesting + Cooling + Initial Packing + Shipping</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span>Processors: Initial Packing + Transformation + Shipping</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span>Distributors: Receiving + Shipping (+ optional Transformation if repackaging)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span>Importers: First Land-Based Receiving + optional downstream CTEs</span>
                </li>
              </ul>
            </div>

            <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
              <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3">Step 2: Design Data Capture Forms</h3>
              <p className="text-[var(--re-text-secondary)]">
                Create forms for each CTE that capture required KDEs. Build validation rules (lot code format, date format, required fields, etc.). Integrate with your ERP or inventory system to auto-populate supplier/location data.
              </p>
            </div>

            <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
              <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3">Step 3: Implement Lot Code Tracking</h3>
              <p className="text-[var(--re-text-secondary)] mb-3">
                Design your traceability lot code format. It should be:
              </p>
              <ul className="space-y-2 text-[var(--re-text-secondary)]">
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span><strong>Unique:</strong> No two lots can have the same code</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span><strong>Traceable:</strong> Code must be linkable across all CTEs</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[var(--re-brand)] font-bold">•</span>
                  <span><strong>Consistent:</strong> Format stays the same throughout supply chain (or mapped clearly)</span>
                </li>
              </ul>
            </div>

            <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
              <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3">Step 4: Build Backward/Forward Traceability Queries</h3>
              <p className="text-[var(--re-text-secondary)]">
                Your system must be able to answer: "What suppliers provided ingredients in this lot?" (backward) and "What customers received this lot?" (forward). Test these queries monthly.
              </p>
            </div>

            <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
              <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-3">Step 5: Establish 24-Hour Response Protocol</h3>
              <p className="text-[var(--re-text-secondary)]">
                Document your process for responding to FDA requests within 24 hours. You must be able to identify affected lots, notify customers, and provide traceability records rapidly.
              </p>
            </div>
          </div>

          {/* Key Takeaways */}
          <div className="mb-10 p-6 rounded-lg bg-[var(--re-brand)]/5 border border-[var(--re-brand)]/30">
            <h3 className="text-[var(--re-text-primary)] font-bold text-lg mb-4 flex items-center gap-3">
              <CheckCircle2 className="w-6 h-6 text-[var(--re-brand)]" />
              Key Takeaways
            </h3>
            <ul className="space-y-3">
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>The 7 CTEs are fixed by regulation. Your job is identifying which apply to your business and capturing KDEs at each one.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>KDEs are the actual data fields (lot code, date, location, etc.). You must capture all 7 universal KDEs at every CTE.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Traceability lot code is the thread linking all CTEs. If you can't trace a lot through harvest → receiving → shipping → customer, your system is incomplete.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>EPCIS 2.0 is the FDA-recommended format for submitting data. Most enterprise systems will require this standard for recalls.</span>
              </li>
              <li className="flex items-start gap-3 text-[var(--re-text-secondary)]">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Your 24-hour response time depends on real-time traceability queries. Test your backward/forward traceability monthly.</span>
              </li>
            </ul>
          </div>

          {/* Next Steps */}
          <h2 className="text-[var(--re-text-primary)] font-serif text-2xl font-bold mb-6 mt-12">Next Steps</h2>
          <p className="text-[var(--re-text-secondary)] mb-8">
            Understanding CTEs and KDEs is foundational, but implementation is where compliance happens. Start by mapping your CTEs, then build data capture workflows that integrate with your existing systems. RegEngine automates this entire process, helping you capture FSMA 204 data in minutes instead of months.
          </p>

          <div className="mb-8 p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
            <p className="text-[var(--re-text-secondary)] mb-4">
              Ready to implement FSMA 204 traceability in your business? See how RegEngine handles CTE/KDE capture, validation, and EPCIS export.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 flex-wrap">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-6 py-3 rounded-lg text-sm font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-1 hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)]"
              >
                <span>Get Your Readiness Score</span>
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link
                href="/fsma-204"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-6 py-3 rounded-lg text-sm font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-1"
              >
                Read FSMA 204 Overview
              </Link>
            </div>
          </div>

          <p className="text-[var(--re-text-muted)] text-sm mb-4">
            Questions? <a href="mailto:support@regengine.co" className="text-[var(--re-brand)] hover:underline">Contact our team</a> for technical guidance on CTE/KDE implementation.
          </p>
        </article>
      </section>
    </div>
  );
}
