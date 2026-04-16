import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle, XCircle, Minus, ArrowRight, Shield, FileText, Zap, Users } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs TraceGains — FSMA 204 Compliance Comparison",
  description:
    "Compare RegEngine and TraceGains for FSMA 204 compliance. Document management vs real-time traceability rule evaluation.",
};

const FEATURES = [
  { feature: "Time to first compliance export", regengine: "check", competitor: "x", note: "Minutes vs weeks of setup" },
  { feature: "Self-serve signup (no demo required)", regengine: "check", competitor: "x", note: "14-day free trial vs enterprise onboarding" },
  { feature: "Public API + OpenAPI docs", regengine: "check", competitor: "x", note: "Full REST API vs limited integrations" },
  { feature: "FSMA 204 rule engine (KDE + relational)", regengine: "check", competitor: "x", note: "Deep validation vs document storage" },
  { feature: "Real-time compliance scoring", regengine: "check", competitor: "x", note: "Per-event scoring vs manual review" },
  { feature: "CSV / API / webhook ingestion", regengine: "check", competitor: "partial", note: "All three vs document upload" },
  { feature: "Supplier document management (COAs, specs)", regengine: "partial", competitor: "check", note: "TraceGains' core strength" },
  { feature: "Supplier onboarding portal", regengine: "check", competitor: "check", note: "Both offer supplier management" },
  { feature: "Transparent pricing on website", regengine: "check", competitor: "x", note: "$425-$749/mo vs custom quotes" },
  { feature: "Free sandbox / developer tools", regengine: "check", competitor: "x", note: "Try before you buy" },
];

const WHY_SWITCH = [
  { title: "Traceability, not just documents", icon: Zap, desc: "TraceGains excels at collecting COAs and supplier specs. But FSMA 204 requires CTE-level traceability with KDE validation \u2014 something document management can\u2019t do." },
  { title: "Real-time rule evaluation", icon: Shield, desc: "RegEngine validates every event against 31+ FSMA 204 rules in real time. TraceGains stores documents but doesn\u2019t validate the data inside them." },
  { title: "Built for fresh produce", icon: FileText, desc: "TraceGains was built for CPG supplier quality management. RegEngine is purpose-built for produce, seafood, and FTL-covered commodities." },
  { title: "Complement, don't replace", icon: Users, desc: "Many teams use TraceGains for supplier docs AND RegEngine for CTE traceability. They solve different problems \u2014 you may need both." },
];

export default function TraceGainsCompare() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-white">
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-xs font-medium mb-4">
            <Shield className="w-3.5 h-3.5" />
            Comparison
          </div>
          <h1 className="text-3xl md:text-4xl font-bold mb-4">RegEngine vs TraceGains</h1>
          <p className="text-[var(--re-text-muted)] text-lg max-w-2xl mx-auto">
            TraceGains is a supplier document management platform. RegEngine is a FSMA 204 traceability engine.
            Different tools for different problems &mdash; here&apos;s how they compare.
          </p>
        </div>

        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden mb-12">
          <div className="grid grid-cols-3 px-4 py-3 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)] text-xs font-semibold">
            <span className="text-[var(--re-text-muted)]">Feature</span>
            <span className="text-center text-[var(--re-brand)]">RegEngine</span>
            <span className="text-center text-[var(--re-text-muted)]">TraceGains</span>
          </div>
          {FEATURES.map((f, i) => (
            <div key={i} className="grid grid-cols-3 px-4 py-3 border-b border-[var(--re-surface-border)] last:border-0 items-center">
              <div>
                <div className="text-sm text-[var(--re-text-primary)]">{f.feature}</div>
                <div className="text-[0.65rem] text-[var(--re-text-disabled)]">{f.note}</div>
              </div>
              <div className="flex justify-center">
                {f.regengine === "check" ? <CheckCircle className="w-5 h-5 text-green-400" /> : f.regengine === "x" ? <XCircle className="w-5 h-5 text-red-400" /> : <Minus className="w-5 h-5 text-amber-400" />}
              </div>
              <div className="flex justify-center">
                {f.competitor === "check" ? <CheckCircle className="w-5 h-5 text-green-400" /> : f.competitor === "x" ? <XCircle className="w-5 h-5 text-red-400" /> : <Minus className="w-5 h-5 text-amber-400" />}
              </div>
            </div>
          ))}
        </div>

        <h2 className="text-xl font-bold mb-6">Why teams add RegEngine alongside TraceGains</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-12">
          {WHY_SWITCH.map((item, i) => (
            <div key={i} className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
              <div className="flex items-center gap-2 mb-2">
                <item.icon className="w-4 h-4 text-[var(--re-brand)]" />
                <h3 className="text-sm font-semibold">{item.title}</h3>
              </div>
              <p className="text-[0.75rem] text-[var(--re-text-muted)] leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>

        <div className="bg-gradient-to-r from-[var(--re-brand)]/10 to-purple-500/10 border border-[var(--re-brand)]/20 rounded-xl p-8 text-center">
          <h2 className="text-xl font-bold mb-2">See the difference yourself</h2>
          <p className="text-[var(--re-text-muted)] text-sm mb-6">Drop your CSV in the sandbox and get FSMA 204 compliance results in under 60 seconds.</p>
          <div className="flex items-center justify-center gap-4">
            <Link href="/#sandbox" className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] transition-colors">
              Try the Sandbox <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/pricing" className="inline-flex items-center gap-2 bg-white/10 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-colors">See Pricing</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
