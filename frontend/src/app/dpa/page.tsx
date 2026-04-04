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

export const metadata: Metadata = {
  title: 'Data Processing Agreement | RegEngine',
  description:
    'RegEngine Data Processing Agreement — covering processor obligations, sub-processors, data subject rights, breach notification, and data deletion under GDPR and applicable law.',
  openGraph: {
    title: 'Data Processing Agreement | RegEngine',
    description:
      'RegEngine DPA — GDPR-compliant data processor obligations for food safety traceability data.',
    url: 'https://www.regengine.co/dpa',
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

/* ── Sub-processors ───────────────────────────────────────────── */

const SUBPROCESSORS = [
  {
    name: 'Supabase',
    purpose: 'Authentication, user database (PostgreSQL), and row-level security enforcement',
    location: 'United States',
    link: 'https://supabase.com/privacy',
  },
  {
    name: 'Railway',
    purpose: 'Backend API hosting for compliance, ingestion, NLP, and graph services',
    location: 'United States',
    link: 'https://railway.app/legal/privacy',
  },
  {
    name: 'Vercel',
    purpose: 'Frontend hosting, CDN, edge middleware, and build infrastructure',
    location: 'United States / Global CDN',
    link: 'https://vercel.com/legal/privacy-policy',
  },
  {
    name: 'Stripe',
    purpose: 'Payment processing and subscription management',
    location: 'United States',
    link: 'https://stripe.com/privacy',
  },
  {
    name: 'Resend',
    purpose: 'Transactional email delivery (account, billing, and compliance alerts)',
    location: 'United States',
    link: 'https://resend.com/legal/privacy-policy',
  },
  {
    name: 'Sentry',
    purpose: 'Error monitoring and performance tracking (no personal traceability data)',
    location: 'United States',
    link: 'https://sentry.io/privacy/',
  },
];

/* ── Security measures ────────────────────────────────────────── */

const SECURITY_MEASURES = [
  {
    Icon: Lock,
    title: 'Encryption at Rest',
    text: 'All customer data is encrypted at rest using AES-256. Traceability lot data and compliance records are additionally protected by SHA-256 content hashing for integrity verification.',
  },
  {
    Icon: Globe,
    title: 'Encryption in Transit',
    text: 'All data transmitted between customers, the RegEngine platform, and sub-processors is encrypted using TLS 1.3.',
  },
  {
    Icon: Shield,
    title: 'Tenant Isolation',
    text: 'Customer data is isolated at the database layer using PostgreSQL Row-Level Security policies. No application-level bypass is possible. Each tenant can only access their own traceability and compliance records.',
  },
  {
    Icon: Server,
    title: 'Access Controls',
    text: 'Access to production systems requires multi-factor authentication. Production database credentials are rotated regularly and stored exclusively in secret management systems — never in source code.',
  },
  {
    Icon: Users,
    title: 'Personnel',
    text: "RegEngine personnel with access to customer data are subject to confidentiality obligations. Access is granted on a least-privilege basis and reviewed periodically.",
  },
  {
    Icon: RefreshCw,
    title: 'Incident Response',
    text: 'RegEngine maintains a documented incident response procedure. Security incidents are triaged within 4 hours of detection, with affected customers notified within 72 hours of confirmed personal data breach.',
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
            <ShieldCheck className="h-3 w-3" /> GDPR Compliant
          </span>
        </div>
        <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mb-3 leading-tight tracking-tight">
          Data Processing Agreement
        </h1>
        <p className="text-sm text-[var(--re-text-disabled)] font-mono">
          Effective: April 1, 2026 · Version 1.0
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
          <div className="flex items-start gap-3">
            <FileText className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
            <div>
              <h2 className="text-[15px] font-bold text-[var(--re-text-primary)] mb-1">
                This agreement is incorporated into your RegEngine subscription.
              </h2>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                By using RegEngine to process food traceability data that includes personal
                information — such as supplier contacts, employee records, or data subjects covered
                by GDPR, CCPA, or other applicable privacy law — you (the <strong>Controller</strong>)
                and RegEngine, Inc. (the <strong>Processor</strong>) agree to the terms of this Data
                Processing Agreement (&ldquo;DPA&rdquo;). This DPA supplements and is incorporated
                into the RegEngine Terms of Service.
              </p>
            </div>
          </div>
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
                <p>RegEngine shall:</p>
                <ul className="list-none space-y-2 pl-0">
                  {[
                    'Process Personal Data only on documented instructions from the Controller, unless required to do so by applicable law (in which case RegEngine will notify the Controller before processing, to the extent permitted by law).',
                    'Ensure that personnel authorised to process Personal Data have committed themselves to confidentiality or are under an appropriate statutory obligation of confidentiality.',
                    'Implement the technical and organisational security measures described in Section 6 of this DPA.',
                    'Not engage Sub-Processors without prior written authorisation from the Controller, except as set out in Section 4 of this DPA.',
                    'Assist the Controller, by appropriate technical and organisational measures, in responding to requests from data subjects exercising their rights under Applicable Data Protection Law.',
                    'Assist the Controller in ensuring compliance with security, breach notification, data protection impact assessment, and prior consultation obligations, taking into account the nature of processing and information available to RegEngine.',
                    'Delete or return all Personal Data to the Controller after the end of the provision of Services, as described in Section 8 of this DPA, and delete existing copies unless applicable law requires storage.',
                    'Make available to the Controller all information necessary to demonstrate compliance with the obligations of this DPA and allow for and contribute to audits as described in Section 10.',
                    'Immediately inform the Controller if, in its opinion, an instruction infringes Applicable Data Protection Law.',
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
                The Controller grants RegEngine general authorisation to engage the Sub-Processors
                listed below. RegEngine will notify the Controller at least 30 days before engaging
                a new Sub-Processor or making a material change to an existing Sub-Processor, giving
                the Controller the opportunity to object. RegEngine imposes data protection
                obligations on each Sub-Processor equivalent to those in this DPA.
              </p>
              <div className="rounded-xl border border-[var(--re-surface-border)] overflow-hidden">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)]">
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)]">Sub-Processor</th>
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)]">Purpose</th>
                      <th className="text-left px-4 py-3 font-semibold text-[var(--re-text-secondary)] hidden sm:table-cell">Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SUBPROCESSORS.map((sp, i) => (
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
                        </td>
                        <td className="px-4 py-3 text-[var(--re-text-muted)]">{sp.purpose}</td>
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
                    { Icon: FileText, title: 'Access & Portability', text: 'Export all traceability and compliance records via the API or dashboard at any time.' },
                    { Icon: Trash2, title: 'Erasure', text: 'Request deletion of your account and all associated data. Completed within 30 days.' },
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
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-3 text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                <div className="flex items-center gap-2 mb-1">
                  <Bell className="h-4 w-4 text-amber-500 shrink-0" />
                  <h3 className="text-[14px] font-semibold text-[var(--re-text-primary)]">72-Hour Notification Commitment</h3>
                </div>
                <p>
                  RegEngine will notify the Controller without undue delay — and in any event within
                  72 hours of becoming aware — of a personal data breach affecting Personal Data
                  processed on behalf of the Controller. Notification will be made to the primary
                  account email address on record.
                </p>
                <p>
                  The notification will include, to the extent available at the time: a description of
                  the nature of the breach; the categories and approximate number of data subjects
                  concerned; the categories and approximate number of personal data records concerned;
                  the likely consequences of the breach; and the measures taken or proposed to address
                  the breach.
                </p>
                <p>
                  Where it is not possible to provide complete information at the time of initial
                  notification, RegEngine will provide the information in phases without undue further
                  delay.
                </p>
                <p>
                  RegEngine will document all personal data breaches, including those not required to
                  be notified under applicable law, and will make that documentation available to the
                  Controller on request.
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
                  Upon termination or expiry of the Controller&apos;s subscription, RegEngine will
                  retain the Controller&apos;s data for a 90-day grace period to allow the Controller
                  to retrieve and export their data. After this grace period, all Personal Data and
                  Traceability Data processed on behalf of the Controller will be permanently deleted
                  from RegEngine systems and Sub-Processor systems, except to the extent that
                  applicable law requires continued storage.
                </p>
                <p>
                  The Controller may request deletion at any time by contacting{' '}
                  <a href="mailto:privacy@regengine.co" className="text-[var(--re-brand)] underline hover:opacity-90">
                    privacy@regengine.co
                  </a>
                  . RegEngine will complete the deletion within 30 days of a verified request and
                  provide written confirmation.
                </p>
                <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 flex items-start gap-3 mt-2">
                  <Trash2 className="h-4 w-4 text-[var(--re-brand)] mt-0.5 shrink-0" />
                  <p className="text-[12px] text-[var(--re-text-muted)] leading-relaxed">
                    <strong className="text-[var(--re-text-secondary)]">FSMA 204 Retention Note:</strong>{' '}
                    FDA regulations require covered entities to maintain traceability records for a
                    minimum of 2 years. Customers with ongoing FDA compliance obligations should
                    export and maintain their own archive of traceability records before cancelling
                    their RegEngine subscription, rather than relying on RegEngine as their sole
                    record-keeping system.
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
                  Personal Data to RegEngine in the United States are governed by the EU Standard
                  Contractual Clauses (SCCs) as adopted by the European Commission (Decision
                  2021/914), which are incorporated into this DPA by reference.
                </p>
                <p>
                  For UK data subjects, transfers are made pursuant to the UK International Data
                  Transfer Agreement (IDTA) or the UK Addendum to the EU SCCs.
                </p>
                <p>
                  Where RegEngine engages Sub-Processors located outside the EEA or UK that process
                  EEA or UK personal data, RegEngine ensures appropriate transfer safeguards are in
                  place — such as SCCs or equivalent mechanisms — with each such Sub-Processor.
                </p>
                <p>
                  Controllers who require a countersigned copy of the SCCs or IDTA for their records
                  may request one by emailing{' '}
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
                      RegEngine will make available to the Controller all information reasonably
                      necessary to demonstrate compliance with the obligations set out in this DPA and
                      in Applicable Data Protection Law.
                    </p>
                    <p>
                      The Controller (or a mandated auditor) may conduct an audit of RegEngine&apos;s
                      processing activities no more than once per calendar year, with at least 30 days&apos;
                      written notice, during normal business hours, and at the Controller&apos;s expense.
                      RegEngine may satisfy audit requests by providing relevant third-party certifications
                      (e.g. SOC 2 reports) in lieu of a direct on-site audit where appropriate.
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
                      This DPA is governed by the laws of the State of Delaware, United States, without
                      regard to conflict-of-law principles, except where Applicable Data Protection Law
                      requires otherwise (e.g. GDPR dispute resolution mechanisms for EEA Controllers).
                    </p>
                    <p>
                      RegEngine may update this DPA to reflect changes in applicable law, regulatory
                      guidance, or Sub-Processor arrangements. Material changes will be notified to the
                      Controller at least 30 days before taking effect. Continued use of the Services
                      after the effective date constitutes acceptance of the updated DPA.
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
                      For questions about this DPA, to request a countersigned copy for your records, or
                      to exercise any rights described herein, contact:{' '}
                      <a
                        href="mailto:privacy@regengine.co"
                        className="text-[var(--re-brand)] underline hover:opacity-90"
                      >
                        privacy@regengine.co
                      </a>
                      . Enterprise customers requiring a separately executed DPA with custom addenda
                      should contact us to arrange this.
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
            Enterprise and design-partner customers can request a countersigned DPA, custom data
            retention schedules, or a security review call. You&apos;ll hear from the founder, not
            a legal department.
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
