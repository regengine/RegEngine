import Link from 'next/link';
import { ListOrdered, Upload } from 'lucide-react';

const ONBOARDING_OPTIONS = [
  {
    title: 'Step-by-Step Setup',
    description:
      "Walk through 8 guided steps - from buyer invite to FDA export. Best if you're setting up for the first time.",
    eta: '~15 minutes',
    cta: 'Start Wizard →',
    href: '/onboarding/supplier-flow',
    icon: ListOrdered,
  },
  {
    title: 'Bulk Data Import',
    description:
      'Already have facilities, TLCs, and events in CSV/XLSX? Upload everything in one pass. Template included.',
    eta: '~5 minutes',
    cta: 'Upload Data →',
    href: '/onboarding/bulk-upload',
    icon: Upload,
  },
];

export default function OnboardingHubPage() {
  return (
    <main className="re-page overflow-x-hidden">
      <div className="re-noise" />

      <section className="relative z-[2] max-w-[1120px] mx-auto px-4 sm:px-6 pt-[84px] pb-[72px]">
        <div className="absolute top-[-90px] left-1/2 -translate-x-1/2 w-[640px] h-[420px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.09)_0%,transparent_72%)] pointer-events-none" />

        <div className="text-center mb-12">
          <h1 className="text-[clamp(32px,5vw,50px)] font-bold tracking-[-0.02em] text-[var(--re-text-primary)] leading-[1.08]">
            Get Started with RegEngine
          </h1>
          <p className="mt-4 text-lg text-[var(--re-text-muted)] max-w-[760px] mx-auto leading-relaxed">
            Choose your onboarding path. Both lead to full FSMA 204 compliance - pick the one that
            fits your data.
          </p>
          <Link
            href="/login"
            className="mt-4 inline-block text-sm text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]"
          >
            Already have an account? Log in
          </Link>
        </div>

        <div className="max-w-[960px] mx-auto grid grid-cols-1 sm:grid-cols-2 gap-5">
          {ONBOARDING_OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <article
                key={option.title}
                className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 transition-colors duration-200 hover:border-[color-mix(in_srgb,var(--re-brand)_30%,transparent)]"
              >
                <div className="h-11 w-11 rounded-lg bg-[var(--re-brand-muted)] flex items-center justify-center mb-5">
                  <Icon className="h-5 w-5 text-[var(--re-brand)]" />
                </div>
                <h2 className="text-2xl font-semibold text-[var(--re-text-primary)] mb-3">{option.title}</h2>
                <p className="text-sm text-[var(--re-text-secondary)] leading-relaxed min-h-[72px]">
                  {option.description}
                </p>
                <div className="mt-7 flex items-center justify-between gap-3">
                  <span className="text-sm text-[var(--re-text-muted)]">{option.eta}</span>
                  <Link
                    href={option.href}
                    className="inline-flex items-center justify-center bg-[var(--re-brand)] text-[var(--re-surface-base)] px-6 py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90"
                  >
                    {option.cta}
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </main>
  );
}
