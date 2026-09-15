import type { Metadata } from "next";
import Link from "next/link";
import { sandboxCta } from "@/lib/sandbox-cta";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
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


/**
 * One comparison cell. The icon carries the claim; the claim wording on this
 * page is legally reviewed, so no text alternative is invented here.
 */
function Mark({ value }: { value: string }) {
  if (value === "check") return <CheckCircle className="h-5 w-5 text-re-success" strokeWidth={1.75} />;
  if (value === "x") return <XCircle className="h-5 w-5 text-re-danger" strokeWidth={1.75} />;
  return <Minus className="h-5 w-5 text-re-warning" strokeWidth={1.75} />;
}

export default function ReposiTrakCompare() {
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
        title={"RegEngine vs ReposiTrak"}
        description={
          <>
            ReposiTrak connects suppliers to retailer compliance mandates. RegEngine validates your traceability data
            against FSMA 204 rules before the FDA asks to see it.
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
              <th scope="col" className="px-4 py-3 text-center text-label text-re-text-tertiary">ReposiTrak</th>
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
      <h2 className="mb-6 text-heading text-re-text-primary">Why you might run RegEngine alongside ReposiTrak</h2>
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
        ReposiTrak is a trademark of its respective owner. Comparison reflects
        publicly available information and RegEngine&apos;s interpretation; verify current capabilities
        and pricing directly with the vendor.
      </p>
    </Container>
  );
}
