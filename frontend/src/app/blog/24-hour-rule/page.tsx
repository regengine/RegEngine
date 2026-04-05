import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Clock, AlertTriangle, CheckCircle, FileText, Shield } from "lucide-react";

export const metadata: Metadata = {
  title: "The FSMA 204 24-Hour Rule Explained | RegEngine Blog",
  description:
    "The FDA can request your traceability records within 24 hours of a recall or outbreak. Learn what records you need, how to organize them, and how to respond in time.",
  openGraph: {
    title: "The FSMA 204 24-Hour Rule Explained",
    description: "What the FDA's 24-hour records request means for your food business.",
    type: "article",
    publishedTime: "2026-03-15T00:00:00Z",
  },
};

const KEY_RECORDS = [
  "Traceability Lot Codes (TLCs) for every product on the Food Traceability List",
  "Critical Tracking Events (CTEs): shipping, receiving, transformation, and more",
  "Key Data Elements (KDEs): who, what, when, where for each CTE",
  "Reference documents: BOLs, purchase orders, ASNs",
  "Location identifiers: GLNs or descriptive names for every facility",
];

const COMMON_MISTAKES = [
  {
    mistake: "Storing records in paper binders or disconnected spreadsheets",
    fix: "Use a centralized digital system that can export records instantly",
  },
  {
    mistake: "Relying on one person to know where everything is",
    fix: "Document your record-keeping process so anyone on your team can respond",
  },
  {
    mistake: "Not testing your recall readiness",
    fix: "Run a mock recall drill quarterly — the FDA recommends this",
  },
  {
    mistake: "Waiting for an FDA request to organize records",
    fix: "Keep records sortable by TLC, date range, and product from day one",
  },
];

export default function TwentyFourHourRulePage() {
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
            <span>March 15, 2026</span>
            <span>&middot;</span>
            <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> 6 min read</span>
          </div>
          <h1
            className="text-3xl md:text-4xl font-bold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            The FSMA 204 24-Hour Rule: What It Really Means for Your Operation
          </h1>
          <p className="text-lg" style={{ color: "var(--re-text-secondary)" }}>
            When the FDA identifies a foodborne illness outbreak or contamination event,
            they can request your traceability records within <strong>24 hours</strong>.
            Here&apos;s what that means in practice.
          </p>
        </div>

        {/* Section: What is the 24-hour rule? */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            What is the 24-Hour Rule?
          </h2>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            Under 21 CFR 1.1455, the FDA can require any person who is subject to the
            food traceability requirements to provide, within 24 hours of a request,
            the information required to be maintained under the rule. This applies to
            all foods on the Food Traceability List (FTL).
          </p>
          <div
            className="flex items-start gap-3 p-4 rounded-lg mb-4"
            style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
          >
            <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "#f59e0b" }} />
            <p style={{ color: "var(--re-text-secondary)" }}>
              <strong>This is not optional.</strong> Failure to produce records within 24 hours
              can result in FDA enforcement actions, including warning letters, import alerts,
              and potential criminal referral for repeat violations.
            </p>
          </div>
          <p style={{ color: "var(--re-text-secondary)" }}>
            The clock starts when the FDA sends the request — not when you read it.
            Weekends and holidays are not excluded. This means your traceability system
            needs to be accessible and queryable at any time.
          </p>
        </section>

        {/* Section: What records does the FDA want? */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            What Records Does the FDA Want?
          </h2>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            The FDA will typically request records for a specific product, lot code,
            or time period. You need to provide:
          </p>
          <ul className="space-y-3">
            {KEY_RECORDS.map((record) => (
              <li key={record} className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "var(--re-brand)" }} />
                <span style={{ color: "var(--re-text-secondary)" }}>{record}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Section: Common mistakes */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            Common Mistakes That Slow Your Response
          </h2>
          <div className="space-y-4">
            {COMMON_MISTAKES.map((item) => (
              <div
                key={item.mistake}
                className="p-4 rounded-lg"
                style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
              >
                <p className="font-medium mb-1" style={{ color: "var(--re-text-primary)" }}>
                  <AlertTriangle className="w-4 h-4 inline mr-1" style={{ color: "#ef4444" }} />
                  {item.mistake}
                </p>
                <p className="text-sm" style={{ color: "var(--re-text-secondary)" }}>
                  <CheckCircle className="w-4 h-4 inline mr-1" style={{ color: "var(--re-brand)" }} />
                  {item.fix}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Section: How to prepare */}
        <section className="mb-12">
          <h2
            className="text-2xl font-semibold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            How to Prepare
          </h2>
          <div className="space-y-4" style={{ color: "var(--re-text-secondary)" }}>
            <p>
              <strong>1. Digitize your records.</strong> Paper-based systems cannot
              meet a 24-hour deadline at scale. You need a system that can query
              records by TLC, product, date range, and location.
            </p>
            <p>
              <strong>2. Run mock recalls.</strong> The FDA recommends periodic mock
              recall exercises. Use RegEngine&apos;s{" "}
              <Link href="/tools/drill-simulator" style={{ color: "var(--re-brand)" }}>
                Recall Drill Simulator
              </Link>{" "}
              to practice.
            </p>
            <p>
              <strong>3. Assign a response team.</strong> Designate who receives and
              responds to FDA requests. Include backup contacts for evenings and weekends.
            </p>
            <p>
              <strong>4. Pre-configure exports.</strong> Set up your system to produce
              sortable spreadsheets or electronic records that the FDA can review
              immediately. The FDA accepts CSV, Excel, and PDF formats.
            </p>
          </div>
        </section>

        {/* CTA */}
        <div
          className="p-8 rounded-xl text-center"
          style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
        >
          <Shield className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--re-brand)" }} />
          <h3
            className="text-xl font-semibold mb-2"
            style={{ color: "var(--re-text-primary)" }}
          >
            Test Your 24-Hour Readiness
          </h3>
          <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
            RegEngine&apos;s free tools help you assess your compliance readiness
            before the FDA comes knocking.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/tools/drill-simulator"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-white"
              style={{ backgroundColor: "var(--re-brand)" }}
            >
              <FileText className="w-4 h-4" /> Run a Mock Recall
            </Link>
            <Link
              href="/tools/readiness-assessment"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium"
              style={{ border: "1px solid var(--re-surface-border)", color: "var(--re-text-primary)" }}
            >
              Take Readiness Assessment
            </Link>
          </div>
        </div>
      </article>
    </div>
  );
}
