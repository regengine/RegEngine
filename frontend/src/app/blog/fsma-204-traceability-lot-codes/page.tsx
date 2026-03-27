import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, Hash, CheckCircle, AlertTriangle, Leaf, Package, Truck, RefreshCw, Timer, Building2, Link2, Code2 } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export const metadata: Metadata = {
  title: 'FSMA 204 Traceability Lot Codes (TLCs): The Complete Technical Guide | RegEngine',
  description:
    'A technical deep-dive into Traceability Lot Codes under FSMA 204 (21 CFR Part 1, Subpart S). Covers TLC assignment rules, GTIN + lot code structure, source references, supply chain flow, common mistakes, and JSON validation examples.',
  keywords: [
    'FSMA 204 traceability lot code',
    'TLC food traceability',
    'traceability lot code definition',
    '21 CFR 1.1310',
    'GTIN lot code',
    'food traceability lot code format',
    'FSMA 204 TLC source reference',
    'critical tracking events lot codes',
    'traceability lot code assignment',
    'FDA food traceability rule',
  ],
  openGraph: {
    title: 'FSMA 204 Traceability Lot Codes (TLCs): The Complete Technical Guide',
    description:
      'Everything you need to know about assigning, tracking, and validating Traceability Lot Codes under the FDA Food Traceability Rule.',
    url: 'https://www.regengine.co/blog/fsma-204-traceability-lot-codes',
    type: 'article',
  },
};

/* ── Data ─────────────────────────────────────────────────────── */

const TLC_BY_CTE = [
  {
    cte: 'Harvesting',
    icon: Leaf,
    who: 'The grower or farm',
    when: 'At the time of harvest, before the food leaves the growing area',
    rule: 'The harvester assigns the initial TLC. This is the origin point for the entire traceability chain. Every downstream CTE will reference back to this TLC or to a new TLC created at transformation.',
    format: 'Grower-defined. Must be unique per harvest lot. Common patterns include date + field + sequence (e.g., "20260115-F3-001") or a GTIN-based code.',
  },
  {
    cte: 'Cooling',
    icon: Timer,
    who: 'The entity performing cooling (often the farm or a third-party cooler)',
    when: 'At the time product is cooled after harvest',
    rule: 'The TLC of the cooled product is recorded. If the cooling entity is the same as the harvester, the TLC typically does not change. If a third-party cooler receives from multiple harvesters, each lot retains its original TLC.',
    format: 'Same as the harvest TLC unless repacking occurs during cooling.',
  },
  {
    cte: 'Initial Packing',
    icon: Package,
    who: 'The packhouse or packing operation',
    when: 'At the time product is first packed into consumer or case-level packaging',
    rule: 'This is a critical TLC decision point. If the packer creates new case-level or consumer-level packaging, they may assign a new TLC. The regulation requires a TLC source reference linking the new TLC back to the original harvest TLC. If no new TLC is assigned, the original TLC is carried forward.',
    format: 'Frequently uses GTIN + lot code at case level. The GTIN identifies the product, the lot code identifies the production batch.',
  },
  {
    cte: 'First Land-Based Receiving',
    icon: Building2,
    who: 'The first US-based entity receiving imported food',
    when: 'At the time of receipt on US soil',
    rule: 'The receiver records the TLC of the imported food. If the imported food does not have a TLC, the first receiver must assign one. This is the bridge between international supply chains and the FSMA 204 traceability framework.',
    format: 'May use the foreign supplier\'s lot code if it meets TLC requirements, or assign a new TLC with a source reference to the import entry.',
  },
  {
    cte: 'Shipping',
    icon: Truck,
    who: 'The entity shipping the food',
    when: 'At the time of shipment',
    rule: 'The shipper records the TLC of the food being shipped. No new TLC is assigned at shipping. The purpose is to create a chain-of-custody record linking the food (by TLC) to the recipient.',
    format: 'Same TLC as the current lot. No format change.',
  },
  {
    cte: 'Receiving',
    icon: Package,
    who: 'The entity receiving the food',
    when: 'At the time of receipt',
    rule: 'The receiver records the TLC of the food received. This must match the TLC on the shipper\'s records. Discrepancies between shipping and receiving TLCs are a compliance red flag and indicate a break in the traceability chain.',
    format: 'Same TLC as recorded by the shipper. Receiver does not assign a new TLC unless they also perform a transformation.',
  },
  {
    cte: 'Transformation',
    icon: RefreshCw,
    who: 'The entity that transforms the food (processor, manufacturer)',
    when: 'When input foods are combined, processed, or altered to create a new food product',
    rule: 'This is the only CTE where a new TLC is always assigned. The transformer records all input TLCs (source lots) and assigns a new TLC to the output product. The TLC source reference for the new TLC must list every input TLC. This many-to-one linkage is the most complex part of the TLC system.',
    format: 'Transformer-assigned. Must be unique per output lot. Typically GTIN + lot code for the finished product.',
  },
];

const COMMON_MISTAKES = [
  {
    title: 'Reassigning TLCs without a source reference',
    description:
      'When a packer or transformer assigns a new TLC, they must record the TLC source reference linking back to the input lot(s). Without this reference, the traceability chain breaks and investigators cannot trace upstream. This is the single most common compliance failure in TLC management.',
  },
  {
    title: 'Using the same TLC for different lots',
    description:
      'A TLC must uniquely identify a specific lot of food. Reusing a TLC across different harvest dates, different fields, or different production runs defeats the purpose of the system and can dramatically expand the scope of a recall.',
  },
  {
    title: 'Inconsistent TLC formats across systems',
    description:
      'When shipping records use "LOT-2026-001" and receiving records use "2026001" for the same lot, automated matching fails and manual reconciliation is required during an investigation. Standardize TLC formats with your supply chain partners before enforcement begins.',
  },
  {
    title: 'Dropping TLCs at transformation',
    description:
      'Processors sometimes record the output TLC but fail to capture all input TLCs. If a finished product draws from 15 input lots and you only record 3, the FDA cannot trace the other 12 lots forward or backward. The input TLC list must be exhaustive.',
  },
  {
    title: 'Confusing TLCs with internal production codes',
    description:
      'Internal production codes, batch numbers, and work order IDs are not TLCs unless they meet the regulation\'s requirements. A TLC must be assigned at or before a CTE, must identify a specific lot of FTL food, and must be communicated to the next entity in the supply chain.',
  },
  {
    title: 'Not communicating TLCs to downstream partners',
    description:
      'A TLC is only useful if it travels with the food. When you ship product, the TLC must be included in the shipping documentation so the receiver can record it. If you assign a TLC but do not communicate it, the receiver will create their own, and the chain breaks.',
  },
];

/* ── Component ────────────────────────────────────────────────── */

export default function TLCGuidePage() {
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
              Technical Guide
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
            FSMA 204 Traceability Lot Codes (TLCs): The Complete Technical Guide
          </h1>
          <p style={{ color: T.textMuted, fontSize: '17px', lineHeight: 1.6, maxWidth: '640px' }}>
            Traceability Lot Codes are the backbone of the FDA Food Traceability Rule. This guide
            covers the regulatory definition, assignment rules by CTE type, GTIN structures, source
            references, and common implementation mistakes.
          </p>
        </div>
      </div>

      {/* Article Body */}
      <article style={{ padding: '48px 24px 80px' }}>
        <div className="max-w-[780px] mx-auto" style={{ color: T.text, fontSize: '16px', lineHeight: 1.75 }}>

          {/* ── Section: Definition ──────────────────────────────── */}
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
              What Is a Traceability Lot Code?
            </h2>
            <p className="mb-4">
              A Traceability Lot Code (TLC) is defined in 21 CFR &sect;1.1310 as a descriptor,
              often alphanumeric, used to identify a specific lot of food. Under FSMA 204, the TLC
              is the primary key that links a physical batch of food to its traceability records
              across the entire supply chain.
            </p>
            <p className="mb-4">
              The regulation does not prescribe a specific format for TLCs. A TLC can be a lot
              number, a batch code, a production code, or any other alphanumeric string, as long as
              it uniquely identifies a specific lot and is consistently used across all CTE records
              for that lot.
            </p>
            <p className="mb-4">
              What the regulation does require is that every entity in the supply chain that
              handles a food on the Food Traceability List (FTL) must record the TLC at each
              Critical Tracking Event (CTE) and must be able to produce those records within 24
              hours of an FDA request.
            </p>

            <div
              style={{
                background: T.surface,
                border: `1px solid ${T.border}`,
                borderRadius: T.cardRadius,
                padding: '20px 24px',
              }}
            >
              <div className="flex items-start gap-3">
                <Hash className="w-5 h-5 text-emerald-500 mt-1 shrink-0" />
                <div>
                  <p style={{ color: T.heading, fontWeight: 600, marginBottom: '6px' }}>
                    The key principle
                  </p>
                  <p style={{ color: T.textMuted, fontSize: '14px', lineHeight: 1.6 }}>
                    A TLC is not just a label on a box. It is the join key that connects every CTE
                    record for a specific lot of food across every entity that handled it. If you
                    think of traceability as a database query, the TLC is the primary key. Get it
                    wrong and your records become un-queryable.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Section: GTIN + Lot Code ─────────────────────────── */}
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
              GTIN + Lot Code: The Standard Structure
            </h2>
            <p className="mb-4">
              While the regulation does not mandate GTINs, the industry standard for TLCs at the
              case and consumer level is the combination of a GTIN (Global Trade Item Number) and a
              lot code. This pairing is the most interoperable format because both GTINs and lot
              codes are already used in most supply chain systems.
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
              <p
                style={{
                  color: T.textMuted,
                  fontSize: '12px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: '12px',
                }}
              >
                GTIN + Lot Code Structure
              </p>
              <div style={{ fontFamily: T.fontMono, fontSize: '14px', color: T.accent, marginBottom: '12px' }}>
                TLC = GTIN (14 digits) + Lot Code (variable)
              </div>
              <div className="space-y-2" style={{ fontSize: '14px', color: T.text }}>
                <p>
                  <strong style={{ color: T.heading }}>GTIN (14 digits):</strong> identifies the
                  product. A 14-digit number that includes the GS1 Company Prefix, the item
                  reference, and a check digit. Example: <code style={{ color: T.accent, fontFamily: T.fontMono }}>00810012345678</code>
                </p>
                <p>
                  <strong style={{ color: T.heading }}>Lot code (variable length):</strong> identifies
                  the specific production batch of that product. Assigned by the manufacturer or
                  packer. Example: <code style={{ color: T.accent, fontFamily: T.fontMono }}>LOT-20260115-A</code>
                </p>
                <p>
                  <strong style={{ color: T.heading }}>Combined TLC:</strong> the GTIN + lot code
                  together form the TLC. Example: <code style={{ color: T.accent, fontFamily: T.fontMono }}>00810012345678:LOT-20260115-A</code>
                </p>
              </div>
            </div>

            <p className="mb-4">
              The GTIN component is critical for inter-company traceability because it provides a
              globally unique product identifier. When Company A ships product to Company B using a
              GTIN + lot code as the TLC, Company B can record the same TLC without ambiguity. Two
              different products will never share the same GTIN, so the TLC is globally unique.
            </p>
            <p>
              For foods at the farm level that are not yet in consumer packaging, GTINs may not be
              available. In those cases, the grower assigns a lot code using their own format. The
              key requirement is uniqueness within the grower&apos;s operation and consistency across
              the CTE records for that lot.
            </p>
          </section>

          {/* ── Section: TLC Source Reference ────────────────────── */}
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
              TLC Source Reference: The Chain of Custody Link
            </h2>
            <p className="mb-4">
              The TLC source reference is arguably the most important and most misunderstood concept
              in FSMA 204 traceability. It is the mechanism that links a downstream TLC to its
              upstream origin.
            </p>
            <p className="mb-4">
              Here is when a TLC source reference is required: any time a new TLC is assigned to a
              food that already had a TLC, the entity assigning the new TLC must record a TLC source
              reference that identifies the original TLC(s). This happens primarily at two CTEs:
            </p>

            <ul className="mb-6 space-y-3 pl-6" style={{ listStyleType: 'disc' }}>
              <li>
                <strong style={{ color: T.heading }}>Initial packing</strong>: if the packer
                assigns a new case-level TLC (GTIN + lot code), they must record the harvest TLC as
                the source reference. This links the case back to the field.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Transformation</strong>: when a processor
                creates a new product from one or more input lots, the new output TLC must include
                source references for every input TLC. If a salad mix draws from 8 different
                lettuce lots, all 8 TLCs must be recorded as source references.
              </li>
            </ul>

            <div
              style={{
                background: T.warningBg,
                border: `1px solid ${T.warningBorder}`,
                borderRadius: T.cardRadius,
                padding: '20px 24px',
              }}
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-500 mt-1 shrink-0" />
                <div>
                  <p style={{ color: T.heading, fontWeight: 600, marginBottom: '6px' }}>
                    Why this matters for investigations
                  </p>
                  <p style={{ color: T.text, fontSize: '14px', lineHeight: 1.6 }}>
                    During an outbreak investigation, the FDA traces backwards from the point of
                    illness to the source of contamination. The TLC source reference is how they
                    follow that chain. If Company C&apos;s finished product TLC has no source reference
                    to Company B&apos;s input lot, which has no source reference to Company A&apos;s
                    harvest lot, the chain is broken and the investigation stalls. In practice, the
                    FDA will then request records from every possible supplier &mdash; dramatically
                    expanding the scope and cost of the investigation for everyone involved.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Section: TLC Assignment by CTE ──────────────────── */}
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
              TLC Assignment Rules by CTE Type
            </h2>
            <p className="mb-6" style={{ color: T.textMuted }}>
              Who assigns the TLC, when, and what format is expected at each Critical Tracking Event.
            </p>

            <div className="space-y-5">
              {TLC_BY_CTE.map((item) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.cte}
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
                        {item.cte}
                      </h3>
                    </div>
                    <div className="grid gap-2" style={{ fontSize: '14px' }}>
                      <p>
                        <strong style={{ color: T.heading }}>Who assigns:</strong>{' '}
                        <span style={{ color: T.textMuted }}>{item.who}</span>
                      </p>
                      <p>
                        <strong style={{ color: T.heading }}>When:</strong>{' '}
                        <span style={{ color: T.textMuted }}>{item.when}</span>
                      </p>
                      <p style={{ color: T.text, lineHeight: 1.6 }}>{item.rule}</p>
                      <p>
                        <strong style={{ color: T.heading }}>Format:</strong>{' '}
                        <span style={{ color: T.textMuted }}>{item.format}</span>
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ── Section: Supply Chain Flow ───────────────────────── */}
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
              How TLCs Flow Through the Supply Chain
            </h2>
            <p className="mb-6">
              Understanding TLC flow is easier with a concrete example. Here is a simplified chain
              for romaine lettuce moving from a California farm to a grocery store salad kit.
            </p>

            <div className="space-y-0">
              {[
                {
                  step: 1,
                  label: 'Harvesting',
                  tlc: 'FARM-20260115-F3',
                  detail: 'Grower harvests romaine from Field 3. Assigns TLC "FARM-20260115-F3". This is the origin TLC.',
                  isNew: true,
                },
                {
                  step: 2,
                  label: 'Cooling',
                  tlc: 'FARM-20260115-F3',
                  detail: 'Product cooled on-farm. Same TLC carries forward. Cooling CTE recorded with the harvest TLC.',
                  isNew: false,
                },
                {
                  step: 3,
                  label: 'Initial Packing',
                  tlc: '00810012345678:LOT-A120',
                  detail: 'Packhouse creates case-level packaging. Assigns new TLC using GTIN + lot code. TLC source reference: "FARM-20260115-F3".',
                  isNew: true,
                },
                {
                  step: 4,
                  label: 'Shipping (Packhouse to Processor)',
                  tlc: '00810012345678:LOT-A120',
                  detail: 'Packhouse ships cases to a salad kit processor. TLC travels with the shipment on the bill of lading.',
                  isNew: false,
                },
                {
                  step: 5,
                  label: 'Receiving (Processor)',
                  tlc: '00810012345678:LOT-A120',
                  detail: 'Processor receives and records the TLC from the shipping documentation. Must match the shipper\'s TLC exactly.',
                  isNew: false,
                },
                {
                  step: 6,
                  label: 'Transformation',
                  tlc: '00810098765432:SK-20260116-PM',
                  detail: 'Processor combines this romaine lot with 4 other ingredient lots to produce a salad kit. Assigns new TLC. Source references: the TLCs of all 5 input lots.',
                  isNew: true,
                },
                {
                  step: 7,
                  label: 'Shipping (Processor to Retailer)',
                  tlc: '00810098765432:SK-20260116-PM',
                  detail: 'Finished salad kits shipped to retailer distribution center. TLC recorded on shipping documentation.',
                  isNew: false,
                },
                {
                  step: 8,
                  label: 'Receiving (Retailer)',
                  tlc: '00810098765432:SK-20260116-PM',
                  detail: 'Retailer DC receives and records the finished product TLC. This is the last CTE in the chain.',
                  isNew: false,
                },
              ].map((item, i) => (
                <div key={item.step} className="flex gap-4">
                  {/* Timeline line */}
                  <div className="flex flex-col items-center">
                    <div
                      style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        background: item.isNew ? T.accentBg : T.surface,
                        border: `2px solid ${item.isNew ? T.accent : T.border}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '13px',
                        fontWeight: 700,
                        color: item.isNew ? T.accent : T.textMuted,
                        flexShrink: 0,
                      }}
                    >
                      {item.step}
                    </div>
                    {i < 7 && (
                      <div
                        style={{
                          width: '2px',
                          flex: 1,
                          background: T.border,
                          minHeight: '20px',
                        }}
                      />
                    )}
                  </div>

                  {/* Content */}
                  <div style={{ paddingBottom: '20px' }}>
                    <div className="flex items-center gap-2 mb-1">
                      <p style={{ color: T.heading, fontWeight: 600, fontSize: '15px' }}>
                        {item.label}
                      </p>
                      {item.isNew && (
                        <span
                          style={{
                            background: T.accentBg,
                            color: T.accent,
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: '3px',
                            textTransform: 'uppercase',
                          }}
                        >
                          New TLC
                        </span>
                      )}
                    </div>
                    <p style={{ color: T.textMuted, fontSize: '13px', fontFamily: T.fontMono, marginBottom: '4px' }}>
                      TLC: {item.tlc}
                    </p>
                    <p style={{ color: T.text, fontSize: '14px', lineHeight: 1.55 }}>{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-4">
              Notice that new TLCs are only assigned at three points: harvesting (origin), initial
              packing (case-level), and transformation (new product). At every other CTE, the
              existing TLC is carried forward unchanged. This is by design: fewer TLC transitions
              means a simpler chain to trace.
            </p>
          </section>

          {/* ── Section: Common Mistakes ─────────────────────────── */}
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
              Common Mistakes in TLC Implementation
            </h2>
            <p className="mb-6">
              After reviewing hundreds of traceability datasets, these are the TLC implementation
              errors we see most frequently. Each one creates a compliance gap that will surface
              during an FDA records request.
            </p>

            <div className="space-y-4">
              {COMMON_MISTAKES.map((mistake) => (
                <div
                  key={mistake.title}
                  style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: T.cardRadius,
                    padding: '16px 20px',
                  }}
                >
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-amber-500 mt-1 shrink-0" />
                    <div>
                      <p style={{ color: T.heading, fontWeight: 600, marginBottom: '4px', fontSize: '15px' }}>
                        {mistake.title}
                      </p>
                      <p style={{ color: T.textMuted, fontSize: '14px', lineHeight: 1.6 }}>
                        {mistake.description}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Section: JSON Example ────────────────────────────── */}
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
              Valid TLC Structure: JSON Example
            </h2>
            <p className="mb-4">
              For developers building traceability systems, here is a reference JSON structure
              showing a valid TLC as it would appear in CTE records across the supply chain. This
              example covers a transformation event with multiple input TLCs and a single output
              TLC.
            </p>

            <div
              style={{
                background: '#0d1117',
                border: `1px solid ${T.border}`,
                borderRadius: T.cardRadius,
                padding: '24px',
                overflowX: 'auto',
              }}
            >
              <pre
                style={{
                  fontFamily: T.fontMono,
                  fontSize: '13px',
                  lineHeight: 1.65,
                  color: '#c9d1d9',
                  margin: 0,
                }}
              >
{`{
  "cte_type": "transformation",
  "event_id": "evt_transform_20260116_001",
  "timestamp": "2026-01-16T14:30:00Z",
  "location": {
    "name": "FreshCo Processing Plant #2",
    "fda_registration": "18374926",
    "address": "456 Industrial Pkwy, Salinas, CA 93901"
  },
  "input_lots": [
    {
      "tlc": "00810012345678:LOT-A120",
      "commodity": "Romaine Lettuce",
      "quantity": 500,
      "unit": "lb",
      "immediate_previous_source": "Valley Greens Packhouse",
      "tlc_source_reference": "FARM-20260115-F3"
    },
    {
      "tlc": "00810012345999:LOT-B045",
      "commodity": "Baby Spinach",
      "quantity": 200,
      "unit": "lb",
      "immediate_previous_source": "Coastal Farms Pack",
      "tlc_source_reference": "CF-20260114-S1"
    },
    {
      "tlc": "00810012346100:LOT-C012",
      "commodity": "Shredded Carrots",
      "quantity": 150,
      "unit": "lb",
      "immediate_previous_source": "Root Veggie Co",
      "tlc_source_reference": "RV-20260113-CR7"
    }
  ],
  "output_lot": {
    "tlc": "00810098765432:SK-20260116-PM",
    "product_description": "Caesar Salad Kit, 12oz",
    "gtin": "00810098765432",
    "lot_code": "SK-20260116-PM",
    "quantity": 2400,
    "unit": "each",
    "tlc_source_references": [
      "00810012345678:LOT-A120",
      "00810012345999:LOT-B045",
      "00810012346100:LOT-C012"
    ]
  }
}`}
              </pre>
            </div>

            <div className="mt-4 space-y-2" style={{ fontSize: '14px' }}>
              <p>Key observations from this structure:</p>
              <ul className="space-y-2 pl-6" style={{ listStyleType: 'disc', color: T.text }}>
                <li>
                  The <code style={{ color: T.accent, fontFamily: T.fontMono }}>output_lot.tlc_source_references</code> array
                  lists every input TLC, creating the many-to-one linkage the regulation requires.
                </li>
                <li>
                  Each input lot includes its own <code style={{ color: T.accent, fontFamily: T.fontMono }}>tlc_source_reference</code>,
                  which traces further upstream (back to the harvest or previous transformation).
                </li>
                <li>
                  The <code style={{ color: T.accent, fontFamily: T.fontMono }}>immediate_previous_source</code> field
                  identifies the business entity that shipped the input lot, enabling the FDA to
                  request records from that entity if needed.
                </li>
                <li>
                  GTINs are 14-digit, zero-padded. Lot codes are free-form strings assigned by the
                  responsible entity. The combined TLC uses a colon separator, though this is a
                  convention rather than a regulatory requirement.
                </li>
              </ul>
            </div>
          </section>

          {/* ── Section: Validation ──────────────────────────────── */}
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
              How RegEngine Validates TLCs
            </h2>
            <p className="mb-4">
              RegEngine runs TLC validation at ingest time, before records are stored, catching the
              common mistakes described above at data entry rather than during an FDA investigation.
              The validation includes:
            </p>

            <ul className="mb-6 space-y-3 pl-6" style={{ listStyleType: 'disc' }}>
              <li>
                <strong style={{ color: T.heading }}>Format validation</strong>: checks that TLCs
                conform to the configured format (GTIN + lot code, freeform, or custom regex). Flags
                inconsistent formats within the same supply chain.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Uniqueness checks</strong>: ensures a TLC is
                not reused across different lots or different products. Catches duplicate TLC
                assignments before they create traceability ambiguity.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Source reference linkage</strong>: when a CTE
                record includes a TLC source reference, validates that the referenced TLC exists in
                the system and traces to a valid upstream CTE. Orphaned source references are flagged
                immediately.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Cross-entity matching</strong>: when shipping
                and receiving records reference the same TLC, validates that the TLCs match exactly.
                Character-level mismatches, whitespace differences, and format inconsistencies are
                caught automatically.
              </li>
              <li>
                <strong style={{ color: T.heading }}>Transformation completeness</strong>: for
                transformation CTEs, validates that all input TLCs are captured and that the output
                TLC source reference list is exhaustive. Partial input recording is flagged as a
                compliance gap.
              </li>
            </ul>

            <p>
              The result is that by the time an FDA records request arrives, every TLC in the
              system has already been validated. The response is a query, not a reconciliation
              exercise. For implementation details, see the{' '}
              <Link href="/developers" style={{ color: T.accent, textDecoration: 'underline' }}>
                developer documentation
              </Link>.
            </p>
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
              Key Takeaways
            </h2>

            <div
              style={{
                background: T.surface,
                border: `1px solid ${T.border}`,
                borderRadius: T.cardRadius,
                padding: '24px',
              }}
            >
              <ol className="space-y-4 pl-6" style={{ listStyleType: 'decimal' }}>
                <li>
                  <strong style={{ color: T.heading }}>TLCs are the primary key of FSMA 204 traceability.</strong>{' '}
                  Every CTE record, every source reference, and every FDA query operates on TLCs.
                  Get them right and compliance follows.
                </li>
                <li>
                  <strong style={{ color: T.heading }}>New TLCs are assigned only at harvesting, initial packing, and transformation.</strong>{' '}
                  At all other CTEs, the existing TLC carries forward unchanged.
                </li>
                <li>
                  <strong style={{ color: T.heading }}>TLC source references are mandatory when a new TLC is assigned.</strong>{' '}
                  They create the upstream linkage that makes backward tracing possible.
                </li>
                <li>
                  <strong style={{ color: T.heading }}>GTIN + lot code is the industry standard format</strong>{' '}
                  for case-level and consumer-level products. Free-form lot codes are acceptable at
                  the farm level.
                </li>
                <li>
                  <strong style={{ color: T.heading }}>Validate at entry, not at request time.</strong>{' '}
                  TLC format, uniqueness, and source reference integrity should be checked when data
                  is recorded, not when the FDA asks for it.
                </li>
              </ol>
            </div>
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
              See TLC validation in action
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
              Walk through the full RegEngine workflow: ingest CTE data with TLCs, validate against
              FSMA 204, and trace lot codes across the supply chain.
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
