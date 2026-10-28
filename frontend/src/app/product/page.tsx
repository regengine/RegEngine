import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  Database,
  FileOutput,
  GitCommitHorizontal,
  GitPullRequestArrow,
  Lock,
  PackageX,
  ScanLine,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";

export const metadata: Metadata = {
  title: "Product | RegEngine",
  description:
    "RegEngine preflights supplier traceability feeds, creates fix queues, gates production evidence, and helps assemble FSMA 204 export packages from checked tenant data.",
  openGraph: {
    title: "Product | RegEngine",
    description: "Supplier feed preflight plus an FSMA 204 evidence engine with explicit commit gates.",
    url: "https://regengine.co/product",
    type: "website",
  },
};

const inflowEffects = [
  {
    title: "Normalize",
    detail: "Raw rows become CTE/KDE candidates with source, lot, facility, and handoff context.",
    icon: Workflow,
  },
  {
    title: "Check",
    detail: "A coverage and completeness checklist flags whether the feed can support traceability, recall, and export workflows. It is not a readiness score.",
    icon: ScanLine,
  },
  {
    title: "Route",
    detail: "Missing KDEs and lineage breaks become owner-ready fix queue items before persistence.",
    icon: ClipboardCheck,
  },
  {
    title: "Gate",
    detail: "The commit decision separates preflight work from production evidence.",
    icon: GitCommitHorizontal,
  },
];

const engineResults = [
  {
    title: "Flagged for fix",
    detail: "Incomplete or inconsistent supplier rows are surfaced in the fix queue so operators can correct them before treating them as production evidence. Rule blocking is advisory in production today; rejection is not guaranteed.",
    icon: PackageX,
  },
  {
    title: "Tenant-scoped evidence",
    detail: "Allowed records persist with tenant context, provenance, run hashes, and audit history.",
    icon: Lock,
  },
  {
    title: "Export package from stored records",
    detail: "Coverage and completeness checklist results, recall posture, and FDA/retailer export packages are built from records stored for the tenant. RegEngine helps with recordkeeping; it does not certify FDA acceptance or guaranteed compliance.",
    icon: FileOutput,
  },
];

const controls = [
  ["Tenant isolation", "Records are scoped to the authenticated tenant via row-level policies; cross-tenant hardening is in active rollout."],
  ["Provenance", "Evidence commits require traceable source and run context."],
  ["Mode separation", "Preflight work cannot silently become production evidence."],
  ["Hash verification", "Committed evidence carries content hashes so downstream consumers can re-check it independently. Strict downstream verification is rolling out."],
];

const outcomes = [
  { icon: ShieldCheck, title: "Gaps stay visible", body: "Coverage and completeness checklist results, fix counts, sources, and export eligibility stay visible." },
  { icon: Lock, title: "Evidence is gated", body: "Production evidence is designed to require identity, provenance, persistence, and clean mode state. Rule enforcement is currently advisory in production and being promoted to blocking." },
  { icon: FileOutput, title: "Exports are explainable", body: "Export packages come from checked records, not a black-box promise. Regulatory acceptance and retention obligations remain with the operator." },
];

function InflowImpactDiagram() {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-re-border-subtle p-5">
        <p className="font-mono text-label uppercase text-re-text-muted">Inflow affects RegEngine before evidence exists</p>
        <h2 className="mt-3 text-heading text-re-text-primary">
          It turns supplier noise into a commit decision.
        </h2>
      </div>

      <div className="grid lg:grid-cols-[0.86fr_1.14fr]">
        <div className="border-b border-re-border-subtle p-5 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-re-border bg-re-surface-inset text-re-text-tertiary">
              <Database className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <div>
              <p className="font-mono text-label uppercase text-re-text-muted">Raw supplier feed</p>
              <p className="mt-1 text-subheading text-re-text-primary">
                CSV upload or the JSON events API (Live). EPCIS-shaped records are Preview. Other feeds are Beta.
              </p>
            </div>
          </div>

          <ul className="mt-5 grid gap-2">
            {["unmapped columns", "missing KDEs", "broken handoffs", "preflight source mode"].map((label) => (
              <li key={label} className="flex items-center justify-between gap-3 rounded-md border border-re-border-subtle bg-re-surface-inset px-3 py-2">
                <span className="text-ui text-re-text-secondary">{label}</span>
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-tertiary" aria-hidden="true" />
              </li>
            ))}
          </ul>

          <Card variant="inset" padding="compact" className="mt-5">
            <div className="flex items-center gap-2 font-mono text-label uppercase text-re-text-muted">
              <GitPullRequestArrow className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              Inflow Workbench output
            </div>
            <p className="mt-3 text-ui text-re-text-secondary">
              One preflight run containing normalized event candidates, a coverage and completeness checklist, fix queue, and commit gate state.
            </p>
          </Card>
        </div>

        <div className="grid">
          <div className="grid md:grid-cols-4">
            {inflowEffects.map(({ title, detail, icon: Icon }, index) => (
              <article key={title} className="border-b border-r border-re-border-subtle p-4 last:border-r-0">
                <div className="flex items-center justify-between gap-3">
                  <Icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="font-mono text-label tabular-nums text-re-text-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="mt-6 text-subheading text-re-text-primary">{title}</h3>
                <p className="mt-2 text-ui text-re-text-secondary">{detail}</p>
              </article>
            ))}
          </div>

          <div className="grid items-stretch md:grid-cols-[1fr_44px_1fr]">
            <div className="p-5">
              <p className="font-mono text-label uppercase text-re-text-muted">Commit gate says no</p>
              <h3 className="mt-3 text-subheading text-re-text-primary">Fix before evidence</h3>
              <p className="mt-2 text-ui text-re-text-secondary">
                RegEngine keeps failed preflight work in correction mode until the blockers are cleared.
              </p>
            </div>
            <div className="hidden border-x border-re-border-subtle md:grid md:place-items-center">
              <ArrowRight className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            </div>
            <div className="border-t border-re-border-subtle p-5 md:border-t-0">
              <p className="font-mono text-label uppercase text-re-text-muted">Commit gate says yes</p>
              <h3 className="mt-3 text-subheading text-re-text-primary">Persist and prove</h3>
              <p className="mt-2 text-ui text-re-text-secondary">
                RegEngine can promote records that passed the commit gate into tenant-scoped evidence and use that stored evidence for scores and export packages. Enforcement remains advisory unless RULES_ENGINE_ENFORCE is explicitly set and the route opts in.
              </p>
            </div>
          </div>

          <div className="grid border-t border-re-border-subtle md:grid-cols-3">
            {engineResults.map(({ title, detail, icon: Icon }) => (
              <article key={title} className="border-b border-r border-re-border-subtle p-4 last:border-r-0 md:border-b-0">
                <Icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="mt-5 text-subheading text-re-text-primary">{title}</h3>
                <p className="mt-2 text-ui text-re-text-secondary">{detail}</p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function ProductPage() {
  return (
    <div className="re-page min-h-screen">
      <Container width="marketing" className="pb-12 pt-12 md:pb-16 md:pt-16">
        <PageHeader
          size="hero"
          eyebrow="Product"
          title="A workbench for deciding what can become evidence."
          description="RegEngine is built around one simple operating rule: supplier data is useful only after it is mapped, checked, fixed, persisted, and explicitly committed."
          secondaryActions={
            <Button asChild variant="secondary" size="lg">
              <Link href="/security">Verify security</Link>
            </Button>
          }
          className="border-b-0 pb-0"
        />

        <div className="mt-10">
          <InflowImpactDiagram />
        </div>
      </Container>

      <Section width="marketing">
        <div className="grid gap-5 md:grid-cols-2">
          <Card padding="spacious" className="flex flex-col">
            <p className="font-mono text-label uppercase text-re-text-muted">Core loop</p>
            <h2 className="mt-4 font-display text-heading-lg text-re-text-primary">Prepare. Prove. Commit. Export.</h2>
            <p className="mt-4 text-ui text-re-text-secondary">
              Inflow handles the messy outside world. The Engine handles rules, persistence, and gate decisions. The result is an audit path your operations team can explain under pressure.
            </p>
          </Card>
          <Table>
            <TableBody>
              {controls.map(([label, detail]) => (
                <TableRow key={label}>
                  <TableCell className="w-1/3 align-top">
                    <span className="inline-flex items-center gap-2 font-mono text-label uppercase text-re-text-muted">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-tertiary" aria-hidden="true" />
                      {label}
                    </span>
                  </TableCell>
                  <TableCell className="align-top text-re-text-secondary">{detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section width="marketing" className="pb-20">
        <div className="grid gap-5 md:grid-cols-3">
          {outcomes.map(({ icon: Icon, title, body }) => (
            <Card key={title} padding="compact" className="flex flex-col">
              <Icon className="mb-8 h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <h2 className="text-subheading text-re-text-primary">{title}</h2>
              <p className="mt-3 text-ui text-re-text-secondary">{body}</p>
            </Card>
          ))}
        </div>
      </Section>
    </div>
  );
}
