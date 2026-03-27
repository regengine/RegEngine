import Link from "next/link";
import { ArrowRight, Leaf, ShieldCheck, BookOpen, Thermometer, CheckCircle2, XCircle } from "lucide-react";
import { DataTransformDemo } from "@/components/marketing/DataTransformDemo";
import { SandboxUpload } from "@/components/marketing/SandboxUpload";

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const EVIDENCE = [
  { value: "48hr", label: "Average time to first compliant export" },
  { value: "100%", label: "of FSMA 204 CTEs covered" },
  { value: "24hr", label: "Recall response — fully automated" },
  { value: "EPCIS 2.0", label: "FDA-native format, zero conversion" },
];

const FREE_TOOLS = [
  {
    title: "FTL Coverage Checker",
    desc: "Are your products on the FDA Food Traceability List? Find out in seconds.",
    href: "/tools/ftl-checker",
    tag: null,
    icon: Leaf,
  },
  {
    title: "Retailer Readiness Assessment",
    desc: "Could you pass a Walmart supplier audit today? Scored automatically.",
    href: "/retailer-readiness",
    tag: "Popular",
    icon: ShieldCheck,
  },
  {
    title: "FSMA 204 Compliance Guide",
    desc: "Plain-English guide to the food traceability rule. No jargon.",
    href: "/fsma-204",
    tag: null,
    icon: BookOpen,
  },
  {
    title: "FDA Recall Drill",
    desc: "Simulate an FDA records request and test your 24-hour response.",
    href: "/tools/drill-simulator",
    tag: null,
    icon: Thermometer,
  },
];

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function RegEngineLanding() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

      {/* ── HERO ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-12 sm:pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">

          {/* Left — copy */}
          <div>
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-5">
              FSMA 204 Compliance
            </p>
            <h1 className="font-serif text-[clamp(1.75rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
              The FDA gives you 24&nbsp;hours.{" "}
              <em className="font-medium text-[var(--re-brand-dark)]">Your spreadsheets won&apos;t cut&nbsp;it.</em>
            </h1>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[480px]">
              When the FDA or Walmart demands your traceability records, you have 24&nbsp;hours to respond with a complete chain of custody. RegEngine gets you there in&nbsp;minutes.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px]"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Get Your Free Readiness Assessment</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/walkthrough"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                See How It Works
              </Link>
            </div>
          </div>

          {/* Right — Walmart audit scenario card */}
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden shadow-re-md">
            {/* Card header */}
            <div className="px-4 sm:px-5 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[var(--re-warning)] flex-shrink-0" />
              <span className="font-mono text-[0.65rem] sm:text-[0.72rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                INCOMING: SUPPLIER AUDIT REQUEST
              </span>
            </div>

            {/* Card body */}
            <div className="p-4 sm:p-5">
              <p className="font-serif text-[0.95rem] sm:text-[1.05rem] font-medium text-[var(--re-text-primary)] leading-snug mb-5">
                &ldquo;Provide complete chain of custody for{" "}
                <span className="text-[var(--re-brand-dark)]">Romaine Lettuce Lot&nbsp;R&#8209;2026&#8209;0312</span>{" "}
                from farm to distribution center. Due by end of business Friday.&rdquo;
              </p>

              <div className="border-t border-[var(--re-surface-border)] pt-4 mt-4">
                <p className="font-mono text-[0.65rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-3">
                  RegEngine Response — 3 minutes later
                </p>
                <div className="space-y-2.5">
                  {[
                    { label: "CTEs found", value: "12 of 12", badge: "Passed", badgeColor: "emerald" },
                    { label: "Coverage", value: "100%", badge: "Complete", badgeColor: "emerald" },
                    { label: "Format", value: "EPCIS 2.0 + PDF", badge: "Export Ready", badgeColor: "blue" },
                    { label: "Cryptographic verification", value: "SHA-256", badge: "Verified", badgeColor: "emerald" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-2">
                      <span className="text-[0.75rem] sm:text-[0.8rem] text-[var(--re-text-secondary)] shrink-0">{row.label}</span>
                      <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                        <span className="font-mono text-[0.75rem] sm:text-[0.8rem] font-medium text-[var(--re-brand-dark)] truncate">{row.value}</span>
                        <span className={`text-[0.55rem] sm:text-[0.6rem] font-semibold px-1.5 py-0.5 rounded-full border whitespace-nowrap ${
                          row.badgeColor === "blue"
                            ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        }`}>{row.badge}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Card footer */}
            <div className="px-4 sm:px-5 py-3 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-3">
              <span className="text-[0.8rem] text-[var(--re-text-muted)] hidden sm:inline">
                Export ready to send
              </span>
              <Link
                href="/retailer-readiness"
                className="group font-mono text-[0.72rem] font-semibold bg-[var(--re-brand)] text-white px-4 py-2.5 rounded-md transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[1px] hover:shadow-[0_4px_12px_rgba(16,185,129,0.25)] text-center min-h-[44px] flex items-center justify-center"
              >
                Check Your Readiness <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5 ml-1">→</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOUNDER TRUST STRIP ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pb-8">
        <div className="flex items-start gap-4 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 sm:p-6">
          <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-[var(--re-brand)]/10 border-2 border-[var(--re-brand)]/30 flex items-center justify-center flex-shrink-0">
            <span className="text-lg sm:text-xl font-serif font-bold text-[var(--re-brand)]">CS</span>
          </div>
          <div>
            <p className="text-[0.95rem] sm:text-[1.05rem] text-[var(--re-text-primary)] leading-relaxed">
              &ldquo;I&apos;m Chris Sellers, the founder. I work directly with every company in our founding cohort.
              You&apos;ll get a dedicated Slack channel, same-day responses, and my cell phone number.&rdquo;
            </p>
            <p className="text-[0.8rem] text-[var(--re-text-muted)] mt-2">
              Christopher Sellers, Founder &amp; CEO
            </p>
          </div>
        </div>
      </section>

      {/* ── EVIDENCE STRIP ── */}
      <div className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6 sm:py-8 grid grid-cols-2 lg:grid-cols-4 items-center gap-4 sm:gap-6">
          {EVIDENCE.map((e) => (
            <div key={e.label} className="flex items-baseline gap-2">
              <span className="font-serif text-[clamp(1.25rem,3vw,1.75rem)] font-bold text-[var(--re-brand-dark)] tracking-tight">
                {e.value}
              </span>
              <span className="text-[0.75rem] sm:text-[0.85rem] text-[var(--re-text-secondary)] max-w-[180px] leading-snug">
                {e.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── WHO THIS IS FOR ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Is this you?
        </p>
        <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-8 max-w-[640px]">
          Built for mid-size food suppliers who can&apos;t afford to fail an audit.
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 sm:p-6">
            <h3 className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0" />
              Good fit
            </h3>
            <ul className="space-y-2.5 text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li>Mid-size food manufacturer or distributor ($5M&ndash;$250M)</li>
              <li>Tracking traceability in spreadsheets, email, or paper</li>
              <li>Shipping to Walmart, Kroger, Costco, or similar retailers</li>
              <li>Need to prove FSMA 204 compliance but don&apos;t have a system yet</li>
            </ul>
          </div>
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 sm:p-6">
            <h3 className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
              <XCircle className="h-5 w-5 text-[var(--re-text-muted)] flex-shrink-0" />
              Not for you (yet)
            </h3>
            <ul className="space-y-2.5 text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li>Enterprise with an existing traceability platform (SAP, TraceLink)</li>
              <li>Pre-revenue startup not yet shipping product</li>
              <li>Restaurant or food service (FSMA 204 applies to manufacturing/distribution)</li>
              <li>Already passing retailer audits with your current system</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── DATA TRANSFORM DEMO ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 py-12 sm:py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          See what happens to bad data
        </p>
        <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          Messy CSV in. Defensible FDA package out.
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-8">
          This is real. Missing fields, duplicate lots, inconsistent supplier names — the kind of data you actually get. Watch RegEngine catch it all.
        </p>
        <DataTransformDemo />
        <div className="mt-8 text-center">
          <Link
            href="/walkthrough"
            className="inline-flex items-center gap-2 text-[0.85rem] font-medium text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors"
          >
            See the full 24-hour FDA response walkthrough
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* ── LIVE SANDBOX ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pb-12 sm:pb-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Try it yourself — no signup required
        </p>
        <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          Paste your data. See what breaks.
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-8">
          Drop your CSV below and RegEngine will evaluate it against all 25 FSMA 204 rules in real time. Nothing is stored.
        </p>
        <SandboxUpload />
      </section>

      {/* ── FREE TOOLS ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 py-12 sm:py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Free tools — no signup
        </p>
        <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          Check your exposure before you commit.
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-10">
          Use these now. Upgrade when you&apos;re ready.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FREE_TOOLS.map((tool) => (
            <Link
              key={tool.title}
              href={tool.href}
              className="group flex items-start gap-3 sm:gap-4 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-4 sm:p-5 shadow-sm transition-all duration-300 hover:border-[var(--re-brand)] hover:shadow-re-md hover:-translate-y-0.5 min-h-[72px]"
            >
              <div className="w-11 h-11 sm:w-10 sm:h-10 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                <tool.icon className="h-5 w-5 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-serif text-[0.95rem] sm:text-[1.05rem] font-medium text-[var(--re-text-primary)]">
                    {tool.title}
                  </h3>
                  {tool.tag && (
                    <span className="font-mono text-[0.6rem] font-medium text-[var(--re-brand)] bg-[var(--re-brand-muted)] px-2 py-0.5 rounded whitespace-nowrap">
                      {tool.tag}
                    </span>
                  )}
                </div>
                <p className="text-[0.8rem] sm:text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
                  {tool.desc}
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-[var(--re-text-muted)] mt-1.5 flex-shrink-0 group-hover:translate-x-1 group-hover:text-[var(--re-brand)] transition-all duration-300" />
            </Link>
          ))}
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="bg-[var(--re-text-primary)] text-white py-12 sm:py-20 px-4 sm:px-6">
        <div className="max-w-[1100px] mx-auto text-center">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand-light)] uppercase tracking-[0.08em] mb-4">
{/* MEDIUM #7: FSMA 204 enforcement date per FY2025 Consolidated Appropriations Act,
                 Division A, §775 (Pub. L. 118-158, signed Mar 2025). Congress directed FDA
                 not to enforce the Food Traceability Rule before this date. Verify quarterly
                 in case of legislative changes. Last verified: 2026-03-19 */}
            FSMA 204 Deadline: July 20, 2028
          </p>
          <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-white tracking-tight leading-tight mb-4 max-w-[640px] mx-auto">
            Ready to close the gap?
          </h2>
          <p className="text-[1.05rem] text-[#aaa] max-w-[560px] mx-auto leading-relaxed mb-8">
            Start with a free assessment. See exactly where you stand before the deadline hits.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/retailer-readiness"
              className="group relative inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-semibold transition-all duration-300 ease-out hover:bg-[#0BAE78] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.35)] active:translate-y-0 overflow-hidden min-h-[48px]"
            >
              <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
              <span className="relative">Free Readiness Assessment</span>
            </Link>
            <Link
              href="/pricing"
              className="inline-flex items-center justify-center gap-2 border border-[var(--re-brand)]/40 text-[var(--re-brand-light)] px-7 py-3.5 rounded-xl text-[0.95rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-white hover:bg-[var(--re-brand)]/10 hover:-translate-y-[2px] min-h-[48px]"
            >
              Join the Founding Cohort — 50% Off for Life
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
