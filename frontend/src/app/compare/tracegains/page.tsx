import type { Metadata } from "next";
import Link from "next/link";
import { sandboxCta } from "@/lib/sandbox-cta";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { CheckCircle, XCircle, Minus, ArrowRight, Shield, FileText, Zap, Users } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs TraceGains — FSMA 204 Compliance Comparison",
  description:
    "Compare RegEngine and TraceGains for FSMA 204 compliance. Supplier document management vs CTE-level traceability rule evaluation.",
  openGraph: {
    title: 'RegEngine vs TraceGains — FSMA 204 Compliance Comparison',
    description: 'Compare RegEngine and TraceGains for FSMA 204 compliance. Supplier document management vs CTE-level traceability rule evaluation.',
    url: 'https://regengine.co/compare/tracegains',
    type: 'website',
  },
};

const FEATURES = [
  { feature: "Time to first compliance export", regengine: "check", competitor: "partial", note: "Self-serve onboarding vs enterprise setup" },
  { feature: "Self-serve signup", regengine: "partial", competitor: "x", note: "Staged rollout vs enterprise onboarding" },
  { feature: "Public API + OpenAPI docs", regengine: "check", competitor: "partial", note: "Full REST API; verify TraceGains' current integration surface" },
  { feature: "FSMA 204 rule engine (KDE + relational)", regengine: "check", competitor: "partial", note: "Per-event KDE validation; confirm TraceGains' current FSMA 204 coverage" },
  { feature: "Per-event compliance scoring", regengine: "check", competitor: "partial", note: "Advisory readiness signal computed per event" },
  { feature: "CSV / API / webhook ingestion", regengine: "check", competitor: "partial", note: "All three; verify TraceGains' current ingestion options" },
  { feature: "Supplier document management (COAs, specs)", regengine: "partial", competitor: "check", note: "TraceGains' core strength" },
  { feature: "Supplier onboarding portal", regengine: "check", competitor: "check", note: "Both offer supplier management" },
  { feature: "Published pricing on website", regengine: "check", competitor: "x", note: "List price from $849/mo (Founding Design Partner rates from $425/mo, billed annually) vs custom quotes" },
  { feature: "Developer sandbox", regengine: "partial", competitor: "x", note: "Staged rollout — request access" },
];

const WHY_SWITCH = [
  { title: "CTE-level traceability", icon: Zap, desc: "TraceGains is strong at COA and supplier-spec collection. FSMA 204 also requires CTE-level KDE traceability \u2014 confirm coverage with each vendor for your commodities." },
  { title: "Per-event rule evaluation", icon: Shield, desc: "RegEngine evaluates events against 36 FSMA 204 validation rules (33 stateless + 3 cross-event) as part of ingestion. Verify TraceGains' current validation features directly with their team." },
  { title: "Built for FTL commodities", icon: FileText, desc: "TraceGains is positioned for CPG supplier quality management. RegEngine is built for produce, seafood, and other FTL-covered commodities." },
  { title: "Complement, don't replace", icon: Users, desc: "You can use TraceGains for supplier docs AND RegEngine for CTE traceability. They solve different problems \u2014 you may need both." },
];


/**
 * One comparison cell. The icon carries the claim; the claim wording on this
 * page is legally reviewed, so no text alternative is invented here.
 */
function Mark({ value }: { value: string }) {
  if (value === "check") return <CheckCircle className="h-5 w-5 text-re-success" strokeWidth={1.75} />;
  if (value === "x") return <XCircle className="h-5 w-5 text-re-danger" strokeWidth={1.75} />;
  return <Minus className="h-5 w-5 text-re-warning" strokeWidth={1.75} />;
}

export default function TraceGainsCompare() {
  return (
    <Container width="marketing" as="main" className="py-16">
      <PageHeader
        size="hero"
        className="mb-12"
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            Comparison
          </span>
        }
        title={"RegEngine vs TraceGains"}
        description={
          <>
            TraceGains is a supplier document management platform. RegEngine is a FSMA 204 traceability engine.
            Different tools for different problems &mdash; here&apos;s how they compare.
          </>
        }
      />

      {/* Comparison table */}
      <div className="mb-12 overflow-x-auto rounded-lg border border-re-border bg-re-surface-card">
        <table className="w-full min-w-[560px] text-ui">
          <thead>
            <tr className="border-b border-re-border-subtle bg-re-surface-inset">
              <th scope="col" className="px-4 py-3 text-left text-label text-re-text-tertiary">Feature</th>
              <th scope="col" className="px-4 py-3 text-center text-label text-re-text-primary">RegEngine</th>
              <th scope="col" className="px-4 py-3 text-center text-label text-re-text-tertiary">TraceGains</th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.map((f, i) => (
              <tr key={i} className="border-b border-re-border-subtle last:border-0">
                <th scope="row" className="px-4 py-3 text-left align-middle font-normal">
                  <span className="block text-ui text-re-text-primary">{f.feature}</span>
                  <span className="block text-small text-re-text-tertiary">{f.note}</span>
                </th>
                <td className="px-4 py-3 align-middle">
                  <span className="flex justify-center">
                    <Mark value={f.regengine} />
                  </span>
                </td>
                <td className="px-4 py-3 align-middle">
                  <span className="flex justify-center">
                    <Mark value={f.competitor} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Why choose RegEngine */}
      <h2 className="mb-6 text-heading text-re-text-primary">Why you might run RegEngine alongside TraceGains</h2>
      <div className="mb-12 grid grid-cols-1 gap-4 md:grid-cols-2">
        {WHY_SWITCH.map((item, i) => (
          <Card key={i} padding="default" className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <item.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <h3 className="text-subheading text-re-text-primary">{item.title}</h3>
            </div>
            <p className="text-small leading-relaxed text-re-text-secondary">{item.desc}</p>
          </Card>
        ))}
      </div>

      {/* CTA */}
      <Card padding="spacious" className="text-center">
        <h2 className="mb-2 text-heading text-re-text-primary">See the difference yourself</h2>
        {/* #2757 — copy and destination resolve together so the blurb can never
            promise a CSV sandbox that this deployment does not serve. */}
        <p className="mx-auto mb-6 max-w-[68ch] text-ui text-re-text-secondary">
          {sandboxCta().blurb}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link href={sandboxCta().href} className="no-underline">
              {sandboxCta().label} <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/pricing" className="no-underline">
              See Pricing
            </Link>
          </Button>
        </div>
      </Card>

      <p className="mt-10 text-small leading-relaxed text-re-text-tertiary">
        TraceGains is a trademark of its respective owner. Comparison reflects publicly available
        information and RegEngine&apos;s interpretation; verify current capabilities and pricing
        directly with the vendor.
      </p>
    </Container>
  );
}
