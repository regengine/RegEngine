import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  Ban,
  Bell,
  ChevronRight,
  Cookie,
  CreditCard,
  Database,
  FileText,
  Globe,
  Hash,
  KeyRound,
  Lock,
  LockKeyhole,
  Mail,
  MonitorSmartphone,
  RefreshCw,
  Server,
  Shield,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserCheck,
  Users,
} from 'lucide-react';

export const metadata: Metadata = {
  title: 'Privacy Policy | RegEngine',
  description:
    'Plain language privacy policy. What RegEngine collects, why, and what we do with your compliance data.',
  openGraph: {
    title: 'Privacy Policy | RegEngine',
    description: 'Plain language privacy policy for FSMA 204 compliance.',
    url: 'https://www.regengine.co/privacy',
    type: 'website',
  },
};

/* ── TOC entries ──────────────────────────────────────────────── */

const TOC = [
  { id: 'collect', label: 'What We Collect' },
  { id: 'use', label: 'How We Use It' },
  { id: 'dont', label: "What We Don't Do" },
  { id: 'storage', label: 'Storage & Security' },
  { id: 'rights', label: 'Your Rights' },
  { id: 'cookies', label: 'Cookies' },
  { id: 'third-party', label: 'Third-Party Services' },
  { id: 'availability', label: 'Service Availability' },
  { id: 'changes', label: 'Policy Changes' },
  { id: 'contact', label: 'Contact' },
];

/* ── data ─────────────────────────────────────────────────────── */

const collectItems = [
  {
    Icon: Users,
    subtitle: 'Account Information',
    text: 'When you create an account, we collect your name, email address, company name, and billing information. We need this to provide you with our services and process payments.',
  },
  {
    Icon: Database,
    subtitle: 'Compliance Data',
    text: 'When you use RegEngine to manage FSMA 204 compliance, we process and store the traceability data you submit — including Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs). This data belongs to you. We store it to provide the service.',
  },
  {
    Icon: MonitorSmartphone,
    subtitle: 'Usage Data',
    text: 'We collect basic analytics: pages visited, features used, API calls made. We use this to improve the product. We do not sell this data to anyone.',
  },
  {
    Icon: ShieldCheck,
    subtitle: 'FTL Checker (Free Tool)',
    text: 'The FTL Coverage Checker does not require an account and does not store your selections. If you submit your email for a gap analysis, we store that email solely to send you the analysis.',
  },
];

const useItems = [
  { Icon: Server, text: 'Providing and maintaining RegEngine services' },
  { Icon: Database, text: 'Processing your compliance data as directed by you' },
  { Icon: FileText, text: 'Generating FDA-ready exports and reports you request' },
  { Icon: Bell, text: 'Sending transactional emails (account, billing, compliance alerts)' },
  { Icon: RefreshCw, text: 'Improving our platform based on aggregate usage patterns' },
  { Icon: Mail, text: 'Responding to your support requests' },
];

const dontItems = [
  'We do not sell your personal data or compliance data to third parties.',
  'We do not use your compliance data to train machine learning models.',
  'We do not share your data with other RegEngine tenants. Row-Level Security enforces tenant isolation at the database level.',
  'We do not serve targeted ads.',
  'We do not share your data with data brokers.',
];

const storageItems = [
  {
    Icon: Globe,
    subtitle: 'Where',
    text: 'Your data is stored in US-based cloud infrastructure with encryption at rest (AES-256) and in transit (TLS 1.3).',
  },
  {
    Icon: Lock,
    subtitle: 'Isolation',
    text: "Each tenant's data is isolated via PostgreSQL Row-Level Security policies. This is enforced at the database layer, not the application layer.",
  },
  {
    Icon: Hash,
    subtitle: 'Integrity',
    text: 'Regulatory facts are cryptographically hashed with SHA-256. You can independently verify data integrity using our open verification tools.',
  },
];

const rightsItems = [
  {
    Icon: FileText,
    subtitle: 'Access & Export',
    text: 'You can export your compliance data through the API and dashboard surfaces available to your plan. We support FDA-oriented export workflows and customer-managed off-platform archiving.',
  },
  {
    Icon: Trash2,
    subtitle: 'Deletion',
    text: 'You can request deletion of your account and all associated data by contacting privacy@regengine.co. We will complete deletion within 30 days.',
  },
  {
    Icon: UserCheck,
    subtitle: 'Correction',
    text: 'You can update your account information at any time through the dashboard.',
  },
  {
    Icon: KeyRound,
    subtitle: 'California Residents (CCPA)',
    text: 'California residents have additional rights under the CCPA, including the right to know what personal information we collect and the right to opt out of data sales. We do not sell personal information.',
  },
];

/* ── page ─────────────────────────────────────────────────────── */

export default function PrivacyPage() {
  return (
    <div className="re-page">
      {/* ── Hero ───────────────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-6">
        <div className="flex items-center gap-2.5 mb-5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] px-3 py-1 text-[11px] font-semibold tracking-wide text-[var(--re-brand)]">
            <Sparkles className="h-3 w-3" /> Privacy by Design
          </span>
        </div>

        <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mb-3 leading-tight tracking-tight">
          Privacy Policy
        </h1>
        <p className="text-sm text-[var(--re-text-disabled)] font-mono">
          Effective: March 11, 2026 · Last updated: March 11, 2026
        </p>
        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-4">
          Related documents:{' '}
          <Link href="/terms" className="text-[var(--re-brand)] underline hover:opacity-90">
            Terms of Service
          </Link>{' '}
          and{' '}
          <Link href="/security" className="text-[var(--re-brand)] underline hover:opacity-90">
            Security
          </Link>
          .
        </p>
      </section>

      {/* ── TL;DR callout ──────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto px-4 sm:px-6 pb-10">
        <div
          className="rounded-2xl border border-[var(--re-brand)]/20 p-6"
          style={{ background: 'var(--re-brand-muted)', boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}
        >
          <div className="flex items-start gap-3">
            <Shield className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
            <div>
              <h2 className="text-[15px] font-bold text-[var(--re-text-primary)] mb-1">
                Plain language. No legalese walls.
              </h2>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                Here&apos;s what we collect, why, and what we do with it. Your compliance data belongs
                to you — always. We enforce tenant isolation at the database layer, hash every
                regulatory fact with SHA-256, and never sell your data to anyone.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Two-column layout: TOC + Content ───────────────── */}
      <section className="relative z-[2] max-w-[1020px] mx-auto px-4 sm:px-6 pb-12">
        <div className="flex gap-6 lg:gap-10">
          {/* Sticky TOC — desktop only */}
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
          <div className="flex-1 min-w-0 max-w-[720px]">
            {/* ── What We Collect ─────────────────────────── */}
            <div id="collect" className="scroll-mt-24 pb-10">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-5">
                What We Collect
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {collectItems.map((item, i) => (
                  <div
                    key={i}
                    className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5"
                    style={{
                      boxShadow: '0 2px 12px rgba(0,0,0,0.06), 0 0 0 1px var(--re-surface-border)',
                    }}
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                      <item.Icon className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                      {item.subtitle}
                    </h3>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* ── How We Use It ───────────────────────────── */}
            <div id="use" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-5">
                How We Use Your Data
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {useItems.map((item, i) => (
                  <div key={i} className="group flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                      <item.Icon className="h-4 w-4" />
                    </div>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed pt-1.5">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* ── What We Don't Do — highlighted callout ──── */}
            <div id="dont" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div
                className="rounded-2xl border-2 border-red-500/20 p-4 sm:p-6"
                style={{ background: 'rgba(239,68,68,0.04)', boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}
              >
                <div className="flex items-center gap-2.5 mb-4">
                  <Ban className="h-5 w-5 text-red-500" />
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)]">
                    What We Don&apos;t Do
                  </h2>
                </div>
                <ul className="flex flex-col gap-2.5">
                  {dontItems.map((item, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <ShieldCheck className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                      <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                        {item}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* ── Data Storage & Security ─────────────────── */}
            <div id="storage" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-5">
                Data Storage &amp; Security
              </h2>
              <div className="grid gap-4 sm:grid-cols-3">
                {storageItems.map((item, i) => (
                  <article
                    key={i}
                    className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5"
                    style={{
                      borderTop: '3px solid var(--re-brand)',
                      boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
                    }}
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                      <item.Icon className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                      {item.subtitle}
                    </h3>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                      {item.text}
                    </p>
                  </article>
                ))}
              </div>
              {/* Retention note */}
              <div className="mt-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 flex items-start gap-3">
                <LockKeyhole className="h-4 w-4 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-0.5">
                    Retention
                  </h3>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    We retain your compliance data for the duration of your subscription plus 90 days.
                    After cancellation, you can request a full data export. Customers with regulatory
                    retention obligations should maintain recurring exports or an external archive
                    rather than relying on an active subscription alone. After the retention period,
                    data is permanently deleted.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Your Rights ─────────────────────────────── */}
            <div id="rights" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <h2 className="text-xl font-bold text-[var(--re-text-primary)] mb-5">
                Your Rights
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {rightsItems.map((item, i) => (
                  <div
                    key={i}
                    className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5"
                    style={{
                      boxShadow: '0 2px 12px rgba(0,0,0,0.06), 0 0 0 1px var(--re-surface-border)',
                    }}
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                      <item.Icon className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                      {item.subtitle}
                    </h3>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Cookies ─────────────────────────────────── */}
            <div id="cookies" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Cookie className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-1">Cookies</h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    We use essential cookies for authentication and session management. We use basic
                    analytics cookies to understand product usage. We do not use third-party
                    advertising cookies. You can disable non-essential cookies in your browser
                    settings.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Third-Party Services ────────────────────── */}
            <div id="third-party" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <CreditCard className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-1">
                    Third-Party Services
                  </h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    We use a limited number of third-party services to operate RegEngine: cloud
                    hosting (data storage and compute), payment processing (Stripe — they have their
                    own privacy policy), and email delivery (transactional emails only). Each service
                    provider is bound by data processing agreements.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Service Availability ────────────────────── */}
            <div id="availability" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <RefreshCw className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-1">
                    Service Availability Notice
                  </h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    RegEngine features and workflows may change as we improve the platform, and
                    access may be modified during staged rollouts or service updates. This Privacy
                    Policy applies throughout those updates and after broader rollout.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Changes to This Policy ──────────────────── */}
            <div id="changes" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Bell className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-1">
                    Changes to This Policy
                  </h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    We&apos;ll notify you of material changes via email at least 30 days before they
                    take effect. Non-material changes (clarifications, formatting) may be made without
                    notice.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Contact ─────────────────────────────────── */}
            <div id="contact" className="scroll-mt-24 pb-10 border-t border-[var(--re-surface-border)] pt-8">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                <Mail className="h-5 w-5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-1">Contact</h2>
                  <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                    Questions about this policy?{' '}
                    <a
                      href="mailto:privacy@regengine.co"
                      className="text-[var(--re-brand)] underline hover:opacity-90"
                    >
                      privacy@regengine.co
                    </a>{' '}
                    — you&apos;ll hear from the founder directly, not a legal department.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Alpha CTA callout ──────────────────────────────── */}
      <section className="relative z-[2] max-w-[700px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
        <div
          className="rounded-2xl border border-[var(--re-brand)]/20 p-5 sm:p-8 text-center"
          style={{
            background: 'var(--re-brand-muted)',
            boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
          }}
        >
          <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-2">
            Your data belongs to you — always
          </h2>
          <p className="text-[15px] text-[var(--re-text-muted)] mb-6 max-w-[520px] mx-auto leading-relaxed">
            Become a Founding Design Partner to see Row-Level Security and Merkle chain verification live in
            your workspace. No strings attached.
          </p>
          <div className="flex gap-3 justify-center flex-wrap">
            <Link href="/alpha">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-[var(--re-brand)] text-white text-[15px] font-semibold shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                Become a Founding Design Partner <ArrowRight className="h-4 w-4" />
              </button>
            </Link>
            <a href="mailto:privacy@regengine.co">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)] text-[15px] font-semibold hover:border-[var(--re-brand)]/40 transition-colors">
                <Mail className="h-4 w-4" /> Contact the founder
              </button>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
