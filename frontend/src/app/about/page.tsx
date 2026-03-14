import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  Award,
  Code2,
  DollarSign,
  Globe,
  Landmark,
  Mail,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';

export const metadata: Metadata = {
  title: 'About | RegEngine',
  description:
    'Founder-led FSMA 204 compliance infrastructure with an explicit trust surface for customer diligence and implementation readiness.',
  openGraph: {
    title: 'About | RegEngine',
    description:
      'Founder-led FSMA 204 compliance infrastructure with an explicit trust surface for customer diligence and implementation readiness.',
    url: 'https://www.regengine.co/about',
    type: 'website',
  },
};

/* ── data ────────────────────────────────────────────────────────── */

const beliefs = [
  {
    Icon: ShieldCheck,
    title: 'Compliance data should be verifiable, not trusted.',
    body: "Every record is SHA-256 hashed. Run our open verification script — if the hashes don\u2019t match, don\u2019t trust us.",
  },
  {
    Icon: DollarSign,
    title: 'Pricing should be public.',
    body: 'We publish our prices. No "contact sales" gates, no opaque enterprise contracts.',
  },
  {
    Icon: Globe,
    title: 'Regulations are public. Tooling should be accessible.',
    body: 'The CFR is free. We charge for the infrastructure that makes it operationally useful.',
  },
];

const bio = [
  {
    Icon: Landmark,
    text: 'U.S. Senate — served as aide to Senator Jeff Merkley, supporting 150+ constituent engagements statewide.',
  },
  {
    Icon: Award,
    text: 'AmeriCorps NCCC — Team Leader during Hurricane Katrina disaster response. President\u2019s Volunteer Service Award.',
  },
  {
    Icon: Code2,
    text: 'Built every layer of RegEngine — architecture, backend, frontend, compliance logic, and cryptographic verification. Founder-led product with a public trust center rather than enterprise theater.',
  },
];

/* ── page ────────────────────────────────────────────────────────── */

export default function AboutPage() {
  return (
    <div className="re-page">
      {/* ── Hero ──────────────────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10 sm:pb-14">
        <div className="flex items-center gap-2.5 mb-5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] px-3 py-1 text-[11px] font-semibold tracking-wide text-[var(--re-brand)]">
            <Sparkles className="h-3 w-3" /> Founder-Led &bull; FSMA-First
          </span>
        </div>

        <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mb-5 leading-[1.15] tracking-tight">
          Compliance infrastructure, built from the ground up
        </h1>
        <p className="text-base text-[var(--re-text-muted)] leading-[1.7] max-w-[640px]">
          RegEngine turns FSMA 204 requirements into machine-readable,
          cryptographically verifiable records. The product is founder-led,
          FSMA-first, and explicit about where customer process, upstream data
          quality, and off-platform archives still matter.
        </p>
      </section>

      {/* ── Founder bio card ──────────────────────────────────── */}
      <section className="relative z-[2] max-w-[720px] mx-auto px-4 sm:px-6 pb-10 sm:pb-14">
        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 sm:p-8"
          style={{
            borderTop: '3px solid var(--re-brand)',
            boxShadow:
              '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
          }}
        >
          <div className="flex flex-col sm:flex-row gap-4 sm:gap-6 items-start">
            {/* Avatar placeholder */}
            <div className="w-16 h-16 sm:w-[72px] sm:h-[72px] rounded-xl shrink-0 bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center text-2xl sm:text-[28px] font-bold text-[var(--re-brand)]">
              CS
            </div>

            <div className="flex-1 min-w-0">
              <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-0.5">
                Christopher Sellers
              </h2>
              <p className="text-sm font-semibold text-[var(--re-brand)] mb-5">
                Founder &amp; CEO
              </p>

              <div className="flex flex-col gap-4">
                {bio.map((item, i) => (
                  <div key={i} className="group flex gap-3.5 items-start">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                      <item.Icon className="h-4 w-4" />
                    </div>
                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-4 mt-5">
                <a
                  href="https://www.linkedin.com/in/clsellers/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-[13px] text-[var(--re-brand)] font-medium hover:underline"
                >
                  <Users className="h-3.5 w-3.5" /> LinkedIn &rarr;
                </a>
                <a
                  href="mailto:chris@regengine.co"
                  className="inline-flex items-center gap-1.5 text-[13px] text-[var(--re-brand)] font-medium hover:underline"
                >
                  <Mail className="h-3.5 w-3.5" /> chris@regengine.co
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── What we believe — 3-card grid ─────────────────────── */}
      <section className="relative z-[2] max-w-[900px] mx-auto px-4 sm:px-6 pb-10 sm:pb-14">
        <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-6 text-center">
          What we believe
        </h2>

        <div className="grid gap-6 sm:grid-cols-3">
          {beliefs.map((b, i) => (
            <article
              key={i}
              className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 flex flex-col"
              style={{
                borderTop: '3px solid var(--re-brand)',
                boxShadow:
                  '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
              }}
            >
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] group-hover:text-white transition-colors duration-300">
                <b.Icon className="h-5 w-5" />
              </div>
              <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2 leading-snug">
                {b.title}
              </h3>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                {b.body}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* ── Alpha CTA callout ─────────────────────────────────── */}
      <section className="relative z-[2] max-w-[700px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
        <div
          className="rounded-2xl border border-[var(--re-brand)]/20 p-5 sm:p-8 text-center"
          style={{
            background: 'var(--re-brand-muted)',
            boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
          }}
        >
          <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-2">
            Built by a founder who&apos;s been in your shoes
          </h2>
          <p className="text-[15px] text-[var(--re-text-muted)] mb-6 max-w-[520px] mx-auto leading-relaxed">
            Join the Alpha Program for direct access to the team that ships real
            FSMA 204 infrastructure — no sales team, no gatekeepers.
          </p>
          <div className="flex gap-3 justify-center flex-wrap">
            <Link href="/alpha">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-[var(--re-brand)] text-white text-[15px] font-semibold shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                Join Alpha Program <ArrowRight className="h-4 w-4" />
              </button>
            </Link>
            <a href="mailto:chris@regengine.co">
              <button className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)] text-[15px] font-semibold hover:border-[var(--re-brand)]/40 transition-colors">
                <Mail className="h-4 w-4" /> Talk to the founder
              </button>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
