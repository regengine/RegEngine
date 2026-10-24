import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Database, FileCode2, Hash, KeyRound, Lock, ShieldCheck, Terminal } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { NO_DATA_YET } from "@/lib/empty-values";

export const metadata: Metadata = {
  title: "Security | RegEngine",
  description:
    "RegEngine security posture: tenant isolation, evidence integrity after ingest, verifiable export manifests, and exportability.",
  openGraph: {
    title: "Security | RegEngine",
    description: "Tenant isolation, evidence integrity, and verification posture for FSMA 204 records.",
    url: "https://regengine.co/security",
    type: "website",
  },
};

const verified = [
  { title: "Tenant isolation", body: "PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict cross-tenant access on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in active rollout; details available under NDA.", icon: Lock },
  { title: "Append-oriented evidence", body: "Committed compliance records are append-oriented after ingest, and corrections preserve lineage rather than mutating prior records.", icon: Database },
  { title: "Hash verification", body: "Export bundles ship with a SHA-256 manifest so records can be checked outside the product UI. Legacy Kafka-compatible signing exists only for opt-in deployments.", icon: Hash },
  { title: "Operational gates", body: "CI includes secrets, SAST, and dependency checks. DAST, SBOM, and container scans run when configured or on scheduled/main-branch workflows.", icon: ShieldCheck },
];

const controls = [
  ["Encryption", "Encrypted transport in transit; encryption at rest provided by managed database and storage providers (see subprocessors)"],
  ["Identity", "JWT sessions, API keys, CSRF protection"],
  ["Isolation", "Tenant-scoped database access via PostgreSQL row-level policies on core PostgreSQL-backed paths"],
  ["Audit", "Tamper-evident export manifests covering records after ingest; upstream entry is not cryptographically attested"],
  ["Verification", "Open verifier script for export-bundle chain checks"],
  ["Disclosure", "security.txt and vulnerability intake"],
];

const links = [
  { icon: Terminal, label: "Open verifier", href: "/verify" },
  { icon: FileCode2, label: "Security details", href: "/trust/architecture" },
  { icon: KeyRound, label: "Contact security", href: "/contact" },
];

export default function SecurityPage() {
  return (
    <div className="re-page min-h-screen">
      <Container className="grid gap-10 pb-14 pt-12 md:grid-cols-[0.85fr_1fr] md:pb-20 md:pt-16">
        <div>
          <PageHeader
            size="hero"
            eyebrow={<span className="font-mono uppercase">Security</span>}
            title="Verify the evidence, not just the dashboard."
            description="Compliance security should be mechanical: isolate tenants, preserve lineage, hash the evidence, and make verification possible without asking anyone to believe the UI."
            className="mb-0 border-b-0 pb-0"
          />
          <p className="mt-4 max-w-[70ch] text-small text-re-text-tertiary">
            These statements describe controls verified in source and pre-production staging. Production
            validation requires a release-evidence record bound to the deployed frontend and backend commits.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/verify">
                See verification <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/trust">Trust center</Link>
            </Button>
          </div>
        </div>
        <Card className="overflow-hidden">
          <EmptyState
            bare
            size="sm"
            title={NO_DATA_YET}
            description="Verifier output appears here once you export a package from your own records."
            action={
              <Button asChild size="sm">
                <Link href="/ingest">Upload a CSV</Link>
              </Button>
            }
          />
          <div className="grid gap-5 border-t border-re-border-subtle p-5 sm:grid-cols-3">
            <div>
              <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Bundle</p>
              <p className="font-mono text-[0.8125rem] text-re-text-primary">fsma_package.json</p>
              <p className="mt-1 text-small text-re-text-tertiary">Export package selected by the customer workflow.</p>
            </div>
            <div>
              <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Manifest</p>
              <p className="font-mono text-[0.8125rem] text-re-text-primary">SHA-256</p>
              <p className="mt-1 text-small text-re-text-tertiary">Integrity check for records after ingest, not upstream entry proof.</p>
            </div>
            <div>
              <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Review path</p>
              <p className="text-ui font-medium text-re-text-primary">Outside the UI</p>
              <p className="mt-1 text-small text-re-text-tertiary">A supported bundle can be checked independently.</p>
            </div>
          </div>
        </Card>
      </Container>

      <Section width="marketing">
        <div className="grid gap-5 md:grid-cols-4">
          {verified.map(({ title, body, icon: Icon }) => (
            <article key={title} className="h-full">
              <Card className="h-full p-5">
                <Icon className="mb-8 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                <h2 className="text-subheading text-re-text-primary">{title}</h2>
                <p className="mt-3 text-ui text-re-text-secondary">{body}</p>
              </Card>
            </article>
          ))}
        </div>
      </Section>

      <Section width="marketing">
        <div className="grid gap-8 md:grid-cols-[0.75fr_1fr]">
          <div>
            <p className="mb-4 font-mono text-label uppercase text-re-text-muted">Control surface</p>
            <h2 className="font-display text-heading-lg text-re-text-primary">Security claims expressed as checks.</h2>
          </div>
          <Card className="overflow-x-auto">
            <table className="re-rule-table">
              <tbody>
                {controls.map(([label, detail]) => (
                  <tr key={label}>
                    <td className="w-1/3 align-top font-mono text-label uppercase text-re-text-muted">
                      <span className="inline-flex items-center gap-2">
                        <span className="re-signal text-re-text-tertiary" aria-hidden="true" />
                        {label}
                      </span>
                    </td>
                    <td className="text-re-text-primary">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </Section>

      <Section width="marketing">
        <Card className="overflow-hidden">
          {links.map(({ icon: Icon, label, href }) => (
            <Link
              key={label}
              href={href}
              className="flex items-center gap-3 border-b border-re-border-subtle px-5 py-4 text-subheading text-re-text-primary no-underline transition-colors duration-120 last:border-0 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
            >
              <Icon className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
              <span className="flex-1">{label}</span>
              <ArrowRight className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          ))}
        </Card>
      </Section>
    </div>
  );
}
