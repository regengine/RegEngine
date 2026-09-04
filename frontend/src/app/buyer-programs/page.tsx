import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, AlertTriangle, FileCheck2 } from "lucide-react";

export const metadata: Metadata = {
  title: "Buyer traceability programs | RegEngine",
  description:
    "Some buyers have published their own traceability programs. Those programs are the buyer's. They are not federal enforcement and they are not a RegEngine badge. We help you structure CTE/KDE records and export a sortable package.",
  openGraph: {
    title: "Buyer traceability programs | RegEngine",
    description:
      "Buyer programs are not the FDA clock. We help you structure CTE/KDE records and export a sortable package. You confirm format, scope, and dates with your buyer.",
    url: "https://regengine.co/buyer-programs",
    type: "website",
  },
};

const card = "rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm";

export default function BuyerProgramsPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="relative z-[2] max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10 sm:pb-14">
        <span className="block text-[11px] font-mono font-medium text-[var(--re-text-disabled)] tracking-widest uppercase mb-4">
          Buyer Traceability Programs
        </span>
        <h1 className="font-display text-4xl font-bold text-[var(--re-text-primary)] mb-4 leading-tight">
          Buyer programs are not the FDA clock.
        </h1>
        <p className="text-lg text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
          Some buyers have published their own traceability programs. Those programs are the buyer's. They are not federal enforcement and they are not a RegEngine badge. We help you structure CTE/KDE records and export a sortable package. You confirm format, scope, and dates with your buyer.
        </p>

        <div className={`${card} p-5 mt-6`}>
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-[var(--re-warning)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">FDA date</p>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                The FDA Food Traceability Rule compliance date is <strong className="text-[var(--re-text-primary)]">July 20, 2028</strong>. We will not imply that clock is now.
              </p>
            </div>
          </div>
        </div>

        <div className={`${card} p-5 mt-4`}>
          <div className="flex items-start gap-3">
            <FileCheck2 className="h-5 w-5 text-[var(--re-info)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">FTL vs covered person</p>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                The Food Traceability List is the list of foods. Who must keep Subpart S records is a separate question. Being on the list is not the same as being a covered person. We do not decide either one for you.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/contact"
            className="inline-flex min-h-11 items-center justify-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] text-[var(--re-surface-base)] px-5 py-3 text-[13px] font-semibold no-underline transition-colors hover:bg-[var(--re-success)]"
          >
            Book a 30-min call
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link
            href="/verify"
            className="inline-flex min-h-11 items-center justify-center gap-2 border border-[var(--re-border-strong)] bg-[var(--re-surface-elevated)] text-[var(--re-text-primary)] px-5 py-3 text-[13px] font-semibold no-underline transition-colors hover:bg-[var(--re-surface-card)]"
          >
            Verify a sample export
          </Link>
        </div>
      </section>

      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
          <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-6">
            Named buyer programs (first-party facts only)
          </h2>

          <div className="space-y-6">
            <div className={`${card} p-6`}>
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-3">
                Walmart Food Traceability / ASN
              </h3>
              <p className="text-sm text-[var(--re-text-muted)] mb-3 leading-relaxed">
                Source: <a href="https://enablement.walmart.com" target="_blank" rel="noopener noreferrer" className="text-[var(--re-brand)] hover:opacity-80">enablement.walmart.com</a>
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)] leading-relaxed">
                <li>• ASN containing KDEs</li>
                <li>• SSCC-18 on food pallets</li>
                <li>• GS1-128 on food cases</li>
                <li>• As of August 1, 2025 Walmart and Sam's Club require all food and beverage ASN+packaging</li>
                <li>• FTL by that date; other products ASAP</li>
              </ul>
              <p className="text-xs text-[var(--re-text-disabled)] mt-4 leading-relaxed">
                We do not make you Walmart-ready, transmit ASN on Retail Link, certify labels, or assess chargebacks. EDI 856 / ASN mapping is scoped work.
              </p>
            </div>

            <div className={`${card} p-6`}>
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-3">
                Albertsons Companies
              </h3>
              <p className="text-sm text-[var(--re-text-muted)] mb-3 leading-relaxed">
                Source: Letter dated 17 September 2025 (PDF at suppliers.safeway.com)
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)] leading-relaxed">
                <li>• All food and non-alcoholic beverages</li>
                <li>• Albertsons deadline January 1, 2027</li>
                <li>• Federal date remains July 20, 2028</li>
              </ul>
            </div>

            <div className={`${card} p-6 border-[var(--re-warning)]`}>
              <div className="flex items-start gap-3 mb-3">
                <AlertTriangle className="h-5 w-5 text-[var(--re-warning)] flex-shrink-0 mt-0.5" />
                <h3 className="text-lg font-semibold text-[var(--re-text-primary)]">
                  Kroger Food Traceability Policy
                </h3>
              </div>
              <p className="text-sm text-[var(--re-text-muted)] mb-3 leading-relaxed">
                Source: December 2023 first-party letter
              </p>
              <div className="bg-[var(--re-warning)]/10 border border-[var(--re-warning)]/20 rounded p-4 mb-3">
                <p className="text-sm text-[var(--re-text-primary)] leading-relaxed font-medium">
                  A December 2023 first-party Kroger letter stated a June 30, 2025 supplier transition. We have not found a later first-party update. The letter's FDA date of January 20, 2026 is stale. The federal compliance date is July 20, 2028. This is not a claim that anyone is Kroger-ready.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
        <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
          <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-6">
            What we export
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div className={`${card} p-5`}>
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 className="h-5 w-5 text-[var(--re-success)]" />
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">RegEngine provides</h3>
              </div>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)] leading-relaxed">
                <li>• CTE/KDE workspace</li>
                <li>• Advisory coverage/completeness checklist</li>
                <li>• Append-only commit</li>
                <li>• FDA-oriented sortable spreadsheet</li>
                <li>• EPCIS/CSV where enabled</li>
                <li>• Hash manifest re-checkable at /verify</li>
              </ul>
            </div>

            <div className={`${card} p-5`}>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="h-5 w-5 text-[var(--re-warning)]" />
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">Operator still owns</h3>
              </div>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)] leading-relaxed">
                <li>• Covered-person status</li>
                <li>• FTL membership</li>
                <li>• Buyer acceptance</li>
                <li>• Physical labels/SSCC-18/GS1-128</li>
                <li>• Answering FDA under §1.1455</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
          <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-4">
            Pricing
          </h2>
          <div className={`${card} p-6`}>
            <div className="flex items-baseline gap-3 mb-4">
              <span className="text-4xl font-bold text-[var(--re-text-primary)]">$425</span>
              <span className="text-sm text-[var(--re-text-muted)]">per month, billed annually</span>
            </div>
            <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
              No facility/CTE cap. No SLA. No retailer-specific benchmark. No quarterly compliance review. No audit. No readiness score. No FDA/buyer approval. No three-tier ladder or strikethrough list prices.
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
        <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
          <div className={`${card} p-6`}>
            <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-4">
              <strong className="text-[var(--re-text-primary)]">Founder-led.</strong> Book a call. No score.
            </p>
            <p className="text-sm text-[var(--re-text-disabled)]">
              Pasadena, CA
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6 text-center">
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              href="/contact"
              className="inline-flex items-center gap-1.5 text-sm text-[var(--re-brand)] hover:opacity-80 transition-opacity"
            >
              Book a 30-min call <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              href="/verify"
              className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors"
            >
              Verify a sample export <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-base)] py-8">
        <div className="max-w-[860px] mx-auto px-4 sm:px-6">
          <p className="text-sm text-[var(--re-text-muted)]">
            Pasadena, CA
          </p>
          <p className="mt-2 text-xs text-[var(--re-text-disabled)]">
            July 20, 2028 · §1.1455 we do not claim to meet · No seals, competitor table, revenue-at-risk calculator
          </p>
        </div>
      </footer>
    </div>
  );
}
