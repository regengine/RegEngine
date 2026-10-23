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
  type LucideIcon,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
  title: 'Privacy Policy | RegEngine',
  description:
    'Plain language privacy policy. What RegEngine collects, why, and what we do with your compliance data.',
  openGraph: {
    title: 'Privacy Policy | RegEngine',
    description: 'Plain language privacy policy for FSMA 204 compliance.',
    url: 'https://regengine.co/privacy',
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
    text: 'When you use RegEngine to manage FSMA 204 compliance, we process and store the traceability data you submit, including Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs). This data belongs to you. We store it to provide the service.',
  },
  {
    Icon: MonitorSmartphone,
    subtitle: 'Usage Data',
    text: 'We collect basic analytics: pages visited, features used, API calls made. We use this to improve the product. We do not sell this data to anyone.',
  },
  {
    Icon: ShieldCheck,
    subtitle: 'FTL Checker (Free Tool)',
    text: 'The FTL Coverage Checker does not require an account and does not store your selections. If you submit your email for follow-up, we use it to review your request and contact you about coverage questions.',
  },
];

const useItems = [
  { Icon: Server, text: 'Providing, maintaining, and securing RegEngine services' },
  { Icon: Database, text: 'Processing your compliance data as directed by you and the applicable agreement' },
  { Icon: FileText, text: 'Generating FDA-oriented exports and reports you request' },
  { Icon: Bell, text: 'Sending transactional emails (account, billing, compliance alerts)' },
  { Icon: RefreshCw, text: 'Improving our platform based on aggregate usage patterns' },
  { Icon: Mail, text: 'Responding to your support requests' },
];

const dontItems = [
  'We do not sell or share your personal data or compliance data as those terms are defined by CCPA/CPRA.',
  'We do not train RegEngine-owned models on your compliance data. Where third-party LLM providers such as OpenAI or Vertex AI are enabled for extraction, those calls run under the applicable provider terms and the executed agreement.',
  'We do not share your data with other RegEngine tenants. PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict cross-tenant access on core PostgreSQL-backed paths; identity-resolution and graph-layer hardening is in active rollout.',
  'We do not serve targeted ads.',
  'We do not share your data with data brokers.',
];

const storageItems = [
  {
    Icon: Globe,
    subtitle: 'Where',
    text: 'RegEngine uses US-default cloud infrastructure with managed-provider encryption at rest and encrypted transport. Provider-specific locations are listed in the DPA.',
  },
  {
    Icon: Lock,
    subtitle: 'Isolation',
    text: "Tenant data is scoped by PostgreSQL row-level policies and authenticated tenant context, designed and tested to restrict cross-tenant access on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in active rollout. See the DPA for the full subprocessor list.",
  },
  {
    Icon: Hash,
    subtitle: 'Integrity',
    text: 'Supported evidence workflows create SHA-256 manifests so exported records can be independently checked using RegEngine verification tools.',
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
    text: 'You can request deletion of your account and associated data by contacting privacy@regengine.co. Timing, retention exceptions, and confirmation steps follow the executed agreement or DPA.',
  },
  {
    Icon: UserCheck,
    subtitle: 'Correction',
    text: 'You can update your account information at any time through the dashboard.',
  },
  {
    Icon: KeyRound,
    subtitle: 'California Residents (CCPA)',
    text: 'California residents have additional rights under the CCPA/CPRA, including the right to know what personal information we collect and the right to opt out of certain sales or sharing. We do not sell or share personal information as defined by CCPA/CPRA.',
  },
];

/* ── page ─────────────────────────────────────────────────────── */

const PROSE_LINK =
  'text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand';

function NoteCard({
  Icon,
  heading,
  children,
}: {
  Icon: LucideIcon;
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="flex items-start gap-3 p-5">
      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
      <div className="min-w-0">
        <h2 className="mb-1 text-heading text-re-text-primary">{heading}</h2>
        {children}
      </div>
    </Card>
  );
}

export default function PrivacyPage() {
  return (
    <div className="re-page min-h-screen">
      {/* ── Hero ───────────────────────────────────────────── */}
      <Container width="prose" className="pb-6 pt-14 sm:pt-20">
        <div className="mb-5 flex items-center gap-2.5">
          <Badge tone="brand">
            <Sparkles className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden="true" /> Privacy by Design
          </Badge>
        </div>

        <PageHeader
          size="hero"
          title="Privacy Policy"
          className="mb-0 border-b-0 pb-0"
        />
        <p className="mt-3 font-mono text-[0.8125rem] text-re-text-tertiary">
          Effective: March 11, 2026 · Last updated: March 11, 2026
        </p>
        <p className="mt-4 text-ui text-re-text-secondary">
          Related documents:{' '}
          <Link href="/terms" className={PROSE_LINK}>
            Terms of Service
          </Link>
          ,{' '}
          <Link href="/dpa" className={PROSE_LINK}>
            Data Processing Agreement
          </Link>
          , and{' '}
          <Link href="/security" className={PROSE_LINK}>
            Security
          </Link>
          .
        </p>
      </Container>

      {/* ── TL;DR callout ──────────────────────────────────── */}
      <Container width="prose" className="pb-10">
        <Callout tone="info" icon={Shield}>
          <h2 className="text-subheading text-re-text-primary">
            Plain language. No legalese walls.
          </h2>
          <p className="mt-1 text-ui text-re-text-secondary">
            Here&apos;s what we collect, why, and what we do with it. Your compliance data belongs
            to you. RegEngine is designed to restrict tenant access at the database layer,
            provide verifiable evidence exports where configured, and don&apos;t sell your data
            (as defined by the CCPA/CPRA).
          </p>
        </Callout>
      </Container>

      {/* ── Two-column layout: TOC + Content ───────────────── */}
      <Container width="docs" className="pb-12">
        <div className="grid gap-6 lg:grid-cols-[200px_minmax(0,720px)] lg:justify-center lg:gap-10">
          {/* Sticky TOC — desktop only */}
          <nav className="hidden lg:block">
            <div className="sticky top-24">
              <p className="mb-3 font-mono text-label uppercase text-re-text-muted">
                On this page
              </p>
              <ul className="flex flex-col gap-1">
                {TOC.map((t) => (
                  <li key={t.id}>
                    <a
                      href={`#${t.id}`}
                      className="flex items-center gap-1.5 py-1 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                      <ChevronRight className="h-3 w-3 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                      {t.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          {/* Main content */}
          <div className="min-w-0">
            {/* ── What We Collect ─────────────────────────── */}
            <div id="collect" className="scroll-mt-24 pb-10">
              <h2 className="mb-5 text-heading text-re-text-primary">
                What We Collect
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {collectItems.map((item, i) => (
                  <Card key={i} className="p-5">
                    <item.Icon className="mb-3 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                    <h3 className="mb-1 text-subheading text-re-text-primary">
                      {item.subtitle}
                    </h3>
                    <p className="text-ui text-re-text-secondary">
                      {item.text}
                    </p>
                  </Card>
                ))}
              </div>
            </div>

            {/* ── How We Use It ───────────────────────────── */}
            <div id="use" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <h2 className="mb-5 text-heading text-re-text-primary">
                How We Use Your Data
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {useItems.map((item, i) => (
                  <Card key={i} className="flex items-start gap-3 p-4">
                    <item.Icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                    <p className="text-ui text-re-text-secondary">
                      {item.text}
                    </p>
                  </Card>
                ))}
              </div>
            </div>

            {/* ── What We Don't Do — highlighted callout ──── */}
            <div id="dont" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <Callout tone="neutral" icon={Ban}>
                <h2 className="mb-4 text-heading text-re-text-primary">
                  What We Don&apos;t Do
                </h2>
                <ul className="flex flex-col gap-2.5">
                  {dontItems.map((item, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                      <p className="text-ui text-re-text-secondary">
                        {item}
                      </p>
                    </li>
                  ))}
                </ul>
              </Callout>
            </div>

            {/* ── Data Storage & Security ─────────────────── */}
            <div id="storage" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <h2 className="mb-5 text-heading text-re-text-primary">
                Data Storage &amp; Security
              </h2>
              <div className="grid gap-4 sm:grid-cols-3">
                {storageItems.map((item, i) => (
                  <article key={i}>
                    <Card className="h-full p-5">
                      <item.Icon className="mb-3 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                      <h3 className="mb-1 text-subheading text-re-text-primary">
                        {item.subtitle}
                      </h3>
                      <p className="text-ui text-re-text-secondary">
                        {item.text}
                      </p>
                    </Card>
                  </article>
                ))}
              </div>
              {/* Retention note */}
              <Card className="mt-4 flex items-start gap-3 p-4">
                <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                <div>
                  <h3 className="mb-0.5 text-subheading text-re-text-primary">
                    Retention
                  </h3>
                  <p className="text-ui text-re-text-secondary">
                    We retain your compliance data for the duration of your subscription and any
                    post-cancellation period defined by your customer agreement. After cancellation,
                    you can request available exports of customer-submitted compliance data, subject
                    to plan, workspace configuration, retention status, and the executed agreement.
                    Customers with regulatory retention obligations should maintain recurring exports
                    or an external archive rather than relying on an active subscription alone. After the applicable
                    retention period, data is scheduled for deletion from active systems; provider
                    backups, immutable logs, and disaster recovery copies expire on their normal
                    cycles, and legal or regulatory holds may require longer retention.
                  </p>
                </div>
              </Card>
            </div>

            {/* ── Your Rights ─────────────────────────────── */}
            <div id="rights" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <h2 className="mb-5 text-heading text-re-text-primary">
                Your Rights
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {rightsItems.map((item, i) => (
                  <Card key={i} className="p-5">
                    <item.Icon className="mb-3 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                    <h3 className="mb-1 text-subheading text-re-text-primary">
                      {item.subtitle}
                    </h3>
                    <p className="text-ui text-re-text-secondary">
                      {item.text}
                    </p>
                  </Card>
                ))}
              </div>
            </div>

            {/* ── Cookies ─────────────────────────────────── */}
            <div id="cookies" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <NoteCard Icon={Cookie} heading="Cookies">
                <p className="text-ui text-re-text-secondary">
                  We use essential cookies for authentication and session management. We use basic
                  analytics cookies to understand product usage. We do not use third-party
                  advertising cookies. You can disable non-essential cookies in your browser
                  settings.
                </p>
              </NoteCard>
            </div>

            {/* ── Third-Party Services ────────────────────── */}
            <div id="third-party" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <NoteCard Icon={CreditCard} heading="Third-Party Services">
                <p className="text-ui text-re-text-secondary">
                  RegEngine uses subprocessors to operate the platform. Default processors support
                  core hosting, database, and request-routing functions; optional processors are used
                  only where the relevant billing flow, analytics flow, email flow, object storage,
                  or AI extraction workflow is enabled or configured. The authoritative public list,
                  including purpose, data processed, region, and availability, is in the{' '}
                  <Link href="/dpa" className={PROSE_LINK}>DPA</Link>. The
                  executed agreement controls notice periods, objections, and any negotiated
                  subprocessor terms.
                </p>
              </NoteCard>
            </div>

            {/* ── Service Availability ────────────────────── */}
            <div id="availability" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <NoteCard Icon={RefreshCw} heading="Service Availability Notice">
                <p className="text-ui text-re-text-secondary">
                  RegEngine features and workflows may change as we improve the platform, and
                  access may be modified during staged rollouts or service updates. This Privacy
                  Policy applies throughout those updates and after broader rollout.
                </p>
              </NoteCard>
            </div>

            {/* ── Changes to This Policy ──────────────────── */}
            <div id="changes" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <NoteCard Icon={Bell} heading="Changes to This Policy">
                <p className="text-ui text-re-text-secondary">
                  We&apos;ll provide reasonable advance notice of material changes by email.
                  Non-material changes (clarifications, formatting) may be made without
                  notice.
                </p>
              </NoteCard>
            </div>

            {/* ── Contact ─────────────────────────────────── */}
            <div id="contact" className="scroll-mt-24 border-t border-re-border-subtle pb-10 pt-8">
              <NoteCard Icon={Mail} heading="Contact">
                <p className="text-ui text-re-text-secondary">
                  Questions about this policy?{' '}
                  <a
                    href="mailto:privacy@regengine.co"
                    className={PROSE_LINK}
                  >
                    privacy@regengine.co
                  </a>. You&apos;ll hear from the founder directly, not a legal department.
                </p>
              </NoteCard>
            </div>
          </div>
        </div>
      </Container>

      {/* ── Alpha CTA callout ──────────────────────────────── */}
      <Container width="prose" className="pb-12 sm:pb-16">
        <Card className="p-5 text-center sm:p-8">
          <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">
            Your data belongs to you, always
          </h2>
          <p className="mx-auto mb-6 max-w-[520px] text-ui text-re-text-secondary">
            Become a Founding Design Partner to review the current tenant-isolation posture and
            evidence verification workflows in your workspace.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <Link href="/contact">
                Become a Founding Design Partner <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <a href="mailto:privacy@regengine.co">
                <Mail aria-hidden="true" strokeWidth={1.75} /> Contact the founder
              </a>
            </Button>
          </div>
        </Card>
      </Container>
    </div>
  );
}
