import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  Bell,
  Building2,
  ChevronRight,
  FileText,
  Globe,
  Lock,
  Mail,
  RefreshCw,
  Server,
  Shield,
  ShieldCheck,
  Trash2,
  Users,
} from 'lucide-react';
import { TRUST_SUBPROCESSORS } from '@/lib/trust-subprocessors';

export const metadata: Metadata = {
  title: 'Data Processing Agreement | RegEngine',
  description:
    'RegEngine Data Processing Agreement — covering processor obligations, sub-processors, data subject rights, breach notification, and data deletion under GDPR and applicable law.',
  openGraph: {
    title: 'Data Processing Agreement | RegEngine',
    description:
      'RegEngine DPA — data processor obligations for food safety traceability data.',
    url: 'https://regengine.co/dpa',
    type: 'website',
  },
};

/* ── TOC ──────────────────────────────────────────────────────── */

const TOC = [
  { id: 'definitions', label: 'Definitions' },
  { id: 'roles', label: 'Roles & Scope' },
  { id: 'obligations', label: 'Processor Obligations' },
  { id: 'subprocessors', label: 'Sub-Processors' },
  { id: 'rights', label: 'Data Subject Rights' },
  { id: 'security', label: 'Security Measures' },
  { id: 'breach', label: 'Breach Notification' },
  { id: 'deletion', label: 'Data Deletion & Return' },
  { id: 'transfers', label: 'International Transfers' },
  { id: 'audits', label: 'Audits & Compliance' },
  { id: 'liability', label: 'Liability' },
  { id: 'governing', label: 'Governing Law' },
  { id: 'contact', label: 'Contact' },
];

const DPA_SUMMARY_CARDS = [
  {
    Icon: FileText,
    title: 'Summary only',
    text: 'This page summarizes RegEngine standard data processing terms for food traceability data that may include personal information.',
  },
  {
    Icon: ShieldCheck,
    title: 'Executed terms control',
    text: 'Binding commitments are controlled by the DPA, order form, or negotiated agreement signed by your organization and RegEngine.',
  },
  {
    Icon: Users,
    title: 'Personal data may be included',
    text: 'Supplier contacts, employee identifiers, logistics personnel, or other covered data subjects may appear in traceability workflows.',
  },
];

/* ── Security measures ────────────────────────────────────────── */

const SECURITY_MEASURES = [
  {
    Icon: Lock,
    title: 'Encryption at Rest',
    text: 'Customer data is stored with managed provider encryption at rest. Traceability lot data and compliance records are additionally protected by SHA-256 content hashing for integrity verification where evidence workflows create hash manifests.',
  },
  {
    Icon: Globe,
    title: 'Encryption in Transit',
    text: 'Data transmitted between customers, the RegEngine platform, and sub-processors is encrypted using modern TLS configurations.',
  },
  {
    Icon: Shield,
    title: 'Tenant Isolation',
    text: 'Customer data is isolated using PostgreSQL row-level policies and authenticated tenant context, designed and tested to restrict cross-tenant access on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in active rollout; details available under NDA.',
  },
  {
    Icon: Server,
    title: 'Access Controls',
    text: 'Access to production systems requires multi-factor authentication. Production credentials are stored in secret management systems — never in source control — and rotated on a defined schedule and immediately on any suspicion of exposure.',
  },
  {
    Icon: Users,
    title: 'Personnel',
    text: "Access to customer data is restricted to the founder-operator under confidentiality obligations; access expands only with contractual controls as the team grows.",
  },
  {
    Icon: RefreshCw,
    title: 'Incident Response',
    text: 'RegEngine maintains a documented incident response procedure; security incidents are triaged promptly and affected customers notified without undue delay.',
  },
];

/* ── Page ─────────────────────────────────────────────────────── */

export default function DpaPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">

      {/* ── Hero ───────────────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-6">
        <div className="flex items-center gap-2.5 mb-5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] px-3 py-1 text-[11px] font-semibold tracking-wide text-[var(--re-brand)]">
            <ShieldCheck className="h-3 w-3" /> Data Processing Terms
          </span>
        </div>
        <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mb-3 leading-tight tracking-tight">
          Data Processing Agreement
        </h1>
        <p className="text-sm text-[var(--re-text-disabled)] font-mono">
          Effective: August 2, 2026 · Version 1.2
        </p>
        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-4">
          Related documents:{' '}
          <Link href="/privacy" className="text-[var(--re-brand)] underline hover:opacity-90">
            Privacy Policy
          </Link>
          ,{' '}
          <Link href="/terms" className="text-[var(--re-brand)] underline hover:opacity-90">
            Terms of Service
          </Link>
          , and{' '}
          <Link href="/security" className="text-[var(--re-brand)] underline hover:opacity-90">
            Security
          </Link>
          .
        </p>
      </section>

      {/* ── Summary callout ────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto px-4 sm:px-6 pb-10">
        <div
          className="rounded-2xl border border-[var(--re-brand)]/20 p-6"
          style={{ background: 'var(--re-brand-muted)', boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            {DPA_SUMMARY_CARDS.map(({ Icon, title, text }) => (
              <div key={title} className="rounded-xl border border-[var(--re-brand)]/15 bg-[var(--re-surface-card)] p-4">
                <Icon className="mb-3 h-5 w-5 text-[var(--re-brand)]" />
                <h2 className="text-[13px] font-bold text-[var(--re-text-primary)]">{title}</h2>
                <p className="mt-2 text-[12px] leading-relaxed text-[var(--re-text-muted)]">{text}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm leading-relaxed text-[var(--re-text-muted)]">
            This public page is not a substitute for an executed DPA, order form, or negotiated
            agreement. It is a diligence summary for standard processor obligations, subprocessors,
            data subject rights, incident notification, deletion, transfers, audits, and liability
            boundaries.
          </p>
        </div>
      </section>

      {/* ── Two-column: TOC + Content ──────────────────────── */}
      <section className="relative z-[2] max-w-[1020px] mx-auto px-4 sm:px-6 pb-16">
        <div className="flex gap-6 lg:gap-10">

          {/* Sticky TOC */}
          <nav className="hidden lg:block w-[220px] shrink-0">
            <div className="sticky top-24">
              <p className="text-[11px] font-mono font-medium text-[var(--re-text-disabled)] tracking-widest uppercase mb-3">
                On this page
              </p>
              <ul className="flex flex-col gap-1">
                {TOC.map((t) => (
                  <li key={t.id}>
                    <a
                      href={`#${t.id}`}
                      className="flex items-center gap-1.5 text-[13px] text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors py-1"
                    >
                      <ChevronRight className="h-3 w-3 opacity-40" />
                      {t.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          {/* Main content */}
          <div className="flex-1 min-w-0 max-w-[720px] space-y-0">

            {/* ── 1. Definitions ──────────────────────────── */}
            <div id="definitions" className="scroll-mt-24 pb-10">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                1. Definitions
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Controller&rdquo;</strong>{' '}
                  means the natural or legal person, public authority, agency, or other body that
                  determines the purposes and means of processing personal data — in this context,
                  the RegEngine customer.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Processor&rdquo;</strong>{' '}
                  means RegEngine, Inc., which processes personal data on behalf of the Controller.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Personal Data&rdquo;</strong>{' '}
                  means any information relating to an identified or identifiable natural person,
                  processed by RegEngine on behalf of the Controller in connection with the Services.
                  In the food safety context this may include supplier contact names, employee
                  identifiers on traceability records, and logistics personnel information.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Traceability Data&rdquo;</strong>{' '}
                  means Critical Tracking Events (CTEs), Key Data Elements (KDEs), Traceability Lot
                  Codes (TLCs), and associated supply chain records submitted to RegEngine under
                  FSMA Section 204 compliance workflows.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Services&rdquo;</strong>{' '}
                  means the RegEngine FSMA 204 food traceability compliance platform, including all
                  associated APIs, dashboard surfaces, ingestion pipelines, and export tools.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Sub-Processor&rdquo;</strong>{' '}
                  means any third party engaged by RegEngine to process Personal Data in connection
                  with providing the Services.
                </p>
                <p>
                  <strong className="text-[var(--re-text-secondary)]">&ldquo;Applicable Data Protection Law&rdquo;</strong>{' '}
                  means the EU General Data Protection Regulation (GDPR) 2016/679, the UK GDPR, the
                  California Consumer Privacy Act (CCPA) as amended, and any other data protection
                  legislation applicable to the processing described in this DPA.
                </p>
              </div>
            </div>

            {/* ── 2. Roles & Scope ────────────────────────── */}
            <div id="roles" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                2. Roles &amp; Scope
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>
                  The Controller determines the purposes and means of processing Traceability Data
                  and any Personal Data it submits to the Services. RegEngine acts solely as a
                  Processor: it processes Personal Data only on documented instructions from the
                  Controller and for no other purpose.
                </p>
                <p>
                  This DPA applies to all Personal Data processed by RegEngine on the
                  Controller&apos;s behalf through the Services, including data submitted via the
                  dashboard, API, bulk upload, or any automated ingestion workflow.
                </p>
                <p>
                  RegEngine does not determine the business purposes for which Personal Data is
                  processed. The Controller is responsible for ensuring it has a lawful basis to
                  collect and submit Personal Data to RegEngine, and for the accuracy of that data.
                </p>
              </div>
            </div>

            {/* ── 3. Processor Obligations ────────────────── */}
            <div id="obligations" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                3. Processor Obligations
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>RegEngine&apos;s standard processor commitments are intended to include:</p>
                <ul className="list-none space-y-2 pl-0">
                  {[
                    'Processing Personal Data on documented customer instructions, unless applicable law requires otherwise.',
                    'Requiring personnel authorized to process Personal Data to follow confidentiality obligations.',
                    'Maintaining the technical and organizational security measures described in Section 6, subject to the executed agreement and current deployment posture.',
                    'Using Sub-Processors under the authorization, notice, and objection process in the executed agreement or signed DPA.',
                    'Assisting the Controller, by appropriate technical and organizational measures, in responding to applicable data subject rights requests.',
                    'Assisting the Controller with security, breach notification, data protection impact assessment, and prior consultation obligations, taking into account the nature of processing and information available to RegEngine.',
                    'Returning or scheduling active-system deletion of Personal Data after the end of Services, subject to legal-retention, backup, immutable-log, and executed-agreement limits.',
                    'Providing available documentation reasonably needed to support DPA verification under the confidentiality, scope, and cost controls in the executed agreement.',
                    'Informing the Controller if RegEngine believes an instruction infringes Applicable Data Protection Law, to the extent required and permitted by law.',
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <ShieldCheck className="h-4 w-4 text-[var(--re-brand)] mt-0.5 shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* ── 4. Sub-Processors ───────────────────────── */}
            <div id="subprocessors" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">
                4. Sub-Processors
              </h2>
              <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-5">
                The executed agreement or signed DPA controls subprocessor authorization, notice,
                objection, and termination rights. The list below summarizes current default and
                where-configured processors. Default processors support core platform operations;
                optional processors are used only where the relevant feature, billing flow, analytics
                flow, object storage, or AI extraction workflow is enabled or configured.
              </p>
              <div className="rounded-xl border border-[var(--re-surface-border)] overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)]">
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)]">Sub-Processor</th>
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)]">Use</th>
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)]">Data Processed</th>
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)] hidden sm:table-cell">Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TRUST_SUBPROCESSORS.map((sp, i) => (
                      <tr
                        key={sp.name}
                        className={`border-b border-[var(--re-surface-border)] last:border-0 ${i % 2 === 1 ? 'bg-[var(--re-surface-card)]' : ''}`}
                      >
                        <td className="px-4 py-3 font-medium text-[var(--re-text-primary)] whitespace-nowrap">
                          <a
                            href={sp.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[var(--re-brand)] hover:underline"
                          >
                            {sp.name}
                          </a>
                          <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--re-text-disabled)]">
                            {sp.availabilityLabel}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-[var(--re-text-muted)]">{sp.purpose}</td>
                        <td className="px-4 py-3 text-[var(--re-text-muted)]">{sp.dataProcessed}</td>
                        <td className="px-4 py-3 text-[var(--re-text-muted)] hidden sm:table-cell whitespace-nowrap">{sp.location}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ── 5. Data Subject Rights ──────────────────── */}
            <div id="rights" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                5. Data Subject Rights
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>
                  The Controller is responsible for handling data subject requests (rights of access,
                  rectification, erasure, restriction, portability, and objection) received from
                  individuals whose Personal Data is processed through the Services.
                </p>
                <p>
                  RegEngine will, taking into account the nature of the processing, assist the
                  Controller in fulfilling its obligation to respond to such requests. If RegEngine
                  receives a data subject request directly relating to the Controller&apos;s data,
                  RegEngine will promptly forward that request to the Controller and will not respond
                  to the data subject directly without the Controller&apos;s authorisation, unless
                  required to do so by applicable law.
                </p>
                <div className="grid gap-3 sm:grid-cols-3 mt-4">
                  {[
                    { Icon: FileText, title: 'Access & Portability', text: 'Export records through the API, dashboard, or enabled workflow surfaces available to your plan and agreement.' },
                    { Icon: Trash2, title: 'Erasure', text: 'Request deletion under your executed agreement. Verified requests are scheduled for active-system deletion; provider backups expire on their normal cycles.' },
                    { Icon: Building2, title: 'Rectification', text: 'Update or correct records through the dashboard. API updates are available to all plans.' },
                  ].map(({ Icon, title, text }) => (
                    <div key={title} className="group rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4">
                      <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors">
                        <Icon className="h-4 w-4" />
                      </div>
                      <h3 className="text-[13px] font-semibold text-[var(--re-text-primary)] mb-1">{title}</h3>
                      <p className="text-[12px] text-[var(--re-text-muted)] leading-relaxed">{text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ── 6. Security Measures ────────────────────── */}
            <div id="security" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                6. Technical &amp; Organisational Security Measures
              </h2>
              <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-5">
                RegEngine implements and maintains the following technical and organisational measures
                to protect Personal Data processed on behalf of the Controller. These measures reflect
                the state of the art, the costs of implementation, and the nature, scope, context,
                and purposes of processing, as well as the risk of varying likelihood and severity to
                the rights and freedoms of natural persons.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {SECURITY_MEASURES.map(({ Icon, title, text }) => (
                  <div key={title} className="group rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors">
                      <Icon className="h-4 w-4" />
                    </div>
                    <h3 className="text-[13px] font-semibold text-[var(--re-text-primary)] mb-1">{title}</h3>
                    <p className="text-[12px] text-[var(--re-text-muted)] leading-relaxed">{text}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* ── 7. Breach Notification ──────────────────── */}
            <div id="breach" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                7. Personal Data Breach Notification
              </h2>
              <div className="rounded-xl border border-re-warning/30 bg-re-warning-muted0/5 p-5 space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <div className="flex items-center gap-2 mb-1">
                  <Bell className="h-4 w-4 text-re-warning shrink-0" />
                  <h3 className="text-[14px] font-semibold text-[var(--re-text-primary)]">Incident Notification Process</h3>
                </div>
                <p>
                  RegEngine&apos;s standard incident process is designed to notify affected Controllers
                  without undue delay. Where required by applicable law or agreed in the executed
                  agreement or signed DPA, notification will follow the timeline and recipient
                  process stated there.
                </p>
                <p>
                  Any notification will include, to the extent available and appropriate at the time: a description of
                  the nature of the breach; the categories and approximate number of data subjects
                  concerned; the categories and approximate number of personal data records concerned;
                  the likely consequences of the breach; and the measures taken or proposed to address
                  the breach.
                </p>
                <p>
                  Where it is not possible to provide complete information at the time of initial
                  notification, RegEngine expects to provide reasonable updates as information becomes
                  available, subject to confidentiality, security, legal privilege, and scope limits.
                </p>
                <p>
                  RegEngine may provide reasonable incident summaries to affected Controllers where
                  required or agreed, subject to confidentiality, legal privilege, security, and scope
                  limits.
                </p>
              </div>
            </div>

            {/* ── 8. Data Deletion & Return ───────────────── */}
            <div id="deletion" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                8. Data Deletion &amp; Return
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>
                  Upon termination or expiry of the Controller&apos;s subscription, data return,
                  retention, and deletion windows are controlled by the executed agreement or DPA.
                  RegEngine will make commercially reasonable export assistance available during the
                  applicable return period. After that period, Personal Data and Traceability Data
                  processed on behalf of the Controller are scheduled for deletion from active
                  systems, except to the extent that applicable law, regulatory obligations, dispute
                  preservation, or the executed agreement requires continued storage.
                </p>
                <p>
                  The Controller may request deletion at any time by contacting{' '}
                  <a href="mailto:privacy@regengine.co" className="text-[var(--re-brand)] underline hover:opacity-90">
                    privacy@regengine.co
                  </a>
                  . RegEngine will process verified deletion requests according to the executed
                  agreement. Provider backups, immutable provider logs, and disaster recovery copies
                  expire according to the applicable provider&apos;s normal retention cycle and may not
                  be overwritten immediately.
                </p>
                <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 flex items-start gap-3 mt-2">
                  <Trash2 className="h-4 w-4 text-[var(--re-brand)] mt-0.5 shrink-0" />
                  <p className="text-[12px] text-[var(--re-text-muted)] leading-relaxed">
                    <strong className="text-[var(--re-text-secondary)]">FSMA 204 Retention Note:</strong>{' '}
                    FDA regulations require covered entities to maintain traceability records for a
                    minimum of 2 years. RegEngine helps support those workflows, but customers remain
                    responsible for maintaining any independent archives required by their own legal,
                    operational, or regulator-facing obligations.
                  </p>
                </div>
              </div>
            </div>

            {/* ── 9. International Transfers ──────────────── */}
            <div id="transfers" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-4">
                9. International Data Transfers
              </h2>
              <div className="space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <p>
                  RegEngine primarily processes data in the United States. For Controllers in the
                  European Economic Area (EEA), the United Kingdom, or Switzerland, transfers of
                  Personal Data to RegEngine in the United States are handled through the executed
                  agreement, signed DPA, Standard Contractual Clauses (SCCs), UK Addendum, or another
                  approved transfer mechanism where required.
                </p>
                <p>
                  SCCs or a UK Addendum can be executed as part of contracting where required.
                </p>
                <p>
                  Where required for a customer deployment, RegEngine relies on the transfer mechanism
                  set out in the executed DPA or procurement package, which may include SCCs, a UK
                  Addendum/IDTA, or another approved mechanism, depending on the data flow and
                  Sub-Processor.
                </p>
                <p>
                  Controllers who require transfer documentation for their records may request the
                  current execution package by emailing{' '}
                  <a href="mailto:privacy@regengine.co" className="text-[var(--re-brand)] underline hover:opacity-90">
                    privacy@regengine.co
                  </a>
                  .
                </p>
              </div>
            </div>

            {/* ── 10. Audits & Compliance ─────────────────── */}
            <div id="audits" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Shield className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-2">
                    10. Audits &amp; Compliance Verification
                  </h2>
                  <div className="space-y-2 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    <p>
                  Audit and verification rights are controlled by the executed agreement or signed
                  DPA. RegEngine&apos;s standard diligence process prioritizes written security
                  questionnaires, available policies, control summaries, and completed third-party
                  attestations when available.
                    </p>
                    <p>
                      Direct system, facility, or personnel audits are available only where required by
                      law or expressly agreed in the executed agreement, and remain subject to
                      confidentiality, security, scope, timing, and cost controls. Formal audit reports,
                      penetration-test summaries, or similar artifacts are provided only if completed
                      and available for the requested review tier.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* ── 11. Liability ───────────────────────────── */}
            <div id="liability" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Lock className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-2">
                    11. Liability
                  </h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    Each party&apos;s liability under this DPA is subject to the limitations and
                    exclusions set out in the RegEngine Terms of Service. Nothing in this DPA is
                    intended to limit either party&apos;s liability to data subjects or to supervisory
                    authorities in ways that are not permissible under Applicable Data Protection Law.
                    Where RegEngine is held liable for a data protection violation caused solely by
                    the Controller&apos;s instructions, RegEngine may seek indemnification from the
                    Controller to the extent permitted by law.
                  </p>
                </div>
              </div>
            </div>

            {/* ── 12. Governing Law ───────────────────────── */}
            <div id="governing" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Globe className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-2">
                    12. Governing Law &amp; Amendments
                  </h2>
                  <div className="space-y-2 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    <p>
                      The governing law for any binding data processing terms is the law specified in
                      the executed agreement or signed DPA, except where Applicable Data Protection Law
                      requires otherwise.
                    </p>
                    <p>
                      RegEngine may update this public summary to reflect changes in applicable law,
                      regulatory guidance, or Sub-Processor arrangements. Notice, objection, and
                      acceptance rights for binding DPA changes are controlled by the executed agreement
                      or signed DPA.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* ── 13. Contact ─────────────────────────────── */}
            <div id="contact" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Mail className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-2">
                    13. Contact &amp; Executed Copies
                  </h2>
                  <div className="space-y-2 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    <p>
                      For questions about this public DPA summary, to request an execution package, or
                      to exercise privacy rights, contact:{' '}
                      <a
                        href="mailto:privacy@regengine.co"
                        className="text-[var(--re-brand)] underline hover:opacity-90"
                      >
                        privacy@regengine.co
                      </a>
                      . Customer agreements and DPA redlines should be reviewed by the appropriate
                      business, security, and legal contacts before execution.
                    </p>
                    <p className="font-medium text-[var(--re-text-secondary)]">
                      RegEngine, Inc.<br />
                      Wilmington, Delaware, United States
                    </p>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────────── */}
      <section className="relative z-[2] max-w-[700px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
        <div
          className="rounded-2xl border border-[var(--re-brand)]/20 p-5 sm:p-8 text-center"
          style={{ background: 'var(--re-brand-muted)', boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }}
        >
          <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-2">
            Questions about data processing?
          </h2>
          <p className="text-[15px] text-[var(--re-text-muted)] mb-6 max-w-[520px] mx-auto leading-relaxed">
            Enterprise and design-partner customers can request a DPA execution package, custom data
            retention schedules, or a security review call. Legal terms require appropriate customer
            and RegEngine review before execution.
          </p>
          <div className="flex gap-3 justify-center flex-wrap">
            <a href="mailto:privacy@regengine.co">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-[var(--re-brand)] text-white text-[15px] font-semibold hover:-translate-y-0.5 transition-all">
                <Mail className="h-4 w-4" /> Contact us about data
              </button>
            </a>
            <Link href="/security">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)] text-[15px] font-semibold hover:border-[var(--re-brand)]/40 transition-colors">
                Security overview <ArrowRight className="h-4 w-4" />
              </button>
            </Link>
          </div>
        </div>
      </section>

    </div>
  );
}
