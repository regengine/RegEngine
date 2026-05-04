import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, X, TrendingUp, Lock } from 'lucide-react';

export const metadata: Metadata = {
  title: 'RegEngine vs Spreadsheets: Why Food Companies Outgrow Excel for Traceability',
  description: 'Why spreadsheets fail for FSMA 204 compliance. Learn how RegEngine solves the audit trail, scale, and 24-hour response problems.',
  openGraph: {
    title: 'RegEngine vs Spreadsheets: Why Food Companies Outgrow Excel for Traceability',
    description: 'Why spreadsheets fail for FSMA 204 compliance. Learn how RegEngine solves the audit trail, scale, and 24-hour response problems.',
    type: 'article',
  },
};

export default function RegEngineVsSpreadsheets() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* Hero */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-8 sm:pb-12">
        <div className="mb-8">
          <Link
            href="/blog"
            className="inline-flex items-center gap-2 text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors duration-200 text-sm font-medium mb-6"
          >
            ← Back to Blog
          </Link>
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            Tools & Solutions
          </p>
          <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight mb-6">
            RegEngine vs Spreadsheets: Why Food Companies Outgrow Excel for Traceability
          </h1>
          <p className="text-[1.1rem] text-[var(--re-text-secondary)] leading-relaxed mb-4">
            How spreadsheets break at scale and why FSMA 204 requires a better approach.
          </p>
          <div className="flex gap-6 text-sm text-[var(--re-text-muted)] pt-4 border-t border-[var(--re-surface-border)]">
            <span>April 2026</span>
            <span>8 min read</span>
          </div>
        </div>
      </section>

      {/* Content */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <article className="prose max-w-none prose-headings:text-[var(--re-text-primary)] prose-p:text-[var(--re-text-secondary)] prose-strong:text-[var(--re-text-primary)] prose-li:text-[var(--re-text-secondary)] prose-a:text-[var(--re-brand)]">
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              When you're a small food company, spreadsheets work fine. You know your suppliers by name. Your product line is small. Your warehouse staff can track shipments by memory. Traceability feels manageable.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              But as you grow, spreadsheets become a liability. You add products, suppliers, and distribution channels. Data entry errors multiply. You lose the audit trail of who changed what. Your 24-hour FDA response time becomes impossible to meet. And when an inspector asks to see your traceability records, you realize you're not even sure which versions of your spreadsheets are the real ones.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              This guide walks through the specific ways spreadsheets fail for FSMA 204 compliance and how RegEngine solves these problems.
            </p>
          </div>

          {/* Problem 1 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6 mt-12">
              Problem 1: No Audit Trail
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              When you use a spreadsheet for traceability data, you face an immediate compliance problem: you have no way to prove who entered the data, when they entered it, or what they changed.
            </p>
            <div className="space-y-5 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <X className="w-5 h-5 text-re-danger" />
                  Spreadsheet Problems
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Multiple copies of the same file floating around email and shared drives</li>
                  <li>• No history of who edited what or when</li>
                  <li>• Easy to overwrite or accidentally delete data</li>
                  <li>• Can't track who accessed the file or when</li>
                  <li>• If someone makes a mistake, you can't see when or how it happened</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                  RegEngine Platform
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Centralized database with single source of truth</li>
                  <li>• Complete audit trail: who entered data, when, and all changes</li>
                  <li>• Data integrity protection—changes are logged and cannot be undone silently</li>
                  <li>• Access controls: see who accessed which data and when</li>
                  <li>• FDA-ready compliance reports with full traceability of the data itself</li>
                </ul>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              When an FDA inspector asks, "Can you prove this data was entered correctly and hasn't been altered?" a spreadsheet fails the test. RegEngine passes it.
            </p>
          </div>

          {/* Problem 2 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Problem 2: Manual Data Entry = Human Error at Scale
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              Spreadsheets require manual data entry. Someone in the warehouse has to fill in shipping information. Someone in production has to log transformations. Someone in receiving has to record what came in. Each of these steps is a point of failure.
            </p>
            <div className="space-y-5 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <X className="w-5 h-5 text-re-danger" />
                  Spreadsheet Problems
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• People forget to fill in fields or enter them incorrectly</li>
                  <li>• Date and time formats vary—is that 3/5 or 5/3?</li>
                  <li>• Typos in supplier or customer names break traceability links</li>
                  <li>• No validation—data that doesn't make sense (e.g., receiving before shipping) is accepted</li>
                  <li>• At 100+ transactions per day, error rates are significant</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                  RegEngine Platform
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Automate data capture from your ERP, WMS, and other systems</li>
                  <li>• Smart forms with required fields, dropdowns, and validation rules</li>
                  <li>• Standardized date/time formats and units of measure</li>
                  <li>• Real-time validation: if something doesn't make sense, the system flags it</li>
                  <li>• Built-in error checking reduces data entry mistakes by 90%+</li>
                </ul>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              When you rely on humans to enter traceability data into a spreadsheet, you're guaranteed to have gaps and errors. RegEngine reduces human error through automation and validation.
            </p>
          </div>

          {/* Problem 3 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Problem 3: Can't Meet the 24-Hour Response Requirement
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              The FDA's central requirement is clear: you have 24 hours to provide complete traceability records. With a spreadsheet, this is nearly impossible.
            </p>
            <div className="space-y-5 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <X className="w-5 h-5 text-re-danger" />
                  Spreadsheet Problems
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Finding the right data: which file version is current? Where's the 2022 data?</li>
                  <li>• Manually querying: searching through thousands of rows for matching products and dates</li>
                  <li>• Cross-referencing: matching suppliers to lot codes, then to customers (hours of work)</li>
                  <li>• Formatting: converting your data into the FDA's required format (EPCIS 2.0) by hand</li>
                  <li>• Review and validation: making sure the report is complete and accurate</li>
                  <li>• Total time: 8-16 hours on a good day. You miss the deadline.</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                  RegEngine Platform
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• One-click query: search by product name, date range, lot code, or customer</li>
                  <li>• Instant results: within seconds, see all matching transactions</li>
                  <li>• Auto-formatted: data is automatically formatted in FDA-required EPCIS 2.0 format</li>
                  <li>• Traceability links: immediate source and recipient are already linked in the system</li>
                  <li>• One-click export: generate a complete, audit-ready report in minutes</li>
                  <li>• Total time: 5-30 minutes from request to delivery. You exceed the requirement.</li>
                </ul>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              A spreadsheet makes the 24-hour response nearly impossible. RegEngine makes it easy and repeatable.
            </p>
          </div>

          {/* Problem 4 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Problem 4: You Don't Know What You Have
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              After a year of using spreadsheets, you face a critical problem: you're not sure if your data is complete or accurate. You have multiple versions of the same files. Some are on shared drives, some in email, some on laptops. You don't know which one is the truth.
            </p>
            <div className="space-y-5 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <X className="w-5 h-5 text-re-danger" />
                  Spreadsheet Problems
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Which version of the file is correct?</li>
                  <li>• Are there gaps in your data?</li>
                  <li>• Did you capture all CTEs and KDEs?</li>
                  <li>• Do your traceability lot codes actually link back to suppliers?</li>
                  <li>• How do you answer an auditor who asks, "Is this complete?"</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                  RegEngine Platform
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Single source of truth: one database, always up to date</li>
                  <li>• Data validation: automated checks ensure CTEs and KDEs are captured correctly</li>
                  <li>• Traceability validation: automated checks verify that source-recipient links are complete</li>
                  <li>• Compliance reports: see at a glance what you have, what's missing, and where</li>
                  <li>• Auditor-ready: generate comprehensive compliance reports on demand</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Problem 5 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Problem 5: Supplier Collaboration Breaks Down
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              With a spreadsheet, collecting traceability data from suppliers is painful. You email them a form. They fill it out manually. You copy and paste it into your spreadsheet. Errors happen. Data gets lost. Half your suppliers never get around to responding.
            </p>
            <div className="space-y-5 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <X className="w-5 h-5 text-re-danger" />
                  Spreadsheet Problems
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Manual emails back and forth</li>
                  <li>• Suppliers filling out templates incorrectly</li>
                  <li>• You manually entering supplier data into your spreadsheet</li>
                  <li>• No visibility into what's missing until you need it</li>
                  <li>• Supplier compliance is low—they don't see why it matters</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                  RegEngine Platform
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Supplier portal: suppliers log in and submit traceability data directly</li>
                  <li>• Simple templates: no expertise needed—suppliers fill in basic fields</li>
                  <li>• Automatic validation: the system checks data before it's submitted</li>
                  <li>• Real-time visibility: you see what you're missing and who hasn't responded</li>
                  <li>• Fewer support emails: suppliers get instant feedback on what's needed</li>
                </ul>
              </div>
            </div>
          </div>

          {/* TCO Comparison */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Total Cost of Ownership: Spreadsheets vs RegEngine
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              Spreadsheets are "free" up front, but the hidden costs add up fast:
            </p>
            <div className="space-y-6 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  Spreadsheet Total Cost of Ownership
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• Staff time to manage spreadsheets: $40K-80K/year</li>
                  <li>• Data entry errors and corrections: $20K-40K/year</li>
                  <li>• Supplier data collection and management: $30K-60K/year</li>
                  <li>• FDA response preparation and compliance work: $50K-100K/year (sporadic but high effort)</li>
                  <li>• Risk of non-compliance, enforcement action, or recall: $500K+ (potential)</li>
                  <li>• <strong>Total 2-year cost: $180K-360K+ (plus compliance risk)</strong></li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  RegEngine Total Cost of Ownership
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm">
                  <li>• RegEngine subscription: $15K-50K/year (depending on volume)</li>
                  <li>• Implementation and training: $10K-20K (one-time)</li>
                  <li>• Staff time reduction: -$30K-50K/year (automation handles data entry)</li>
                  <li>• FDA response preparation: 30 minutes instead of 8 hours (minimal cost)</li>
                  <li>• Compliance assurance: built-in, reduces risk to near-zero</li>
                  <li>• <strong>Total 2-year cost: $40K-120K (with compliance confidence)</strong></li>
                </ul>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              RegEngine typically pays for itself within the first year through labor savings and risk reduction.
            </p>
          </div>

          {/* When to Migrate */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              When Should You Move Away from Spreadsheets?
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              You're probably ready for RegEngine if you see any of these signs:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You have more than 50 SKUs or more than 10 suppliers</span>
              </li>
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Your team spends more than 5 hours per week managing traceability data</span>
              </li>
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You've had data entry errors that affected your supply chain</span>
              </li>
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You're not confident you could respond to an FDA records request within 24 hours</span>
              </li>
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You have concerns about data integrity, audit trails, or compliance gaps</span>
              </li>
              <li className="flex gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Your FSMA 204 deadline is less than 12 months away</span>
              </li>
            </ul>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Key Takeaways
            </h2>
            <ul className="space-y-3 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Spreadsheets fail at FSMA 204 compliance because they lack audit trails, scale poorly, and can't meet the 24-hour response requirement.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Manual data entry leads to errors at scale. Automated systems dramatically reduce errors and improve data quality.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Spreadsheets are "free" but have hidden costs: staff time, errors, supplier management, and compliance risk.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>RegEngine provides a dedicated traceability system that meets all FSMA 204 requirements and reduces labor costs.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>If you have more than 50 SKUs, 10+ suppliers, or less than 12 months to the deadline, you need a dedicated system.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <div className="p-8 sm:p-12 rounded-xl border border-[var(--re-brand)]/20 bg-gradient-to-br from-[var(--re-brand)]/5 to-cyan-600/5">
            <h3 className="font-serif text-xl font-bold text-[var(--re-text-primary)] mb-4">
              Ready to move beyond spreadsheets?
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-8">
              Get a free readiness assessment and see how RegEngine can replace your spreadsheet traceability system.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px] max-w-fit"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Get Your Readiness Score</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/tools/data-import"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                Import Your Data
              </Link>
            </div>
          </div>
        </article>
      </section>
    </div>
  );
}
