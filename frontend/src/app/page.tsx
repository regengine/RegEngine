import Link from "next/link";
import { ArrowRight } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const EVIDENCE = [
  { value: "23", label: "FDA food categories mapped" },
  { value: "1", label: "API call for FDA-ready export" },
  { value: "24hr", label: "Recall window — fully covered" },
  { value: "EPCIS 2.0", label: "Native format, no conversion" },
];

const FREE_TOOLS = [
  {
    title: "FTL Coverage Checker",
    desc: "Are your products on the FDA Food Traceability List? Find out in seconds.",
    href: "/tools/ftl-checker",
    tag: null,
  },
  {
    title: "Retailer Readiness Assessment",
    desc: "Could you pass a Walmart supplier audit today? Scored automatically.",
    href: "/retailer-readiness",
    tag: "Popular",
  },
  {
    title: "FSMA 204 Compliance Guide",
    desc: "Plain-English guide to the food traceability rule. No jargon.",
    href: "/fsma-204",
    tag: null,
  },
  {
    title: "Cold-Chain Anomaly Simulator",
    desc: "Test your monitoring against real failure patterns.",
    href: "/tools/drill-simulator",
    tag: null,
  },
];

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function RegEngineLanding() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

      {/* ── HERO ── */}
      <section className="max-w-[1100px] mx-auto px-6 pt-20 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">

          {/* Left — copy */}
          <div>
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-5">
              FSMA 204 Compliance
            </p>
            <h1 className="font-serif text-[clamp(2rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
              The FDA gives you 24 hours.{" "}
              <em className="font-medium text-[var(--re-brand-dark)]">Your spreadsheets won&apos;t cut it.</em>
            </h1>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[480px]">
              RegEngine connects your suppliers, lots, and traceability events into one auditable record — so when the FDA or Walmart asks, you respond in minutes.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/onboarding"
                className="group relative inline-flex items-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Start Workspace</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/retailer-readiness"
                className="inline-flex items-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)]"
              >
                Free Readiness Assessment
              </Link>
            </div>
          </div>

          {/* Right — Walmart audit scenario card */}
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden shadow-re-md">
            {/* Card header */}
            <div className="px-5 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[var(--re-warning)]" />
              <span className="font-mono text-[0.72rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                INCOMING: SUPPLIER AUDIT REQUEST
              </span>
            </div>

            {/* Card body */}
            <div className="p-5">
              <p className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)] leading-snug mb-5">
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
                    { label: "CTEs found", value: "12 of 12", status: "good" },
                    { label: "Coverage", value: "100%", status: "good" },
                    { label: "Format", value: "EPCIS 2.0 + PDF", status: "good" },
                    { label: "Cryptographic verification", value: "Passed", status: "good" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between">
                      <span className="text-[0.8rem] text-[var(--re-text-secondary)]">{row.label}</span>
                      <span className="font-mono text-[0.8rem] font-medium text-[var(--re-brand-dark)]">{row.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Card footer */}
            <div className="px-5 py-3 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
              <span className="text-[0.8rem] text-[var(--re-text-muted)]">
                Export ready to send
              </span>
              <Link
                href="/retailer-readiness"
                className="group font-mono text-[0.72rem] font-medium bg-[var(--re-text-primary)] text-[var(--re-surface-base)] px-4 py-2 rounded-md transition-all duration-300 ease-out hover:opacity-90"
              >
                Try it with your data <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5">→</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── EVIDENCE STRIP ── */}
      <div className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1100px] mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-6">
          {EVIDENCE.map((e) => (
            <div key={e.label} className="flex items-baseline gap-2.5">
              <span className="font-serif text-[1.75rem] font-bold text-[var(--re-brand-dark)] tracking-tight">
                {e.value}
              </span>
              <span className="text-[0.85rem] text-[var(--re-text-secondary)] max-w-[180px] leading-snug">
                {e.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── FREE TOOLS ── */}
      <section className="max-w-[1100px] mx-auto px-6 py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Free tools — no signup
        </p>
        <h2 className="font-serif text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
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
              className="group flex justify-between items-start bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 transition-all duration-300 hover:border-[var(--re-brand)] hover:shadow-re-md hover:-translate-y-0.5"
            >
              <div>
                <h3 className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)] mb-1.5">
                  {tool.title}
                </h3>
                <p className="text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
                  {tool.desc}
                </p>
              </div>
              {tool.tag ? (
                <span className="font-mono text-[0.65rem] font-medium text-[var(--re-brand)] bg-[var(--re-brand-muted)] px-2.5 py-1 rounded whitespace-nowrap ml-4">
                  {tool.tag}
                </span>
              ) : (
                <span className="text-[1.2rem] text-[var(--re-text-muted)] ml-4 group-hover:translate-x-1 group-hover:text-[var(--re-brand)] transition-all duration-300">
                  →
                </span>
              )}
            </Link>
          ))}
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="bg-[var(--re-text-primary)] text-white py-20 px-6">
        <div className="max-w-[1100px] mx-auto text-center">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand-light)] uppercase tracking-[0.08em] mb-4">
            FSMA 204 Deadline: January 20, 2026
          </p>
          <h2 className="font-serif text-[2.25rem] font-bold text-white tracking-tight leading-tight mb-4 max-w-[640px] mx-auto">
            Ready to close the gap?
          </h2>
          <p className="text-[1.05rem] text-[#aaa] max-w-[560px] mx-auto leading-relaxed mb-8">
            Start with a free assessment. See exactly where you stand before the deadline hits.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              href="/retailer-readiness"
              className="group relative inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-semibold transition-all duration-300 ease-out hover:bg-[#0BAE78] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.35)] active:translate-y-0 overflow-hidden"
            >
              <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
              <span className="relative">Free Readiness Assessment</span>
            </Link>
            <Link
              href="/onboarding"
              className="inline-flex items-center gap-2 border border-[#444] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand-light)] hover:-translate-y-[2px]"
            >
              Start Workspace
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
