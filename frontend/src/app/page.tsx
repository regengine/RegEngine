import Link from "next/link";
import { ArrowRight } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const EVIDENCE = [
  { value: "23", label: "FDA food categories verified and mapped" },
  { value: "1", label: "API call to generate FDA-ready export" },
  { value: "24hr", label: "Recall response window — fully covered" },
  { value: "EPCIS 2.0", label: "Native export format, no conversion needed" },
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
    title: "Supply Chain Explorer",
    desc: "See how traceability works across real recall scenarios.",
    href: "/demo/supply-chains",
    tag: null,
  },
  {
    title: "Cold-Chain Anomaly Simulator",
    desc: "Test your monitoring against real failure patterns.",
    href: "/tools/drill-simulator",
    tag: null,
  },
];

const DASHBOARD_ROWS = [
  { product: "Romaine Lettuce (Lot R-2026-0312)", ftl: "Complete", cte: "12/12", last: "2h ago", status: "complete" },
  { product: "Atlantic Salmon (Lot S-2026-0311)", ftl: "Complete", cte: "10/10", last: "6h ago", status: "complete" },
  { product: "Shell Eggs (Lot E-2026-0310)", ftl: "Partial", cte: "7/9", last: "1d ago", status: "partial" },
  { product: "Peanut Butter (Lot P-2026-0308)", ftl: "Gap", cte: "4/8", last: "3d ago", status: "missing" },
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
              FSMA 204 Compliance Infrastructure
            </p>
            <h1 className="font-serif text-[clamp(2rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
              The FDA gives you 24 hours.{" "}
              <em className="font-medium text-[var(--re-brand-dark)]">Can you deliver?</em>
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

          {/* Right — recall simulation card */}
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden shadow-re-md">
            {/* Sim header */}
            <div className="px-5 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[var(--re-danger)] animate-pulse" />
              <span className="font-mono text-[0.72rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                RECALL SIMULATION — LIVE
              </span>
            </div>

            {/* Sim body */}
            <div className="p-5">
              <p className="font-mono text-[0.72rem] text-[var(--re-text-muted)] uppercase tracking-[0.06em] mb-2">
                Incoming FDA Request
              </p>
              <p className="font-serif text-[1.1rem] font-medium text-[var(--re-text-primary)] leading-snug mb-5">
                <span className="text-[var(--re-danger)]"><em>E.&nbsp;coli O157:H7</em></span> detected in romaine lettuce.<br />
                Trace all affected lots from farm to shelf.
              </p>

              <div className="grid grid-cols-2 gap-3">
                {/* Without */}
                <div className="p-4 rounded-lg bg-[var(--re-danger-muted)] border border-[rgba(220,38,38,0.2)]">
                  <p className="font-mono text-[0.65rem] font-medium text-[var(--re-danger)] uppercase tracking-[0.08em] mb-3">Without RegEngine</p>
                  <div className="space-y-2">
                    {[
                      { label: "Response time", value: "18 hours", bad: true },
                      { label: "Data sources", value: "7 systems", bad: false },
                      { label: "Completeness", value: "62%", bad: true },
                      { label: "Verifiable", value: "No", bad: true },
                    ].map((r) => (
                      <div key={r.label}>
                        <p className="text-[0.7rem] text-[var(--re-text-muted)]">{r.label}</p>
                        <p className={`font-mono text-[0.85rem] font-medium ${r.bad ? "text-[var(--re-danger)]" : "text-[var(--re-text-primary)]"}`}>{r.value}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* With */}
                <div className="p-4 rounded-lg bg-[var(--re-success-muted)] border border-[rgba(22,163,74,0.2)]">
                  <p className="font-mono text-[0.65rem] font-medium text-[var(--re-brand-dark)] uppercase tracking-[0.08em] mb-3">With RegEngine</p>
                  <div className="space-y-2">
                    {[
                      { label: "Response time", value: "42 min", good: true },
                      { label: "Data sources", value: "1 API call", good: false },
                      { label: "Completeness", value: "98%", good: true },
                      { label: "Verifiable", value: "Cryptographic", good: true },
                    ].map((r) => (
                      <div key={r.label}>
                        <p className="text-[0.7rem] text-[var(--re-text-muted)]">{r.label}</p>
                        <p className={`font-mono text-[0.85rem] font-medium ${r.good ? "text-[var(--re-brand-dark)]" : "text-[var(--re-text-primary)]"}`}>{r.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Sim footer */}
            <div className="px-5 py-3 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
              <span className="font-mono text-sm">
                <strong className="text-[var(--re-brand-dark)] text-lg">96%</strong>{" "}
                <span className="text-[var(--re-text-muted)] text-xs">faster recall response</span>
              </span>
              <Link
                href="/tools/drill-simulator"
                className="group font-mono text-[0.72rem] font-medium bg-[var(--re-text-primary)] text-[var(--re-surface-base)] px-4 py-2 rounded-md transition-all duration-300 ease-out hover:opacity-90 hover:shadow-[0_4px_12px_rgba(0,0,0,0.2)]"
              >
                Run Full Simulation <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5">→</span>
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

      {/* ── HOW IT WORKS — Pipeline ── */}
      <section className="max-w-[1100px] mx-auto px-6 py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          How it works
        </p>
        <h2 className="font-serif text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          Data in, compliance out.
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-10">
          No twelve-month implementation. No six-figure platform fee. Connect your supply chain data and get audit-ready exports from day one.
        </p>

        <div className="flex flex-col md:flex-row bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden">
          {[
            { tag: "Ingest", title: "Connect your supply chain", desc: "API, CSV, EDI 856, or supplier portal. RegEngine normalizes everything into EPCIS 2.0 automatically." },
            { tag: "Monitor", title: "Track compliance live", desc: "CTE/KDE coverage scoring, gap detection, and cold-chain alerts across every FTL-covered product." },
            { tag: "Export", title: "Respond in minutes", desc: "FDA requests, retailer audits, recall simulations — one call, complete chain of custody, cryptographically verifiable." },
          ].map((step, i, arr) => (
            <div
              key={step.tag}
              className={`flex-1 p-7 ${i < arr.length - 1 ? "md:border-r border-b md:border-b-0 border-[var(--re-surface-border)]" : ""} relative`}
            >
              <span className="inline-block font-mono text-[0.65rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.06em] bg-[var(--re-brand-muted)] px-2.5 py-1 rounded mb-3">
                {step.tag}
              </span>
              <h3 className="font-serif text-[1.1rem] font-medium text-[var(--re-text-primary)] mb-2">
                {step.title}
              </h3>
              <p className="text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
                {step.desc}
              </p>
              {i < arr.length - 1 && (
                <span className="hidden md:block absolute right-[-0.6rem] top-1/2 -translate-y-1/2 text-[1.2rem] text-[var(--re-text-muted)] z-10">
                  →
                </span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── PRODUCT DASHBOARD MOCKUP ── */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-20 px-6">
        <div className="max-w-[1100px] mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            The product
          </p>
          <h2 className="font-serif text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
            This is what recall-ready looks like.
          </h2>
          <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-10">
            Not a slide deck. Not a roadmap. This is the compliance command center your team logs into.
          </p>

          {/* Fake browser window */}
          <div className="bg-[#111] rounded-xl overflow-hidden shadow-re-lg">
            {/* Title bar */}
            <div className="bg-[#1a1a1a] px-4 py-3 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#28CA41]" />
              <span className="font-mono text-[0.7rem] text-[#666] ml-2">app.regengine.co/dashboard</span>
            </div>

            {/* Dashboard content */}
            <div className="p-6 grid grid-cols-1 md:grid-cols-[200px_1fr] gap-5 min-h-[380px]">
              {/* Sidebar */}
              <div className="md:border-r md:border-[#2a2a2a] md:pr-5 flex md:flex-col flex-wrap gap-0.5">
                {["Dashboard", "Facilities", "Products", "Suppliers", "CTE Events", "FDA Export", "Alerts", "Audit Log"].map((item) => (
                  <span
                    key={item}
                    className={`font-mono text-[0.72rem] px-3 py-2 rounded-md cursor-default ${item === "Dashboard" ? "text-[var(--re-brand)] bg-[rgba(13,150,104,0.1)]" : "text-[#888]"}`}
                  >
                    {item}
                  </span>
                ))}
              </div>

              {/* Main area */}
              <div className="text-[#ddd]">
                <div className="flex justify-between items-center mb-5">
                  <span className="font-serif text-[1.15rem] font-medium text-white">Compliance Overview</span>
                  <span className="font-mono text-[0.72rem] font-medium px-3 py-1.5 rounded-full bg-[rgba(13,150,104,0.15)] text-[var(--re-brand)] border border-[rgba(13,150,104,0.3)]">
                    Recall Ready: 94%
                  </span>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
                  {[
                    { label: "CTE Coverage", value: "96%", color: "text-[var(--re-brand)]" },
                    { label: "Supplier Score", value: "91%", color: "text-[var(--re-brand)]" },
                    { label: "Open Gaps", value: "3", color: "text-[#EAB308]" },
                  ].map((m) => (
                    <div key={m.label} className="bg-[rgba(255,255,255,0.03)] border border-[#2a2a2a] rounded-lg p-4">
                      <p className="font-mono text-[0.65rem] text-[#666] uppercase tracking-[0.06em] mb-2">{m.label}</p>
                      <p className={`font-serif text-[1.5rem] font-bold ${m.color}`}>{m.value}</p>
                    </div>
                  ))}
                </div>

                {/* Table */}
                <div className="hidden sm:grid grid-cols-[2fr_1fr_1fr_1fr] px-0 py-2 border-b border-[#2a2a2a] font-mono text-[0.65rem] text-[#555] uppercase tracking-[0.06em]">
                  <span>Product</span>
                  <span>FTL Status</span>
                  <span>CTE/KDE</span>
                  <span>Last Event</span>
                </div>
                {DASHBOARD_ROWS.map((row) => (
                  <div key={row.product} className="hidden sm:grid grid-cols-[2fr_1fr_1fr_1fr] py-2.5 border-b border-[rgba(255,255,255,0.03)] text-[0.8rem] text-[#bbb] items-center">
                    <span>{row.product}</span>
                    <span>
                      <span className={`font-mono text-[0.65rem] font-medium px-2 py-0.5 rounded ${
                        row.status === "complete"
                          ? "bg-[rgba(13,150,104,0.15)] text-[var(--re-brand)]"
                          : row.status === "partial"
                          ? "bg-[rgba(234,179,8,0.15)] text-[#EAB308]"
                          : "bg-[rgba(220,38,38,0.15)] text-[#F87171]"
                      }`}>
                        {row.ftl}
                      </span>
                    </span>
                    <span>{row.cte}</span>
                    <span className="font-mono text-[0.75rem]">{row.last}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FREE TOOLS ── */}
      <section className="max-w-[1100px] mx-auto px-6 py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Free tools — no signup
        </p>
        <h2 className="font-serif text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          Check your exposure before you commit.
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-10">
          Built by a food industry founder who knows the FSMA 204 deadline is real. Use these now, upgrade when you&apos;re ready.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FREE_TOOLS.map((tool) => (
            <Link
              key={tool.title}
              href={tool.href}
              className="group flex justify-between items-start bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 transition-all hover:border-[var(--re-brand)] hover:shadow-re-md hover:-translate-y-0.5"
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
                <span className="text-[1.2rem] text-[var(--re-text-muted)] ml-4 group-hover:translate-x-1 group-hover:text-[var(--re-brand)] transition-all">
                  →
                </span>
              )}
            </Link>
          ))}
        </div>
      </section>

      {/* ── FOUNDER ── */}
      <section className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-base)] py-20 px-6">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-[280px_1fr] gap-12 items-start">
          {/* Photo placeholder */}
          <div className="w-full md:w-[280px] h-[320px] bg-gradient-to-br from-[var(--re-brand-muted)] to-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] rounded-xl flex items-center justify-center">
            <p className="font-mono text-[0.72rem] text-[var(--re-text-muted)] text-center leading-relaxed px-4">
              [ Your photo here ]
            </p>
          </div>

          <div>
            <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
              From the founder
            </p>
            <h2 className="font-serif text-[1.75rem] font-bold text-[var(--re-text-primary)] tracking-tight mb-6">
              Built by someone who knows food compliance.
            </h2>
            <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-4 max-w-[540px]">
              Family restaurant kid. Organic farm hand. AmeriCorps volunteer. U.S. Senate staff. Startup closer.
            </p>
            <blockquote className="font-serif italic text-[1.15rem] text-[var(--re-text-primary)] border-l-[3px] border-[var(--re-brand)] pl-5 my-6 leading-relaxed max-w-[540px]">
              &ldquo;Compliance shouldn&apos;t require a six-figure platform and a twelve-month implementation. Your traceability data should be verified, exportable, and ready before anyone asks for it.&rdquo;
            </blockquote>
            <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed max-w-[540px]">
              Every record in RegEngine is deterministic, versioned, and independently verifiable. No AI guessing. No black boxes.
            </p>
            <Link
              href="/retailer-readiness"
              className="group inline-flex items-center gap-2.5 bg-[var(--re-brand)] text-white px-6 py-3 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_6px_24px_rgba(16,185,129,0.25)] active:translate-y-0 mt-6"
            >
              Run Free Assessment
              <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="bg-[var(--re-text-primary)] text-white py-20 px-6">
        <div className="max-w-[1100px] mx-auto text-center">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand-light)] uppercase tracking-[0.08em] mb-4">
            FSMA 204 Deadline: July 20, 2028
          </p>
          <h2 className="font-serif text-[2.25rem] font-bold text-white tracking-tight leading-tight mb-4 max-w-[640px] mx-auto">
            Ready to close the gap?
          </h2>
          <p className="text-[1.05rem] text-[#aaa] max-w-[560px] mx-auto leading-relaxed mb-8">
            Start with a free assessment. See exactly what it takes to move from reactive traceability to recall-ready infrastructure.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              href="/retailer-readiness"
              className="group relative inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-semibold transition-all duration-300 ease-out hover:bg-[#0BAE78] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.35)] active:translate-y-0 overflow-hidden"
            >
              <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
              <span className="relative">Retailer Readiness Assessment</span>
            </Link>
            <Link
              href="/pricing"
              className="inline-flex items-center gap-2 border border-[#444] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand-light)] hover:-translate-y-[2px]"
            >
              View Pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
