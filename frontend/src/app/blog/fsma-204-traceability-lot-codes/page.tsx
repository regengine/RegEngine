import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Clock, CheckCircle, Tag, Layers, AlertTriangle, ArrowRight } from "lucide-react";

export const metadata: Metadata = {
  title: "FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide | RegEngine Blog",
  description:
    "Learn how to assign, track, and maintain Traceability Lot Codes under FSMA 204. Covers TLC requirements, best practices, and common mistakes for food businesses.",
  openGraph: {
    title: "FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide",
    description: "Everything food businesses need to know about TLCs under the FDA Food Traceability Rule.",
    type: "article",
    publishedTime: "2026-03-01T00:00:00Z",
  },
};

const TLC_REQUIREMENTS = [
  {
    cte: "Harvesting",
    who: "Farms & growers",
    requirement: "Assign a TLC at harvest. The TLC must uniquely identify the lot — typically a combination of farm, field, date, and commodity.",
  },
  {
    cte: "Cooling",
    who: "Coolers & packhouses",
    requirement: "Maintain the TLC assigned at harvest. If lots are not commingled, the TLC carries through.",
  },
  {
    cte: "Initial Packing",
    who: "Packhouses",
    requirement: "If you create new consumer-facing lots, assign a new TLC. Record the link between the original harvest TLC and the new pack TLC.",
  },
  {
    cte: "Shipping",
    who: "Any shipper",
    requirement: "Include the TLC on shipping documents (BOL, ASN). The receiver must be able to trace back to your TLC.",
  },
  {
    cte: "Receiving",
    who: "Any receiver",
    requirement: "Record the TLC from the shipper. If you assign your own internal lot code, maintain the mapping to the original TLC.",
  },
  {
    cte: "Transformation",
    who: "Manufacturers & processors",
    requirement: "When inputs are combined into a new product, assign a new TLC. Record all input TLCs that went into the output.",
  },
];

const BEST_PRACTICES = [
  {
    title: "Use a consistent format",
    description: "Standardize your TLC format across facilities. A common pattern: FACILITY-DATE-SEQ (e.g., SAL-20260301-001).",
  },
  {
    title: "Include the date",
    description: "Embedding the production or harvest date in the TLC makes sorting and filtering much faster during a recall.",
  },
  {
    title: "Avoid reuse",
    description: "Never reuse a TLC, even across years. If you harvest romaine on March 1 every year, each year's lot must have a distinct code.",
  },
  {
    title: "Make it scannable",
    description: "Encode your TLC in a barcode (GS1-128 or DataMatrix) so it can be captured at receiving without manual entry.",
  },
  {
    title: "Document your scheme",
    description: "Write down your TLC assignment logic. The FDA may ask how you generate codes during an inspection.",
  },
];

export default function TLCGuidePage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <article className="max-w-[900px] mx-auto px-6 py-16 md:py-24">
        <Link
          href="/blog"
          className="inline-flex items-center gap-1 text-sm mb-8"
          style={{ color: "var(--re-brand)" }}
        >
          <ArrowLeft className="w-4 h-4" /> Back to Blog
        </Link>

        {/* Header */}
        <div className="mb-12">
          <div className="flex items-center gap-3 text-sm mb-4" style={{ color: "var(--re-text-muted)" }}>
            <span>March 1, 2026</span>
            <span>&middot;</span>
            <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> 8 min read</span>
          </div>
          <h1
            className="text-3xl md:text-4xl font-bold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide
          </h1>
          <p className="text-lg" style={{ color: "var(--re-text-secondary)" }}>
            Traceability Lot Codes are the connective tissue of FSMA 204. Every
            Critical Tracking Event requires one. Here&apos;s how to get them right.
          </p>
        </div>

        {/* What is a TLC? */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            What Is a Traceability Lot Code?
          </h2>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            A Traceability Lot Code (TLC) is a descriptor — often a number, code,
            or combination — used to identify a traceability lot. Under 21 CFR 1.1310,
            every food on the Food Traceability List must carry a TLC that connects it
            to the Critical Tracking Events (CTEs) in its supply chain.
          </p>
          <div
            className="flex items-start gap-3 p-4 rounded-lg"
            style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
          >
            <Tag className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "var(--re-brand)" }} />
            <p style={{ color: "var(--re-text-secondary)" }}>
              <strong>Think of a TLC as a lot&apos;s passport.</strong> It travels with the
              food from farm to fork. When the FDA needs to trace a contaminated product,
              the TLC is how they follow the trail.
            </p>
          </div>
        </section>

        {/* TLC Requirements by CTE */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            TLC Requirements by Critical Tracking Event
          </h2>
          <div className="space-y-4">
            {TLC_REQUIREMENTS.map((item) => (
              <div
                key={item.cte}
                className="p-4 rounded-lg"
                style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Layers className="w-4 h-4" style={{ color: "var(--re-brand)" }} />
                  <span className="font-semibold" style={{ color: "var(--re-text-primary)" }}>
                    {item.cte}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: "var(--re-surface-border)", color: "var(--re-text-muted)" }}>
                    {item.who}
                  </span>
                </div>
                <p className="text-sm" style={{ color: "var(--re-text-secondary)" }}>
                  {item.requirement}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* The Transformation Problem */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            The Transformation Challenge
          </h2>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            Transformation CTEs are where TLC tracking gets complex. When you combine
            romaine from three different harvest lots into a single salad kit, you must:
          </p>
          <ol className="list-decimal list-inside space-y-2 mb-4" style={{ color: "var(--re-text-secondary)" }}>
            <li>Assign a <strong>new TLC</strong> to the output product</li>
            <li>Record <strong>all input TLCs</strong> that went into it</li>
            <li>Maintain this mapping for <strong>at least 2 years</strong></li>
          </ol>
          <div
            className="flex items-start gap-3 p-4 rounded-lg"
            style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
          >
            <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "#f59e0b" }} />
            <p style={{ color: "var(--re-text-secondary)" }}>
              This input-to-output TLC mapping is what the FDA uses to trace contamination
              backwards through your supply chain. Missing or incomplete mappings are the
              #1 compliance gap we see in food manufacturing operations.
            </p>
          </div>
        </section>

        {/* Best Practices */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            TLC Best Practices
          </h2>
          <div className="space-y-4">
            {BEST_PRACTICES.map((item) => (
              <div key={item.title} className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "var(--re-brand)" }} />
                <div>
                  <p className="font-medium" style={{ color: "var(--re-text-primary)" }}>
                    {item.title}
                  </p>
                  <p className="text-sm" style={{ color: "var(--re-text-secondary)" }}>
                    {item.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <div
          className="p-8 rounded-xl text-center"
          style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
        >
          <Tag className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--re-brand)" }} />
          <h3
            className="text-xl font-semibold mb-2"
            style={{ color: "var(--re-text-primary)" }}
          >
            Validate Your TLCs
          </h3>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            Use RegEngine&apos;s free TLC Validator to check your lot codes against
            FSMA 204 requirements.
          </p>
          <Link
            href="/tools/tlc-validator"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-white"
            style={{ backgroundColor: "var(--re-brand)" }}
          >
            Open TLC Validator <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </article>
    </div>
  );
}
