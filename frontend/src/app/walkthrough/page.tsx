import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight, AlertTriangle, CheckCircle2, Clock, FileText,
  Package, Search, Shield, ShieldAlert, Upload, XCircle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
  title: '24-Hour FDA Response Walkthrough | RegEngine',
  description: 'Step-by-step: how RegEngine turns messy supplier data into a defensible FDA response package under deadline.',
  openGraph: {
    title: '24-Hour FDA Response Walkthrough | RegEngine',
    description: 'See exactly what happens when the FDA requests your traceability records.',
    url: 'https://www.regengine.co/walkthrough',
    type: 'website',
  },
};

const TIMELINE = [
  {
    time: 'T+0:00',
    title: 'FDA request arrives',
    icon: Clock,
    description: 'The FDA sends a records request under 21 CFR 1.1455: "Provide all traceability records for Romaine Lettuce lots R-2026-0312 through R-2026-0318, from farm to retail, within 24 hours."',
    detail: 'This is a real scenario. The FDA can request records for any product on the Food Traceability List. You have 24 hours to respond with complete chain-of-custody documentation.',
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
    description: 'The rules engine evaluates all 47 events against 25 FSMA 204 validation rules. Results: 38 pass, 6 have warnings, 3 have blocking defects.',
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
      { lot: 'R-2026-0312', issue: 'Identity conflict: "Valley Fresh Farms LLC" vs "Valley Fresh" — >=85% match, unresolved', severity: 'critical' },
      { lot: 'R-2026-0314', issue: 'Invalid unit_of_measure: "bushels" not in FSMA standard units', severity: 'critical' },
    ],
  },
  {
    time: 'T+0:15',
    title: 'Exception cases created',
    icon: AlertTriangle,
    description: 'Each blocking defect becomes an Exception Case with severity, owner assignment, and remediation guidance. The operator sees exactly what needs fixing and why.',
    detail: 'Exception cases track resolution status, signoffs, and waiver history. Nothing gets swept under the rug — every decision is recorded in the audit trail.',
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
    title: 'All defects resolved — submission unblocked',
    icon: Shield,
    description: 'The blocking defect check runs again: 0 blocking defects remain. The package can now be assembled.',
    detail: 'RegEngine checks 7 blocker categories: critical rule failures, unresolved exceptions, unevaluated events, missing signoffs, identity ambiguity, stale evaluations, and deadline monitoring.',
    color: 'emerald',
  },
  {
    time: 'T+1:35',
    title: 'FDA response package assembled',
    icon: Package,
    description: 'The operator clicks "Assemble Package." RegEngine generates an immutable, SHA-256 hashed package containing all 47 records, rule evaluations, exception resolutions, and a signed manifest.',
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
    detail: 'If the FDA questions any record, the SHA-256 hash chain proves the data hasn\'t been modified since ingestion. The verify_chain.py script can independently confirm integrity.',
    color: 'emerald',
  },
];

export default function WalkthroughPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* Hero */}
      <section className="relative z-[2] max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-8 sm:pb-12">
        <Badge className="mb-5 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand)]/20">
          Product Walkthrough
        </Badge>
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold text-re-text-primary leading-tight mb-5">
          The FDA gives you 24&nbsp;hours.<br />
          <span className="text-re-brand">Here&apos;s how you respond in&nbsp;2.</span>
        </h1>
        <p className="text-lg text-re-text-muted max-w-xl leading-relaxed mb-8">
          A step-by-step walkthrough of a real FDA records request — from messy supplier data to a cryptographically verified response package.
        </p>
        <div className="flex items-center gap-4 text-sm text-re-text-disabled">
          <span className="flex items-center gap-1.5">
            <Clock className="w-4 h-4" /> 24-hour deadline
          </span>
          <span className="flex items-center gap-1.5">
            <Package className="w-4 h-4" /> 47 records
          </span>
          <span className="flex items-center gap-1.5">
            <Shield className="w-4 h-4" /> 3 blocking defects
          </span>
        </div>
      </section>

      {/* Timeline */}
      <section className="relative z-[2] max-w-[800px] mx-auto px-4 sm:px-6 pb-12 sm:pb-20">
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[23px] sm:left-[27px] top-0 bottom-0 w-px bg-[var(--re-surface-border)]" />

          <div className="space-y-6 sm:space-y-8">
            {TIMELINE.map((step, i) => {
              const StepIcon = step.icon;
              const colorMap: Record<string, string> = {
                red: 'border-red-500/30 bg-red-500/10 text-red-400',
                amber: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
                blue: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
                emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
                brand: 'border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 text-[var(--re-brand)]',
              };
              const iconColor = colorMap[step.color] || colorMap.brand;

              return (
                <div key={i} className="relative flex gap-4 sm:gap-5">
                  {/* Icon */}
                  <div className={`w-[48px] h-[48px] sm:w-[56px] sm:h-[56px] rounded-xl border flex items-center justify-center flex-shrink-0 z-10 ${iconColor}`}>
                    <StepIcon className="w-5 h-5 sm:w-6 sm:h-6" />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0 pb-2">
                    {step.time && (
                      <span className="font-mono text-[0.7rem] font-medium text-re-text-disabled tracking-wider">
                        {step.time}
                      </span>
                    )}
                    <h3 className="text-lg sm:text-xl font-bold text-re-text-primary mt-1 mb-2">
                      {step.title}
                    </h3>
                    {step.description && (
                      <p className="text-[0.9rem] text-re-text-muted leading-relaxed mb-3">
                        {step.description}
                      </p>
                    )}
                    {step.detail && (
                      <p className="text-[0.8rem] text-re-text-disabled leading-relaxed mb-3 italic">
                        {step.detail}
                      </p>
                    )}

                    {/* Blocking defects list */}
                    {step.defects && (
                      <div className="rounded-xl border-2 border-red-500/20 bg-red-500/5 p-4 space-y-2">
                        {step.defects.map((d, j) => (
                          <div key={j} className="flex items-start gap-2">
                            <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                            <div>
                              <span className="font-mono text-[0.75rem] font-medium text-red-400">{d.lot}</span>
                              <span className="text-[0.8rem] text-re-text-muted ml-2">{d.issue}</span>
                            </div>
                          </div>
                        ))}
                        <p className="text-[0.75rem] text-red-400 font-semibold mt-3 pt-2 border-t border-red-500/20">
                          SUBMISSION BLOCKED until all defects resolved or waived
                        </p>
                      </div>
                    )}

                    {/* Package details */}
                    {step.packageDetails && (
                      <div className="rounded-xl border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 p-4 space-y-2">
                        {step.packageDetails.map((d) => (
                          <div key={d.label} className="flex items-center justify-between text-[0.8rem]">
                            <span className="text-re-text-muted">{d.label}</span>
                            <span className="font-mono font-medium text-[var(--re-brand)]">{d.value}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* What if blockers aren't resolved */}
      <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[800px] mx-auto py-12 sm:py-16 px-4 sm:px-6">
          <h2 className="text-2xl font-bold text-re-text-primary mb-3">You cannot submit if:</h2>
          <p className="text-sm text-re-text-muted mb-6">
            RegEngine enforces these checks at package assembly time. There is no bypass.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {[
              { rule: 'Required KDEs are missing', example: 'cooling_date, reference_document, tlc_source_reference' },
              { rule: 'Identity conflicts are unresolved', example: 'Supplier name matches >=85% but not confirmed' },
              { rule: 'Events have not been evaluated', example: 'Newly ingested records not yet run through rules engine' },
              { rule: 'Required signoffs are missing', example: 'QA manager approval not recorded' },
              { rule: 'Evaluations are stale', example: 'Event amended after last rule evaluation' },
              { rule: 'Deadline has been breached', example: 'Response window expired (24 hours from request)' },
            ].map((item) => (
              <div key={item.rule} className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
                <div className="flex items-start gap-2 mb-1">
                  <ShieldAlert className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                  <span className="text-[0.85rem] font-medium text-re-text-primary">{item.rule}</span>
                </div>
                <p className="text-[0.75rem] text-re-text-disabled ml-6">{item.example}</p>
              </div>
            ))}
          </div>
          <div className="mt-6 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              <div>
                <span className="text-[0.85rem] font-medium text-re-text-primary">You can proceed if:</span>
                <p className="text-[0.8rem] text-re-text-muted mt-1">
                  Non-critical warnings remain, issues have been waived with documented reason and approver, or all blocking defects are resolved.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-[2] max-w-[700px] mx-auto px-6 py-12 sm:py-16 text-center">
        <h2 className="text-2xl font-bold text-re-text-primary mb-3">This is what RegEngine does.</h2>
        <p className="text-[0.95rem] text-re-text-muted mb-6 max-w-lg mx-auto">
          It takes messy, inconsistent supplier data and turns it into a defensible FDA response under deadline. Nothing more. Nothing less.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link href="/pricing">
            <button className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-3 rounded-xl text-[0.9rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)] hover:-translate-y-0.5 hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)]">
              Join the Founding Cohort
              <ArrowRight className="w-4 h-4" />
            </button>
          </Link>
          <Link href="/security">
            <button className="inline-flex items-center gap-2 border border-[var(--re-surface-border)] text-re-text-secondary px-6 py-3 rounded-xl text-[0.9rem] font-medium transition-all hover:border-[var(--re-brand)]/30">
              See Security Details
            </button>
          </Link>
        </div>
      </section>
    </div>
  );
}
