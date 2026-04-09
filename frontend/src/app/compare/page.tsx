import { Metadata } from 'next';
import Link from 'next/link';
import { Check, X } from 'lucide-react';

export const metadata: Metadata = {
  title: 'FSMA 204 Software Comparison | RegEngine vs Competitors',
  description: 'Compare RegEngine with ReposiTrak, FoodLogiQ (Aptean), TraceGains, and FoodReady. Feature matrix for FSMA 204 compliance, KDE validation, API architecture, and implementation speed.',
  keywords: [
    'FSMA 204 software comparison',
    'ReposiTrak alternative',
    'FoodLogiQ alternative',
    'Aptean alternative',
    'TraceGains alternative',
    'FoodReady alternative',
    'food traceability software',
    'FDA food safety',
  ],
  openGraph: {
    title: 'Compare RegEngine vs FSMA 204 Competitors',
    description: 'See how RegEngine compares to ReposiTrak, FoodLogiQ, TraceGains, and FoodReady on critical compliance features.',
    type: 'website',
    url: 'https://regengine.app/compare',
  },
};

interface ComparisonRow {
  feature: string;
  description?: string;
  regEngine: { value: boolean | string; note?: string };
  reposiTrak: { value: boolean | string; note?: string };
  foodLogiQ: { value: boolean | string; note?: string };
  traceGains: { value: boolean | string; note?: string };
  foodReady: { value: boolean | string; note?: string };
}

const comparisonData: ComparisonRow[] = [
  {
    feature: 'FSMA 204 (All 7 CTEs)',
    description: 'Complete support for all 7 Critical Tracking Elements across all products',
    regEngine: { value: true, note: 'Full coverage' },
    reposiTrak: { value: 'partial', note: 'Limited' },
    foodLogiQ: { value: 'partial', note: 'Limited' },
    traceGains: { value: 'partial', note: 'Limited' },
    foodReady: { value: true, note: 'Full coverage' },
  },
  {
    feature: 'KDE Validation',
    description: 'Key Data Element (KDE) validation and enforcement',
    regEngine: { value: true },
    reposiTrak: { value: false },
    foodLogiQ: { value: false },
    traceGains: { value: false },
    foodReady: { value: false },
  },
  {
    feature: '24-Hour FDA Response',
    description: 'Ability to respond to FDA requests within 24 hours',
    regEngine: { value: true },
    reposiTrak: { value: false },
    foodLogiQ: { value: false },
    traceGains: { value: false },
    foodReady: { value: false },
  },
  {
    feature: 'API-First Architecture',
    description: 'Modern, REST/GraphQL API for integrations and automation',
    regEngine: { value: true },
    reposiTrak: { value: false },
    foodLogiQ: { value: false },
    traceGains: { value: false },
    foodReady: { value: false },
  },
  {
    feature: 'Transparent Pricing',
    description: 'Public pricing published on website',
    regEngine: { value: true, note: '$425-639/mo' },
    reposiTrak: { value: false, note: 'Contact Sales' },
    foodLogiQ: { value: false, note: 'Contact Sales' },
    traceGains: { value: false, note: 'Contact Sales' },
    foodReady: { value: true, note: '~$24/seat' },
  },
  {
    feature: 'Implementation Speed',
    description: 'Time from signup to production use',
    regEngine: { value: 'Days', note: 'API ready immediately' },
    reposiTrak: { value: 'Weeks', note: 'Professional services' },
    foodLogiQ: { value: 'Months', note: 'Enterprise onboarding' },
    traceGains: { value: 'Weeks', note: 'Implementation team' },
    foodReady: { value: 'Hours', note: 'Cloud-based' },
  },
  {
    feature: 'Full Data Export',
    description: 'Ability to export all data in standard formats',
    regEngine: { value: true, note: 'CSV, JSON, API' },
    reposiTrak: { value: 'limited', note: 'Restricted' },
    foodLogiQ: { value: 'limited', note: 'Restricted' },
    traceGains: { value: 'limited', note: 'Restricted' },
    foodReady: { value: true, note: 'Standard export' },
  },
  {
    feature: 'Tamper-Evident Audit Trail',
    description: 'Immutable audit logs with cryptographic verification',
    regEngine: { value: true, note: 'SHA-256 hash chain' },
    reposiTrak: { value: false },
    foodLogiQ: { value: false },
    traceGains: { value: false },
    foodReady: { value: false },
  },
];

function FeatureCell({
  value,
  note,
}: {
  value: boolean | string;
  note?: string;
}) {
  if (value === true) {
    return (
      <div className="flex items-center gap-2">
        <Check className="w-5 h-5 text-[var(--re-success)]" />
        {note && <span className="text-sm text-[var(--re-text-secondary)]">{note}</span>}
      </div>
    );
  }
  if (value === false) {
    return (
      <div className="flex items-center gap-2">
        <X className="w-5 h-5 text-[var(--re-error)]" />
        {note && <span className="text-sm text-[var(--re-text-secondary)]">{note}</span>}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <div className="w-5 h-5 rounded bg-[var(--re-surface-light)] flex items-center justify-center">
        <span className="text-xs text-[var(--re-text-secondary)]">◐</span>
      </div>
      {note && <span className="text-sm text-[var(--re-text-secondary)]">{note}</span>}
    </div>
  );
}

export default function ComparePage() {
  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      {/* Hero Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 border-b border-[var(--re-surface-light)]">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl sm:text-5xl font-bold mb-4">
            Compare FSMA 204 Solutions
          </h1>
          <p className="text-xl text-[var(--re-text-secondary)] mb-6 max-w-2xl">
            See how RegEngine stacks up against legacy competitors. Based on publicly available
            information as of April 2026.
          </p>
          <div className="inline-block px-4 py-2 rounded-lg bg-[var(--re-surface-light)] border border-[var(--re-surface-lighter)]">
            <p className="text-sm text-[var(--re-text-secondary)]">
              Compare feature-by-feature on FSMA 204 compliance, architecture, pricing, and
              implementation.
            </p>
          </div>
        </div>
      </section>

      {/* Comparison Table */}
      <section className="py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          {/* Desktop Table */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--re-surface-light)]">
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-text-primary)]">
                    Feature
                  </th>
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-brand)] bg-[var(--re-surface-light)] rounded-t-lg">
                    RegEngine
                  </th>
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-text-primary)]">
                    ReposiTrak
                  </th>
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-text-primary)]">
                    FoodLogiQ (Aptean)
                  </th>
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-text-primary)]">
                    TraceGains
                  </th>
                  <th className="text-left py-4 px-6 font-semibold text-[var(--re-text-primary)]">
                    FoodReady
                  </th>
                </tr>
              </thead>
              <tbody>
                {comparisonData.map((row, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-[var(--re-surface-light)] hover:bg-[var(--re-surface-light)] transition-colors"
                  >
                    <td className="py-6 px-6">
                      <div className="font-semibold text-[var(--re-text-primary)]">
                        {row.feature}
                      </div>
                      {row.description && (
                        <div className="text-sm text-[var(--re-text-secondary)] mt-1">
                          {row.description}
                        </div>
                      )}
                    </td>
                    <td className="py-6 px-6 bg-[var(--re-surface-light)]">
                      <FeatureCell
                        value={row.regEngine.value}
                        note={row.regEngine.note}
                      />
                    </td>
                    <td className="py-6 px-6">
                      <FeatureCell
                        value={row.reposiTrak.value}
                        note={row.reposiTrak.note}
                      />
                    </td>
                    <td className="py-6 px-6">
                      <FeatureCell
                        value={row.foodLogiQ.value}
                        note={row.foodLogiQ.note}
                      />
                    </td>
                    <td className="py-6 px-6">
                      <FeatureCell
                        value={row.traceGains.value}
                        note={row.traceGains.note}
                      />
                    </td>
                    <td className="py-6 px-6">
                      <FeatureCell
                        value={row.foodReady.value}
                        note={row.foodReady.note}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards */}
          <div className="lg:hidden space-y-8">
            {comparisonData.map((row, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-[var(--re-surface-light)] overflow-hidden"
              >
                <div className="bg-[var(--re-surface-light)] p-4 border-b border-[var(--re-surface-light)]">
                  <h3 className="font-semibold text-[var(--re-text-primary)]">
                    {row.feature}
                  </h3>
                  {row.description && (
                    <p className="text-sm text-[var(--re-text-secondary)] mt-2">
                      {row.description}
                    </p>
                  )}
                </div>
                <div className="p-4 space-y-3">
                  <div>
                    <div className="text-xs font-semibold text-[var(--re-brand)] mb-2">
                      RegEngine
                    </div>
                    <div className="text-[var(--re-text-primary)]">
                      <FeatureCell
                        value={row.regEngine.value}
                        note={row.regEngine.note}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--re-text-secondary)] mb-2">
                      ReposiTrak
                    </div>
                    <div className="text-[var(--re-text-primary)]">
                      <FeatureCell
                        value={row.reposiTrak.value}
                        note={row.reposiTrak.note}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--re-text-secondary)] mb-2">
                      FoodLogiQ (Aptean)
                    </div>
                    <div className="text-[var(--re-text-primary)]">
                      <FeatureCell
                        value={row.foodLogiQ.value}
                        note={row.foodLogiQ.note}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--re-text-secondary)] mb-2">
                      TraceGains
                    </div>
                    <div className="text-[var(--re-text-primary)]">
                      <FeatureCell
                        value={row.traceGains.value}
                        note={row.traceGains.note}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--re-text-secondary)] mb-2">
                      FoodReady
                    </div>
                    <div className="text-[var(--re-text-primary)]">
                      <FeatureCell
                        value={row.foodReady.value}
                        note={row.foodReady.note}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Key Differentiators Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-light)] border-t border-b border-[var(--re-surface-lighter)]">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold mb-12">Why RegEngine Leads</h2>

          <div className="grid md:grid-cols-2 gap-8">
            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="flex-shrink-0 mt-1">
                  <Check className="w-6 h-6 text-[var(--re-success)]" />
                </div>
                <div>
                  <h3 className="font-semibold text-[var(--re-text-primary)] mb-2">
                    Built for FSMA 204
                  </h3>
                  <p className="text-[var(--re-text-secondary)]">
                    Purpose-built from day one for full FSMA 204 compliance, not retrofitted to
                    legacy systems. Every feature supports all 7 CTEs and KDE validation.
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="flex-shrink-0 mt-1">
                  <Check className="w-6 h-6 text-[var(--re-success)]" />
                </div>
                <div>
                  <h3 className="font-semibold text-[var(--re-text-primary)] mb-2">
                    API-First, Not UI-First
                  </h3>
                  <p className="text-[var(--re-text-secondary)]">
                    Designed for automation and integration. Integrate with your existing supply
                    chain systems in days, not months.
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="flex-shrink-0 mt-1">
                  <Check className="w-6 h-6 text-[var(--re-success)]" />
                </div>
                <div>
                  <h3 className="font-semibold text-[var(--re-text-primary)] mb-2">
                    Transparent Pricing
                  </h3>
                  <p className="text-[var(--re-text-secondary)]">
                    No hidden costs. Flat rate starts at $425/month. Competitors require custom
                    quotes—often 10x our price.
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="flex-shrink-0 mt-1">
                  <Check className="w-6 h-6 text-[var(--re-success)]" />
                </div>
                <div>
                  <h3 className="font-semibold text-[var(--re-text-primary)] mb-2">
                    Cryptographic Audit Trail
                  </h3>
                  <p className="text-[var(--re-text-secondary)]">
                    SHA-256 hash chain ensures tamper-evident records for FDA inspections and
                    recalls.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Disclaimer Section */}
      <section className="py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="p-4 rounded-lg bg-[var(--re-surface-light)] border border-[var(--re-surface-lighter)]">
            <p className="text-sm text-[var(--re-text-secondary)]">
              <strong>Disclaimer:</strong> This comparison is based on publicly available
              information as of April 2026. Features, pricing, and capabilities may change. We
              recommend verifying current details directly with vendors. RegEngine makes no
              warranties about competitor features or accuracy of third-party claims.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-light)]">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">Ready to Upgrade Your FSMA 204 Stack?</h2>
          <p className="text-lg text-[var(--re-text-secondary)] mb-8 max-w-2xl mx-auto">
            RegEngine gives you production-ready FSMA 204 compliance in days, at a fraction of the
            cost of legacy platforms.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center px-6 py-3 rounded-lg bg-[var(--re-brand)] text-white font-semibold hover:opacity-90 transition-opacity"
            >
              Start Free Trial
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center justify-center px-6 py-3 rounded-lg border border-[var(--re-surface-lighter)] text-[var(--re-text-primary)] font-semibold hover:bg-[var(--re-surface-lighter)] transition-colors"
            >
              Talk to Sales
            </Link>
          </div>

          <p className="text-sm text-[var(--re-text-secondary)] mt-6">
            No credit card required. API key ready immediately.
          </p>
        </div>
      </section>
    </main>
  );
}
