import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle, XCircle, Minus, ArrowRight, Shield, Clock, Code, Zap } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs FoodLogiQ (Aptean) — FSMA 204 Compliance Comparison",
  description:
    "Compare RegEngine and FoodLogiQ for FSMA 204 compliance. See how self-serve setup, real-time rule evaluation, and transparent pricing stack up against enterprise-only deployment.",
};

const FEATURES = [
  { feature: "Time to first compliance export", regengine: "check", competitor: "x", note: "Minutes vs weeks of implementation" },
  { feature: "Self-serve signup (no demo required)", regengine: "check", competitor: "x", note: "14-day free trial vs enterprise sales cycle" },
  { feature: "Public API + OpenAPI docs", regengine: "check", competitor: "x", note: "Full REST API with interactive docs" },
  { feature: "FSMA 204 rule engine (KDE + relational)", regengine: "check", competitor: "partial", note: "31 stateless + 3 cross-event rules vs basic KDE checks" },
  { feature: "Real-time compliance scoring", regengine: "check", competitor: "partial", note: "Per-event scoring vs batch reporting" },
  { feature: "CSV / API / webhook ingestion", regengine: "check", competitor: "partial", note: "All three vs API-only" },
  { feature: "Supplier portal with compliance scoring", regengine: "check", competitor: "check", note: "Both offer supplier management" },
  { feature: "Recall simulation drills", regengine: "check", competitor: "check", note: "FoodLogiQ's original strength" },
  { feature: "Transparent pricing on website", regengine: "check", competitor: "x", note: "$425-$749/mo vs custom enterprise quotes" },
  { feature: "Free sandbox / developer tools", regengine: "check", competitor: "x", note: "Try before you buy" },
];

const WHY_SWITCH = [
  { title: "Deploy in minutes, not months", desc: "FoodLogiQ requires weeks of enterprise onboarding. RegEngine's sandbox validates your data in under 60 seconds, and the full platform is live in one CSV upload." },
  { title: "Purpose-built for FSMA 204", desc: "FoodLogiQ started as recall management and bolted on FSMA 204. RegEngine was built from the ground up for the Food Traceability Rule with deep KDE validation and cross-event integrity checks." },
  { title: "No vendor lock-in", desc: "Public API, OpenAPI docs, CSV export at any time. FoodLogiQ's closed ecosystem means your data goes in but doesn't easily come out." },
  { title: "Predictable pricing", desc: "Facility-based pricing starting at $425/mo. No surprise quotes, no multi-year commitments required. FoodLogiQ's enterprise pricing often starts at 5-10x." },
];

export default function FoodLogiQCompare() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-white">
      <div className="max-w-4xl mx-auto px-4 py-16">
        {/* Hero */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-xs font-medium mb-4">
            <Shield className="w-3.5 h-3.5" />
            Comparison
          </div>
          <h1 className="text-3xl md:text-4xl font-bold mb-4">
            RegEngine vs FoodLogiQ <span className="text-[var(--re-text-muted)]">(Aptean)</span>
          </h1>
          <p className="text-[var(--re-text-muted)] text-lg max-w-2xl mx-auto">
            FoodLogiQ was built for enterprise recall management. RegEngine was built for FSMA 204 compliance from day one.
            Acquired by Aptean in 2023 &mdash; future product direction uncertain.
          </p>
        </div>

        {/* Comparison table */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden mb-12">
          <div className="grid grid-cols-3 px-4 py-3 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)] text-xs font-semibold">
            <span className="text-[var(--re-text-muted)]">Feature</span>
            <span className="text-center text-[var(--re-brand)]">RegEngine</span>
            <span className="text-center text-[var(--re-text-muted)]">FoodLogiQ</span>
          </div>
          {FEATURES.map((f, i) => (
            <div key={i} className="grid grid-cols-3 px-4 py-3 border-b border-[var(--re-surface-border)] last:border-0 items-center">
              <div>
                <div className="text-sm text-[var(--re-text-primary)]">{f.feature}</div>
                <div className="text-[0.65rem] text-[var(--re-text-disabled)]">{f.note}</div>
              </div>
              <div className="flex justify-center">
                {f.regengine === "check" && <CheckCircle className="w-5 h-5 text-green-400" />}
                {f.regengine === "x" && <XCircle className="w-5 h-5 text-red-400" />}
                {f.regengine === "partial" && <Minus className="w-5 h-5 text-amber-400" />}
              </div>
              <div className="flex justify-center">
                {f.competitor === "check" && <CheckCircle className="w-5 h-5 text-green-400" />}
                {f.competitor === "x" && <XCircle className="w-5 h-5 text-red-400" />}
                {f.competitor === "partial" && <Minus className="w-5 h-5 text-amber-400" />}
              </div>
            </div>
          ))}
        </div>

        {/* Why teams switch */}
        <h2 className="text-xl font-bold mb-6">Why teams switch from FoodLogiQ to RegEngine</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-12">
          {WHY_SWITCH.map((item, i) => (
            <div key={i} className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
              <div className="flex items-center gap-2 mb-2">
                {[<Clock key="c" />, <Zap key="z" />, <Code key="cd" />, <Shield key="s" />][i]}
                <h3 className="text-sm font-semibold">{item.title}</h3>
              </div>
              <p className="text-[0.75rem] text-[var(--re-text-muted)] leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="bg-gradient-to-r from-[var(--re-brand)]/10 to-purple-500/10 border border-[var(--re-brand)]/20 rounded-xl p-8 text-center">
          <h2 className="text-xl font-bold mb-2">See the difference yourself</h2>
          <p className="text-[var(--re-text-muted)] text-sm mb-6">
            Drop your CSV in the sandbox and get FSMA 204 compliance results in under 60 seconds. No signup required.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link href="/#sandbox" className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] transition-colors">
              Try the Sandbox <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/pricing" className="inline-flex items-center gap-2 bg-white/10 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-colors">
              See Pricing
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
