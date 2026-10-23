import type { Metadata } from "next";
import Link from "next/link";
import { sandboxCta } from "@/lib/sandbox-cta";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { CheckCircle, XCircle, Minus, ArrowRight, Shield, Clock, Code, Zap } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs FoodLogiQ (Aptean): FSMA 204 Compliance Comparison",
  description:
    "Compare RegEngine and FoodLogiQ for FSMA 204 compliance. See how self-serve setup, rule evaluation, and transparent pricing differ from enterprise-only deployment.",
  openGraph: {
    title: 'RegEngine vs FoodLogiQ (Aptean): FSMA 204 Compliance Comparison',
    description: 'Compare RegEngine and FoodLogiQ for FSMA 204 compliance. See how self-serve setup, rule evaluation, and transparent pricing differ from enterprise-only deployment.',
    url: 'https://regengine.co/compare/foodlogiq',
    type: 'website',
  },
};

const FEATURES = [
  { feature: "Time to first compliance export", regengine: "check", competitor: "partial", note: "Self-serve onboarding vs enterprise implementation" },
  { feature: "Self-serve signup", regengine: "partial", competitor: "x", note: "Staged rollout vs enterprise sales cycle" },
  { feature: "Public API + OpenAPI docs", regengine: "check", competitor: "partial", note: "Full REST API with interactive docs; verify FoodLogiQ's current API surface" },
  { feature: "FSMA 204 rule engine (KDE + relational)", regengine: "check", competitor: "partial", note: "36 FSMA 204 validation rules (33 stateless + 3 cross-event); rule enforcement is configurable per workflow" },
  { feature: "Per-event compliance scoring", regengine: "check", competitor: "partial", note: "Advisory readiness signal computed per event vs batch reporting" },
  { feature: "CSV upload and JSON events API", regengine: "check", competitor: "partial", note: "Both; verify FoodLogiQ's current ingestion surface" },
  { feature: "Supplier portal with compliance scoring", regengine: "check", competitor: "check", note: "Both offer supplier management" },
  { feature: "Recall simulation drills", regengine: "check", competitor: "check", note: "FoodLogiQ's original strength" },
  { feature: "Published pricing on website", regengine: "check", competitor: "x", note: "List price from $849/mo (Founding rates from $425/mo, billed annually) vs custom enterprise quotes" },
  { feature: "Developer sandbox", regengine: "partial", competitor: "x", note: "Staged rollout; request access" },
];

const WHY_SWITCH = [
  // #2757 - this used to assert the sandbox returns results "in seconds" regardless of
  // whether the sandbox surface is enabled on the deployment. Reworded to the claim the
  // product makes unconditionally: rule evaluation runs on the first CSV you upload.
  { title: "Self-serve onboarding", desc: "RegEngine evaluates your first CSV against the FSMA 204 rule set on upload, with no implementation project to get a readiness answer. FoodLogiQ ships through enterprise implementation; verify current onboarding timelines with their team." },
  { title: "Purpose-built for FSMA 204", desc: "FoodLogiQ originated as recall management; FSMA 204 capabilities were added later per their public roadmap. RegEngine was designed for the Food Traceability Rule from day one with KDE validation and cross-event integrity checks." },
  { title: "Open data egress", desc: "RegEngine ships a public API, OpenAPI docs, and CSV export of every record. Confirm FoodLogiQ's current data-egress options with their team before committing." },
  { title: "Published pricing", desc: "Facility-based list pricing from $849/mo, with Founding rates from $425/mo (billed annually) and no multi-year commitment required. FoodLogiQ pricing is custom-quoted, so request both to compare for your facility count." },
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

export default function FoodLogiQCompare() {
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
        title={
          <>
            RegEngine vs FoodLogiQ <span className="text-re-text-tertiary">(Aptean)</span>
          </>
        }
        description={
          <>
            FoodLogiQ was built for enterprise recall management. RegEngine was built for FSMA 204 compliance from day one.
            FoodLogiQ was acquired by Aptean in 2023; check their roadmap for current direction.
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
              <th scope="col" className="px-4 py-3 text-center text-label text-re-text-tertiary">FoodLogiQ</th>
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
      <h2 className="mb-6 text-heading text-re-text-primary">Why you might choose RegEngine over FoodLogiQ</h2>
      <div className="mb-12 grid grid-cols-1 gap-4 md:grid-cols-2">
        {WHY_SWITCH.map((item, i) => (
          <Card key={i} padding="default" className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <span className="shrink-0 text-re-text-tertiary [&_svg]:h-4 [&_svg]:w-4">
                {[<Clock key="c" strokeWidth={1.75} aria-hidden="true" />, <Zap key="z" strokeWidth={1.75} aria-hidden="true" />, <Code key="cd" strokeWidth={1.75} aria-hidden="true" />, <Shield key="s" strokeWidth={1.75} aria-hidden="true" />][i]}
              </span>
              <h3 className="text-subheading text-re-text-primary">{item.title}</h3>
            </div>
            <p className="text-small leading-relaxed text-re-text-secondary">{item.desc}</p>
          </Card>
        ))}
      </div>

      {/* CTA */}
      <Card padding="spacious" className="text-center">
        <h2 className="mb-2 text-heading text-re-text-primary">See the difference yourself</h2>
        {/* #2757 - copy and destination resolve together so the blurb can never
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
        FoodLogiQ and Aptean are trademarks of their respective owners. Comparison reflects publicly
        available information and RegEngine&apos;s interpretation; verify current capabilities and pricing
        directly with the vendor.
      </p>
    </Container>
  );
}
