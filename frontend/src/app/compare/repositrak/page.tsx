import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle, XCircle, Minus, ArrowRight, Shield, ShoppingCart, Zap, Code } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs ReposiTrak — FSMA 204 Compliance Comparison",
  description:
    "Compare RegEngine and ReposiTrak for FSMA 204 compliance. Deep rule validation vs retailer compliance tracking.",
};

const FEATURES = [
  { feature: "Time to first compliance export", regengine: "check", competitor: "partial", note: "Self-serve onboarding vs retailer-coordinated setup" },
  { feature: "Self-serve signup", regengine: "partial", competitor: "partial", note: "Staged rollout; ReposiTrak access is typically retailer-mediated" },
  { feature: "Public API + OpenAPI docs", regengine: "check", competitor: "partial", note: "Full REST API; verify ReposiTrak's current API surface for your stack" },
  { feature: "FSMA 204 rule engine (KDE + relational)", regengine: "check", competitor: "partial", note: "Per-event KDE validation; rule enforcement is configurable per workflow" },
  { feature: "Per-event compliance scoring", regengine: "check", competitor: "partial", note: "Advisory readiness signal computed per event vs status tracking" },
  { feature: "CSV / API / webhook ingestion", regengine: "check", competitor: "partial", note: "All three; verify ReposiTrak's current ingestion options" },
  { feature: "Retailer compliance network", regengine: "partial", competitor: "check", note: "ReposiTrak's core strength" },
  { feature: "Supplier portal", regengine: "check", competitor: "check", note: "Both offer supplier management" },
  { feature: "Published pricing on website", regengine: "check", competitor: "x", note: "List price from $849/mo (Founding Design Partner rates from $425/mo, billed annually) vs custom retailer quotes" },
  { feature: "Developer sandbox", regengine: "partial", competitor: "x", note: "Staged rollout — request access" },
];

const WHY_SWITCH = [
  { title: "Validation, not just submission tracking", icon: Zap, desc: "ReposiTrak focuses on supplier-data submission tracking. RegEngine validates whether the underlying data is FSMA 204 compliant \u2014 checking KDEs, cross-event integrity, and mass balance. You can use both." },
  { title: "Works beyond one retailer", icon: Shield, desc: "ReposiTrak is optimized for retailer-supplier compliance mandates. RegEngine works across your supply chain regardless of which retailers you serve." },
  { title: "Public API and open egress", icon: Code, desc: "RegEngine ships a public REST API, OpenAPI spec, webhook integrations, and CSV export at any time. Confirm ReposiTrak's current integration options for your stack." },
  { title: "Complement your retailer tools", icon: ShoppingCart, desc: "Use ReposiTrak for retailer compliance tracking AND RegEngine for FSMA 204 validation. They solve adjacent problems." },
];

export default function ReposiTrakCompare() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-white">
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-xs font-medium mb-4">
            <Shield className="w-3.5 h-3.5" />
            Comparison
          </div>
          <h1 className="text-3xl md:text-4xl font-bold mb-4">RegEngine vs ReposiTrak</h1>
          <p className="text-[var(--re-text-muted)] text-lg max-w-2xl mx-auto">
            ReposiTrak connects suppliers to retailer compliance mandates. RegEngine validates your traceability data
            against FSMA 204 rules before the FDA asks to see it.
          </p>
        </div>

        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden mb-12">
          <div className="grid grid-cols-3 px-4 py-3 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)] text-xs font-semibold">
            <span className="text-[var(--re-text-muted)]">Feature</span>
            <span className="text-center text-[var(--re-brand)]">RegEngine</span>
            <span className="text-center text-[var(--re-text-muted)]">ReposiTrak</span>
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

        <h2 className="text-xl font-bold mb-6">Why you might run RegEngine alongside ReposiTrak</h2>
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
            <Link href="/demo" className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] transition-colors">
              Explore the interactive demo <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/pricing" className="inline-flex items-center gap-2 bg-white/10 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-colors">See Pricing</Link>
          </div>
        </div>

        <p className="mt-10 text-[0.65rem] text-[var(--re-text-disabled)] leading-relaxed">
          ReposiTrak is a trademark of its respective owner. Comparison reflects
          publicly available information and RegEngine&apos;s interpretation; verify current capabilities
          and pricing directly with the vendor.
        </p>
      </div>
    </div>
  );
}
