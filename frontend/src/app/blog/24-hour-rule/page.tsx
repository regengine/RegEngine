import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, Clock, CheckCircle, AlertTriangle, FileText, Shield, Zap, List, Timer, Building2, Truck, Leaf, Package, RefreshCw } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export const metadata: Metadata = {
  title: 'The 24-Hour Rule: How Fast Must You Respond to an FDA Records Request? | RegEngine',
  description:
    'FSMA 204 requires traceability records within 24 hours of an FDA request. Learn what the FDA actually asks for, what a compliant response looks like, and how to close the gap between spreadsheets and real-time compliance.',
  keywords: [
    'food recall response time requirements',
    'FDA 24 hour response food safety',
    'FSMA 204 records request',
    'FDA traceability records',
    '21 CFR Part 1 Subpart S',
    'food traceability rule',
    'FDA Food Traceability List',
    'critical tracking events',
    'FSMA 204 compliance',
    'FDA records request deadline',
  ],
  openGraph: {
    title: 'The 24-Hour Rule: How Fast Must You Respond to an FDA Records Request?',
    description:
      'FSMA 204 requires traceability records within 24 hours of an FDA request. Here is what compliance actually looks like.',
    url: 'https://www.regengine.co/blog/24-hour-rule',
    type: 'article',
  },
};

/* ── Data ─────────────────────────────────────────────────────── */

const CTE_TYPES = [
  {
    name: 'Harvesting',
    icon: Leaf,
    description:
      'Where food safety begins. The harvesting CTE captures the farm or growing area, the date of harvest, and the initial Traceability Lot Code (TLC) assigned to that batch. Without a clean harvesting record, the entire downstream chain is untraceable.',
    kdes: ['Commodity', 'Harvest date', 'Location (farm/field)', 'TLC assigned', 'Quantity and unit of measure'],
  },
  {
    name: 'Cooling',
    icon: Timer,
    description:
      'For temperature-sensitive FTL foods, the cooling CTE records when product was cooled after harvest. This is the first point where time-temperature abuse can compromise safety, and the FDA wants to see that the cold chain started promptly.',
    kdes: ['Cooling date', 'Cooling location', 'TLC of cooled product', 'Quantity cooled'],
  },
  {
    name: 'Initial Packing',
    icon: Package,
    description:
      'The packing CTE captures when raw product is first packaged for distribution. This is where TLCs may be reassigned or refined, and where pack-level traceability begins. A common gap: the pack record does not reference the original harvest TLC.',
    kdes: ['Packing date', 'Packing location', 'TLC of packed food', 'Quantity packed', 'TLC source reference (harvest lot)'],
  },
  {
    name: 'First Land-Based Receiving',
    icon: Building2,
    description:
      'For imported foods, this CTE records the first point of entry onto US soil. It bridges international supply chains to the domestic traceability system and is where FDA scrutiny is often highest during an investigation.',
    kdes: ['Receiving date', 'Entry number', 'Port of entry', 'TLC', 'Immediate previous source'],
  },
  {
    name: 'Shipping',
    icon: Truck,
    description:
      'Every time an FTL food changes hands, the shipper must record the event. Shipping CTEs create the chain-of-custody links that let investigators trace product forward from a contamination source to every retail endpoint.',
    kdes: ['Ship date', 'TLC', 'Quantity', 'Receiving location', 'Carrier and transport info'],
  },
  {
    name: 'Receiving',
    icon: Package,
    description:
      'The mirror of shipping. The receiver independently records what arrived, from whom, and with what TLC. Discrepancies between shipping and receiving records are red flags during an FDA investigation and can trigger deeper audits.',
    kdes: ['Receive date', 'TLC', 'Quantity and unit of measure', 'Immediate previous source', 'Receiving location'],
  },
  {
    name: 'Transformation',
    icon: RefreshCw,
    description:
      'When raw ingredients become a new product, the transformation CTE links input lots to output lots. This is the most complex CTE type because one output product may draw from dozens of input lots, each with its own TLC lineage.',
    kdes: ['Transformation date', 'Input TLCs (all source lots)', 'New TLC assigned to output', 'Quantity of output', 'Transformation location'],
  },
];

/* ── Component ────────────────────────────────────────────────── */

export default function TwentyFourHourRulePage() {
  return (
    <div className="re-page">
      {/* Header */}
      <div
        style={{
          borderBottom: `1px solid ${T.border}`,
          padding: '32px 24px 40px',
          background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, transparent 50%)',
        }}
      >
        <div className="max-w-[780px] mx-auto">
          <Link
            href="/blog"
            className="inline-flex items-center gap-2 mb-6"
            style={{ color: T.accent, fontSize: '14px', textDecoration: 'none' }}
          >
            <ArrowLeft className="w-4 h-4" />
            Back to blog
          </Link>

          <div className="flex items-center gap-3 mb-4">
            <span
              style={{
                background: T.accentBg,
                color: T.accent,
                fontSize: '11px',
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: '4px',
                textTransform: 'uppercase',
              }}
            >
              FSMA 204
            </span>
            <span style={{ color: T.textDim, fontSize: '13px' }}>2026-03-27</span>
          </div>

          <h1
            style={{
              color: T.heading,
              fontSize: '32px',
              fontWeight: 700,
              lineHeight: 1.25,
              marginBottom: '16px',
              letterSpacing: '-0.02em',
            }}
          >
            The 24-Hour Rule: How Fast Must You Respond to an FDA Records Request?
          </h1>
          <p style={{ color: T.textMuted, fontSize: '17px', lineHeight: 1.6, maxWidth: '640px' }}>
            FSMA 204 gives you exactly 24 hours to produce complete traceability records when the
            FDA comes calling. Most companies are not ready. Here is what the regulation actually
            requires and what a compliant response looks like.
          </p>
        </div>
      </div>

      {/* Article Body */}
      <article style={{ padding: '48px 24px 80px' }}>
        <div className="max-w-[780px] mx-auto" style={{ color: T.text, fontSize: '16px', lineHeight: 1.75 }}>

          {/* ── Section: The Regulation ──────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              What the Law Actually Says
            </h2>
            <p className="mb-4">
              Section 204(d) of the FDA Food Safety Modernization Act (FSMA) established a new
              traceability records requirement for foods on the Food Traceability List (FTL). The
              implementing regulation, codified at 21 CFR Part 1, Subpart S, requires every person
              who manufactures, processes, packs, or holds an FTL food to maintain specific
              traceability records and to provide those records to the FDA within 24 hours of a
              request.
            </p>
            <p className="mb-4">
              This is not a suggestion. It is a legally binding requirement with an enforcement date
              of January 20, 2026. After that date, FDA investigators can issue a records request
              during a routine inspection, a foodborne illness outbreak investigation, or a recall
              event, and you must produce the requested records within 24 hours.
            </p>

            <div
              style={{
                background: T.surface,
                border: `1px solid ${T.border}`,
                borderRadius: T.cardRadius,
                padding: '20px 24px',
                marginBottom: '16px',
              }}
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-500 mt-1 shrink-0" />
                <div>
                  <p style={{ color: T.heading, fontWeight: 600, marginBottom: '6px' }}>
                    Key distinction: 24 hours, not 24 business hours
                  </p>
                  <p style={{ color: T.textMuted, fontSize: '14px', lineHeight: 1.6 }}>
                    The regulation specifies 24 hours from the time of request. If the FDA issues a
                    records request at 4:00 PM on Friday, your deadline is 4:00 PM Saturday, not
                    Monday morning. There is no weekend or holiday exception in the regulatory text.
                  </p>
                </div>
              </div>
            </div>

            <p>
              The 24-hour window applies specifically to records requests issued under 21 CFR
              1.1455. The FDA may request records for a specific food, a specific Traceability Lot
              Code, a specific time period, or any combination. The request may cover a single
              Critical Tracking Event or the full chain of custody from harvesting through retail.
            </p>
          </section>

          {/* ── Section: What FDA Actually Requests ─────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              What the FDA Actually Requests
            </h2>
            <p className="mb-4">
              An FDA records request under FSMA 204 is not a vague ask for &ldquo;any records you
              have.&rdquo; The regulation defines exactly what you must produce: all traceability
              records for specified foods on the Food Traceability List that are within your
              possession, custody, or control.
            </p>
            <p className="mb-4">In practice, this means the FDA will ask for some or all of the following:</p>

            <ol className="mb-6 space-y-3 pl-6" style={{ listStyleType: 'decimal' }}>
              <li>
                <strong style={{ color: T.heading }}>Critical Tracking Event (CTE) records</strong>{' '}
                for every point where the food was harvested, cooled, packed, shipped, received, or
                transformed within your operation.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Key Data Elements (KDEs)</strong> for each CTE:
                the specific data points the regulation requires at each event, including
                Traceability Lot Codes, dates, locations, quantities, and source references.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Traceability plan</strong>: your written
                document describing how you maintain traceability for FTL foods, including procedures
                for assigning TLCs and recording CTEs.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Sortable, electronic format preferred</strong>:
                while the regulation does not mandate a specific file format, the FDA has indicated
                that electronic, sortable spreadsheets (CSV, Excel) are strongly preferred over paper
                or PDF records. A sortable format lets investigators cross-reference lot codes across
                supply chain partners quickly.
              </li>
            </ol>

            <p className="mb-4">
              The scope of the request depends on the investigation. During a multi-state outbreak,
              the FDA may request all receiving records for a specific commodity over a 90-day
              window. During a targeted recall, they may ask for the full forward-trace of a single
              lot code, from the point of contamination through every downstream recipient.
            </p>
            <p>
              In either case, your records must be complete, internally consistent, and traceable.
              A response that is missing KDEs, contains conflicting lot codes, or cannot link
              receiving events to their upstream shipping events is not a compliant response, even
              if delivered within 24 hours.
            </p>
          </section>

          {/* ── Section: The Reality Gap ─────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              The Reality Gap: Why Most Companies Cannot Hit 24 Hours
            </h2>
            <p className="mb-4">
              The 24-hour requirement was designed for an industry that maintains electronic,
              queryable records systems. The reality is that most small and mid-size food companies
              still rely on a patchwork of spreadsheets, paper logs, email chains, and ERP exports to
              manage traceability.
            </p>
            <p className="mb-6">
              Industry surveys consistently show that companies using manual traceability systems
              take 3 to 7 days to compile a complete response to a mock records request. Some take
              longer. The bottlenecks are predictable:
            </p>

            <div className="space-y-4 mb-6">
              {[
                {
                  title: 'Scattered data sources',
                  desc: 'CTE records live in different spreadsheets, different departments, sometimes different software systems. Receiving logs are in the warehouse ERP. Shipping records are in the logistics platform. Harvest records are on paper in a binder at the farm. Assembling a complete picture means pulling data from 4-8 different sources.',
                },
                {
                  title: 'Inconsistent lot code formats',
                  desc: 'Without a system enforcing TLC format standards, lot codes drift. One team uses "LOT-2026-001", another uses "20260120-A", a third uses the supplier\'s lot code verbatim. When the FDA asks to trace lot code X, finding every record that references it requires manual search across inconsistent naming conventions.',
                },
                {
                  title: 'Missing Key Data Elements',
                  desc: 'FSMA 204 requires specific KDEs at each CTE. Most spreadsheet-based systems were not designed for this regulation and are missing fields like TLC source reference, immediate previous source, or the specific quantity and unit of measure format the regulation requires. Filling in gaps after the fact is slow and error-prone.',
                },
                {
                  title: 'No automated linking between events',
                  desc: 'In a compliant system, a receiving record links to its upstream shipping record via TLC and source reference. In spreadsheet-based systems, these links either do not exist or must be reconstructed manually during an investigation. This reconstruction is the single largest time sink.',
                },
                {
                  title: 'Validation happens at response time, not at data entry',
                  desc: 'When you discover that a CTE record is missing a required KDE during an FDA request, it is too late. The data either exists or it does not. Companies using manual systems often discover gaps only when they try to assemble a response package.',
                },
              ].map((item) => (
                <div
                  key={item.title}
                  style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: T.cardRadius,
                    padding: '16px 20px',
                  }}
                >
                  <p style={{ color: T.heading, fontWeight: 600, marginBottom: '6px', fontSize: '15px' }}>
                    {item.title}
                  </p>
                  <p style={{ color: T.textMuted, fontSize: '14px', lineHeight: 1.6 }}>{item.desc}</p>
                </div>
              ))}
            </div>

            <p>
              The result is a response that arrives late, arrives incomplete, or arrives with
              internal inconsistencies that raise more questions than they answer. None of these
              outcomes are good during a food safety investigation.
            </p>
          </section>

          {/* ── Section: Compliant Response ──────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              What a Compliant Response Actually Looks Like
            </h2>
            <p className="mb-4">
              A compliant 24-hour response is not just fast. It is complete, consistent, and
              structured in a way that FDA investigators can immediately use. Here is what
              distinguishes a compliant response from a rushed data dump:
            </p>

            <ol className="mb-6 space-y-4 pl-6" style={{ listStyleType: 'decimal' }}>
              <li>
                <strong style={{ color: T.heading }}>Complete CTE coverage</strong>: every Critical
                Tracking Event within your operation for the requested food and time period is
                accounted for. No gaps, no &ldquo;we will send that separately.&rdquo;
              </li>
              <li>
                <strong style={{ color: T.heading }}>All required KDEs populated</strong>: every CTE
                record includes all Key Data Elements required by the regulation for that event type.
                TLC, date, location, quantity, unit of measure, source references &mdash; all
                present.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Internally consistent TLC references</strong>:
                lot codes in your shipping records match the lot codes in the corresponding receiving
                records. TLC source references trace back to valid upstream CTEs. There are no
                orphaned lot codes.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Sortable electronic format</strong>: records
                delivered as CSV or structured data that investigators can filter, sort, and
                cross-reference with records from other supply chain partners.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Traceability plan included</strong>: your
                written traceability plan, describing your TLC assignment procedures, CTE recording
                processes, and responsible personnel.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Delivered within the 24-hour window</strong>:
                timestamped delivery, ideally with a confirmation receipt, proving the response was
                provided within the regulatory deadline.
              </li>
            </ol>

            <div
              style={{
                background: T.accentBg,
                border: `1px solid ${T.accentBorder}`,
                borderRadius: T.cardRadius,
                padding: '20px 24px',
              }}
            >
              <div className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-emerald-500 mt-1 shrink-0" />
                <div>
                  <p style={{ color: T.heading, fontWeight: 600, marginBottom: '6px' }}>
                    The gold standard: query, validate, export, deliver
                  </p>
                  <p style={{ color: T.text, fontSize: '14px', lineHeight: 1.6 }}>
                    Companies with electronic traceability systems can query all relevant CTE records
                    by lot code or time period, run automated validation to confirm KDE completeness,
                    export a structured file, and deliver it to the FDA &mdash; often in under an
                    hour. The 24-hour window becomes comfortable rather than impossible.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Section: 7 CTE Types ────────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '8px',
                letterSpacing: '-0.01em',
              }}
            >
              The 7 Critical Tracking Event Types and Why Each Matters
            </h2>
            <p className="mb-6" style={{ color: T.textMuted }}>
              Understanding these is essential because an FDA records request will reference specific
              CTE types. If you do not have a record for a CTE that occurred within your operation,
              your response is incomplete.
            </p>

            <div className="space-y-5">
              {CTE_TYPES.map((cte) => {
                const Icon = cte.icon;
                return (
                  <div
                    key={cte.name}
                    style={{
                      background: T.surface,
                      border: `1px solid ${T.border}`,
                      borderRadius: T.cardRadius,
                      padding: '20px 24px',
                    }}
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <Icon className="w-5 h-5 text-emerald-500 shrink-0" />
                      <h3 style={{ color: T.heading, fontWeight: 600, fontSize: '16px' }}>
                        {cte.name}
                      </h3>
                    </div>
                    <p style={{ color: T.text, fontSize: '14px', lineHeight: 1.65, marginBottom: '12px' }}>
                      {cte.description}
                    </p>
                    <div>
                      <p
                        style={{
                          color: T.textMuted,
                          fontSize: '12px',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                          marginBottom: '6px',
                        }}
                      >
                        Required KDEs
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {cte.kdes.map((kde) => (
                          <span
                            key={kde}
                            style={{
                              background: T.accentBg,
                              color: T.accent,
                              fontSize: '12px',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontFamily: T.fontMono,
                            }}
                          >
                            {kde}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ── Section: Timeline ────────────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              Anatomy of a 24-Hour Records Request: Hour by Hour
            </h2>
            <p className="mb-6">
              To make the deadline concrete, here is what a realistic response timeline looks like
              for a company with an electronic traceability system versus one relying on
              spreadsheets.
            </p>

            <div className="grid md:grid-cols-2 gap-6 mb-6">
              {/* Automated */}
              <div
                style={{
                  background: T.accentBg,
                  border: `1px solid ${T.accentBorder}`,
                  borderRadius: T.cardRadius,
                  padding: '20px 24px',
                }}
              >
                <div className="flex items-center gap-2 mb-4">
                  <Zap className="w-5 h-5 text-emerald-500" />
                  <h3 style={{ color: T.heading, fontWeight: 600, fontSize: '15px' }}>
                    Electronic System
                  </h3>
                </div>
                <ul className="space-y-2" style={{ color: T.text, fontSize: '14px' }}>
                  <li><strong style={{ color: T.heading }}>Hour 0-1:</strong> Receive request, query system by TLC and date range.</li>
                  <li><strong style={{ color: T.heading }}>Hour 1-2:</strong> Review automated validation report, confirm KDE completeness.</li>
                  <li><strong style={{ color: T.heading }}>Hour 2-3:</strong> Export structured CSV, attach traceability plan.</li>
                  <li><strong style={{ color: T.heading }}>Hour 3-4:</strong> Deliver to FDA, log confirmation.</li>
                  <li className="pt-2" style={{ color: T.accent, fontWeight: 600 }}>Total: 2-4 hours. Deadline met with margin.</li>
                </ul>
              </div>

              {/* Manual */}
              <div
                style={{
                  background: T.warningBg,
                  border: `1px solid ${T.warningBorder}`,
                  borderRadius: T.cardRadius,
                  padding: '20px 24px',
                }}
              >
                <div className="flex items-center gap-2 mb-4">
                  <FileText className="w-5 h-5 text-amber-500" />
                  <h3 style={{ color: T.heading, fontWeight: 600, fontSize: '15px' }}>
                    Spreadsheet-Based
                  </h3>
                </div>
                <ul className="space-y-2" style={{ color: T.text, fontSize: '14px' }}>
                  <li><strong style={{ color: T.heading }}>Hour 0-4:</strong> Identify which spreadsheets contain relevant records.</li>
                  <li><strong style={{ color: T.heading }}>Hour 4-12:</strong> Pull data from 4-8 sources, reconcile lot code formats.</li>
                  <li><strong style={{ color: T.heading }}>Hour 12-24:</strong> Fill in missing KDEs, build a unified export file.</li>
                  <li><strong style={{ color: T.heading }}>Hour 24+:</strong> Discover gaps in TLC source references, scramble to reconstruct.</li>
                  <li className="pt-2" style={{ color: T.warning, fontWeight: 600 }}>Total: 3-7 days. Deadline missed.</li>
                </ul>
              </div>
            </div>

            <p>
              The difference is not about staffing or effort. It is about whether your data is
              structured and queryable at the time the request arrives. If it is, the 24-hour
              window is straightforward. If it is not, no amount of overtime will consistently close
              the gap.
            </p>
          </section>

          {/* ── Section: Consequences ────────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              What Happens If You Miss the Deadline
            </h2>
            <p className="mb-4">
              The FSMA framework treats failure to produce records as a serious compliance
              violation. The FDA has a graduated enforcement toolkit:
            </p>

            <ul className="mb-6 space-y-3 pl-6" style={{ listStyleType: 'disc' }}>
              <li>
                <strong style={{ color: T.heading }}>Warning letters</strong>: FDA can issue a
                public warning letter citing your failure to maintain or produce required traceability
                records. Warning letters are published on the FDA website and can affect customer
                and retailer relationships.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Import alerts</strong>: for importers, failure
                to produce records can result in detention of incoming shipments without physical
                examination.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Facility registration suspension</strong>: in
                severe cases, the FDA can suspend a food facility&apos;s registration, effectively
                prohibiting the facility from manufacturing, processing, packing, or holding food
                for US distribution.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Retailer consequences</strong>: major retailers
                including Walmart, Costco, and Kroger are increasingly requiring FSMA 204 compliance
                as a condition of doing business. Failure to demonstrate compliance can result in
                loss of distribution, independent of any FDA enforcement action.
              </li>
            </ul>

            <p>
              Beyond enforcement, there is a practical reality: if you cannot produce traceability
              records during a foodborne illness investigation, the scope of a recall expands. Without
              precise lot-level traceability, companies default to recalling everything produced
              during a broad time window rather than only the affected lots. The financial cost of
              over-inclusive recalls dwarfs the cost of a proper traceability system.
            </p>
          </section>

          {/* ── Section: Getting Ready ──────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              How to Get Ready Before Enforcement Begins
            </h2>
            <p className="mb-4">
              Whether you build your own system or use a platform, the requirements are the same.
              A 24-hour-ready traceability system must do four things:
            </p>

            <ol className="mb-6 space-y-3 pl-6" style={{ listStyleType: 'decimal' }}>
              <li>
                <strong style={{ color: T.heading }}>Capture all 7 CTE types with complete KDEs at the time of the event.</strong>{' '}
                Not after the fact, not during an investigation. At the time product is harvested,
                cooled, packed, shipped, received, or transformed.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Validate data on entry.</strong>{' '}
                Every CTE record should be checked for required KDEs, valid TLC format, and valid
                source references before it is stored. Catching errors at data entry is cheap.
                Discovering them during an FDA request is expensive.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Support query by TLC, date range, and food type.</strong>{' '}
                The FDA will request records using these dimensions. Your system must be able to
                filter and return matching records in minutes, not days.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Export in a sortable, structured format.</strong>{' '}
                CSV is the baseline. The ability to produce a pre-validated export package, including
                a KDE completeness summary, is what separates a smooth response from a scramble.
              </li>
            </ol>

            <p>
              RegEngine is built specifically for this workflow. The platform validates CTE records
              against FSMA 204 requirements at ingest time, maintains TLC linkage across the supply
              chain, and can produce a complete, validated records package in response to an FDA
              request in minutes rather than days.
            </p>
            <p className="mt-4">
              If you want to see how this works in practice, the{' '}
              <Link href="/walkthrough" style={{ color: T.accent, textDecoration: 'underline' }}>
                product walkthrough
              </Link>{' '}
              shows the full flow from data ingest through records request response.
            </p>
          </section>

          {/* ── Section: Checklist ──────────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              24-Hour Readiness Checklist
            </h2>
            <p className="mb-6">
              Use this checklist to evaluate whether your current system can meet the 24-hour
              deadline. If you answer &ldquo;no&rdquo; to any of these, you have a gap that needs
              to be closed before enforcement begins.
            </p>

            <div
              style={{
                background: T.surface,
                border: `1px solid ${T.border}`,
                borderRadius: T.cardRadius,
                padding: '24px',
              }}
            >
              <ul className="space-y-4">
                {[
                  'Can you query all CTE records for a specific TLC within 30 minutes?',
                  'Are all 7 CTE types captured electronically with complete KDEs?',
                  'Do your TLC source references link back to valid upstream CTEs?',
                  'Can you produce a sortable CSV export of filtered records on demand?',
                  'Is your traceability plan documented and current?',
                  'Have you run a mock records request drill in the last 6 months?',
                  'Can you demonstrate your response capability to a retail customer during an audit?',
                  'Are receiving records automatically matched against supplier shipping records?',
                ].map((item) => (
                  <li key={item} className="flex items-start gap-3">
                    <div
                      className="shrink-0 mt-1"
                      style={{
                        width: '18px',
                        height: '18px',
                        border: `2px solid ${T.border}`,
                        borderRadius: '4px',
                      }}
                    />
                    <span style={{ color: T.text, fontSize: '14px', lineHeight: 1.5 }}>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {/* ── Section: Summary ─────────────────────────────────── */}
          <section className="mb-12">
            <h2
              style={{
                color: T.heading,
                fontSize: '24px',
                fontWeight: 600,
                marginBottom: '16px',
                letterSpacing: '-0.01em',
              }}
            >
              The Bottom Line
            </h2>
            <p className="mb-4">
              The 24-hour records request requirement is the teeth of FSMA 204. It transforms food
              traceability from a best practice into an auditable obligation with real deadlines and
              real consequences.
            </p>
            <p className="mb-4">
              The companies that will handle this smoothly are the ones that treat traceability as a
              data engineering problem, not a paperwork problem. Complete records, captured at the
              time of the event, validated on entry, and queryable on demand. That is the standard.
            </p>
            <p>
              Everything else &mdash; the 7 CTE types, the KDE requirements, the TLC linking rules
              &mdash; follows from that foundation. Get the data right, and the 24-hour window is
              routine. Get it wrong, and no amount of late-night scrambling will reliably close the
              gap.
            </p>
          </section>

          {/* ── CTA ──────────────────────────────────────────────── */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(16,185,129,0.03) 100%)',
              border: `1px solid ${T.accentBorder}`,
              borderRadius: T.cardRadius,
              padding: '32px',
              textAlign: 'center',
            }}
          >
            <h3
              style={{
                color: T.heading,
                fontSize: '20px',
                fontWeight: 600,
                marginBottom: '12px',
              }}
            >
              See how RegEngine handles a records request
            </h3>
            <p
              style={{
                color: T.textMuted,
                fontSize: '15px',
                marginBottom: '20px',
                maxWidth: '480px',
                marginLeft: 'auto',
                marginRight: 'auto',
                lineHeight: 1.6,
              }}
            >
              Walk through the full flow: ingest CTE data, validate against FSMA 204, and produce
              an FDA-ready records package in minutes.
            </p>
            <Link
              href="/walkthrough"
              className="inline-flex items-center gap-2"
              style={{
                background: T.accent,
                color: 'white',
                padding: '12px 24px',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '15px',
                textDecoration: 'none',
              }}
            >
              View the walkthrough <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </article>
    </div>
  );
}
