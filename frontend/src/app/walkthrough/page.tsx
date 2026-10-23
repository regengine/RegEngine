import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight, AlertTriangle, CheckCircle2, Clock, FileText,
  Package, Search, Shield, ShieldAlert, Upload, XCircle,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
  title: '24-Hour FDA Response Walkthrough | RegEngine',
  description: 'Illustrative step-by-step scenario showing how RegEngine assembles a §1.1455(c) records-on-request package from supplier data.',
  openGraph: {
    title: '24-Hour FDA Response Walkthrough | RegEngine',
    description: 'See exactly what happens when the FDA requests your traceability records.',
    url: 'https://regengine.co/walkthrough',
    type: 'website',
  },
};

const TIMELINE = [
  {
    time: 'T+0:00',
    title: 'FDA request arrives',
    icon: Clock,
    description: 'The FDA sends a records request under 21 CFR 1.1455: "Provide all traceability records for Romaine Lettuce lots R-2026-0312 through R-2026-0318, from farm to retail, within 24 hours."',
    detail: 'This is an illustrative scenario. Under §1.1455(c), the FDA can request records for products on the Food Traceability List, and you must produce a sortable electronic spreadsheet within 24 hours. Real timing varies by completeness of upstream supplier data.',
    color: 'red',
  },
  {
    time: 'T+0:02',
    title: 'Request case created in RegEngine',
    icon: FileText,
    description: 'An operator creates a Request Case, scoping the affected lots, products, and facilities. RegEngine immediately identifies 47 traceability events across 3 suppliers and 5 facilities.',
    detail: 'The system searches canonical records by lot code, product, and facility reference. Events from different suppliers and source systems are already normalized into a common schema.',
    color: 'blue',
  },
  {
    time: 'T+0:05',
    title: 'Data quality gaps surface',
    icon: Search,
    description: 'The rules engine evaluates all 47 events against 36 FSMA 204 validation rules (33 stateless + 3 cross-event). Results: 38 pass, 6 have warnings, 3 have blocking defects.',
    detail: null,
    color: 'amber',
  },
  {
    time: '',
    title: 'Blocking defects found',
    icon: ShieldAlert,
    description: null,
    detail: null,
    color: 'red',
    defects: [
      { lot: 'R-2026-0312', issue: 'Missing required KDE: cooling_date', severity: 'critical' },
      { lot: 'R-2026-0312', issue: 'Identity conflict: "Valley Fresh Farms LLC" vs "Valley Fresh" (>=85% match, unresolved)', severity: 'critical' },
      { lot: 'R-2026-0314', issue: 'Invalid unit_of_measure: "bushels" not in FSMA standard units', severity: 'critical' },
    ],
  },
  {
    time: 'T+0:15',
    title: 'Exception cases created',
    icon: AlertTriangle,
    description: 'Each blocking defect becomes an Exception Case with severity, owner assignment, and remediation guidance. The operator sees exactly what needs fixing and why.',
    detail: 'Exception cases track resolution status, signoffs, and waiver history. Nothing gets swept under the rug: every decision is recorded in the audit trail.',
    color: 'amber',
  },
  {
    time: 'T+1:00',
    title: 'Operator resolves defects',
    icon: CheckCircle2,
    description: 'The cooling_date is recovered from the supplier ERP and added. The identity conflict is merged (confirmed same entity). The invalid unit is corrected from "bushels" to "cases" with a documented reason.',
    detail: 'Each resolution is signed by the operator and timestamped. The rules engine re-evaluates affected events automatically. Stale evaluations are detected and re-run.',
    color: 'emerald',
  },
  {
    time: 'T+1:30',
    title: 'All defects resolved, submission unblocked',
    icon: Shield,
    description: 'The blocking defect check runs again: 0 blocking defects remain. The package can now be assembled.',
    detail: 'RegEngine checks 7 blocker categories: critical rule failures, unresolved exceptions, unevaluated events, missing signoffs, identity ambiguity, stale evaluations, and deadline monitoring.',
    color: 'emerald',
  },
  {
    time: 'T+1:35',
    title: 'FDA response package assembled',
    icon: Package,
    description: 'The operator clicks "Assemble Package." RegEngine generates an immutable, SHA-256 hashed package containing all 47 records, rule evaluations, exception resolutions, and a manifest listing each file\'s hash.',
    detail: null,
    color: 'brand',
    packageDetails: [
      { label: 'Records included', value: '47 of 47' },
      { label: 'Rule evaluations', value: '47 passed' },
      { label: 'Exceptions resolved', value: '3 of 3' },
      { label: 'Package version', value: 'v1 (immutable)' },
      { label: 'SHA-256 manifest hash', value: 'a7c3e9f2...d1b84c' },
      { label: 'Format', value: 'FDA 21 CFR 1.1455 sortable spreadsheet + EPCIS 2.0 JSON-LD' },
    ],
  },
  {
    time: 'T+1:40',
    title: 'Package submitted to FDA',
    icon: CheckCircle2,
    description: 'The package is submitted with a recorded submission method, recipient, and timestamp. The request case moves to "submitted" status. Total time: 1 hour 40 minutes.',
    detail: 'The SHA-256 manifest lets the FDA or your auditor check that the package files still match the manifest packaged with them. The verify_chain.py script can independently re-run that check. It is a self-consistency check, not a signature: the manifest is not signed, so it does not by itself establish who produced the package. Downstream message-bus signature verification is rolling out and not yet strict-mode by default.',
    color: 'emerald',
  },
];

export default function WalkthroughPage() {
  return (
    <div className="min-h-screen bg-re-surface-base">
      {/* Hero */}
      <Container as="section" width="marketing" className="pt-12 sm:pt-16">
        <Badge className="mb-5">
          Product Walkthrough
        </Badge>
        <PageHeader
          size="hero"
          title={
            <>
              The FDA gives you 24&nbsp;hours.<br />
              <span>Here&apos;s how you respond in&nbsp;2.</span>
            </>
          }
          description="A step-by-step walkthrough of an illustrative FDA records-request scenario, from messy supplier data to a hash-manifested response package anyone can re-check."
          className="border-b-0 pb-0"
        />
        <ul className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2">
          <li className="flex items-center gap-1.5 font-mono text-label uppercase text-re-text-muted">
            <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> 24-hour deadline
          </li>
          <li className="flex items-center gap-1.5 font-mono text-label uppercase text-re-text-muted">
            <Package className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> 47 records
          </li>
          <li className="flex items-center gap-1.5 font-mono text-label uppercase text-re-text-muted">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> 3 blocking defects
          </li>
        </ul>
      </Container>

      {/* Timeline */}
      <Container as="section" width="marketing" className="pb-12 pt-12 sm:pb-20">
        <ol className="relative space-y-6 sm:space-y-8">
          {/* Vertical line */}
          <div
            aria-hidden="true"
            className="absolute bottom-0 left-[19px] top-0 w-px bg-re-border-subtle sm:left-[23px]"
          />

          {TIMELINE.map((step, i) => {
            const StepIcon = step.icon;

            return (
              <li key={i} className="relative flex gap-4 sm:gap-5">
                {/* Icon */}
                <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-card text-re-text-tertiary sm:h-12 sm:w-12">
                  <StepIcon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1 pb-2">
                  {step.time && (
                    <span className="font-mono text-label tabular-nums uppercase text-re-text-muted">
                      {step.time}
                    </span>
                  )}
                  <h3 className="mb-2 mt-1 text-heading text-re-text-primary">
                    {step.title}
                  </h3>
                  {step.description && (
                    <p className="mb-3 max-w-[68ch] text-ui text-re-text-secondary">
                      {step.description}
                    </p>
                  )}
                  {step.detail && (
                    <p className="mb-3 max-w-[68ch] text-small text-re-text-tertiary">
                      {step.detail}
                    </p>
                  )}

                  {/* Blocking defects list */}
                  {step.defects && (
                    <Callout tone="danger" className="max-w-[68ch]">
                      <div className="space-y-2">
                        {step.defects.map((d, j) => (
                          <div key={j} className="flex items-start gap-2">
                            <span className="font-mono text-[0.8125rem] text-re-text-primary">{d.lot}</span>
                            <span className="text-ui text-re-text-secondary">{d.issue}</span>
                          </div>
                        ))}
                        <p className="mt-3 border-t border-re-border-subtle pt-2 text-ui font-medium text-re-text-primary">
                          Export build is blocked until defects are resolved or waived
                        </p>
                      </div>
                    </Callout>
                  )}

                  {/* Package details */}
                  {step.packageDetails && (
                    <Card variant="inset" padding="compact" className="max-w-[68ch] space-y-2">
                      {step.packageDetails.map((d) => (
                        <div key={d.label} className="flex items-center justify-between gap-4 text-ui">
                          <span className="text-re-text-secondary">{d.label}</span>
                          <span className="font-mono text-[0.8125rem] text-re-text-primary">{d.value}</span>
                        </div>
                      ))}
                    </Card>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </Container>

      {/* What if blockers aren't resolved */}
      <section className="border-t border-re-border-subtle bg-re-surface-inset py-12 sm:py-16">
        <Container width="marketing">
          <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">You cannot submit if:</h2>
          <p className="mb-6 max-w-[68ch] text-ui text-re-text-secondary">
            RegEngine surfaces these checks at package assembly time. Rule enforcement is configurable per workflow. In production today, rule failures are recorded as exceptions and surfaced in the dashboard rather than blocking ingest.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { rule: 'Required KDEs are missing', example: 'cooling_date, reference_document, tlc_source_reference' },
              { rule: 'Identity conflicts are unresolved', example: 'Supplier name matches >=85% but not confirmed' },
              { rule: 'Events have not been evaluated', example: 'Newly ingested records not yet run through rules engine' },
              { rule: 'Required signoffs are missing', example: 'QA manager approval not recorded' },
              { rule: 'Evaluations are stale', example: 'Event amended after last rule evaluation' },
              { rule: 'Deadline has been breached', example: 'Response window expired (24 hours from request)' },
            ].map((item) => (
              <Card key={item.rule} padding="compact">
                <div className="mb-1 flex items-start gap-2">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="text-subheading text-re-text-primary">{item.rule}</span>
                </div>
                <p className="ml-6 text-ui text-re-text-tertiary">{item.example}</p>
              </Card>
            ))}
          </div>
          <Callout tone="success" className="mt-6">
            <p className="font-medium text-re-text-primary">You can proceed if:</p>
            <p className="mt-1">
              Non-critical warnings remain, issues have been waived with documented reason and approver, or all blocking defects are resolved.
            </p>
          </Callout>
        </Container>
      </section>

      {/* CTA */}
      <Container as="section" width="marketing" className="py-12 sm:py-16">
        <div className="mx-auto max-w-[640px] text-center">
          <h2 className="font-display text-heading-lg text-re-text-primary">This is what RegEngine does.</h2>
          <p className="mx-auto mt-4 max-w-[48ch] text-body text-re-text-secondary">
            It takes messy, inconsistent supplier data and turns it into an FDA-oriented sortable records-on-request workflow for operator review. Nothing more. Nothing less.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <Link href="/pricing">
                Become a Founding Design Partner
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/security">See Security Details</Link>
            </Button>
          </div>
          <p className="mt-6 text-ui text-re-text-secondary">
            See the underlying transformation step by step at{' '}
            <Link href="/proof/transformation" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">/proof/transformation</Link>.
          </p>
        </div>
      </Container>
    </div>
  );
}
