import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Building2,
  Code2,
  Heart,
  Landmark,
  Lightbulb,
  Shield,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

export const metadata: Metadata = {
  title: "About RegEngine | FSMA 204 Compliance Infrastructure",
  description:
    "RegEngine was built by Christopher Sellers — AmeriCorps alum, former Senate staffer, and solo technical founder — to make FSMA 204 compliance accessible to mid-market food companies without six-figure platforms.",
  openGraph: {
    title: "About RegEngine | FSMA 204 Compliance Infrastructure",
    description:
      "RegEngine was built by Christopher Sellers to make FSMA 204 compliance accessible to mid-market food companies without six-figure platforms.",
    url: "https://www.regengine.co/about",
    type: "website",
  },
};

const TIMELINE = [
  {
    Icon: Heart,
    period: "AmeriCorps",
    description:
      "Served communities on the ground. Learned that the people closest to a problem rarely have the tools to solve it.",
  },
  {
    Icon: Landmark,
    period: "U.S. Senate",
    description:
      "Worked on policy that shaped federal regulation. Saw firsthand how compliance burdens fall hardest on mid-sized operators.",
  },
  {
    Icon: Building2,
    period: "Tech Sales",
    description:
      "Sold enterprise software to regulated industries. Watched companies pay six figures for platforms they barely used.",
  },
  {
    Icon: Code2,
    period: "RegEngine",
    description:
      "Combined regulatory knowledge with modern engineering to build what the market actually needed: accessible, verifiable FSMA 204 infrastructure.",
  },
];

const PRINCIPLES = [
  {
    Icon: Target,
    title: "Accessible by default",
    description:
      "Mid-market food companies deserve the same compliance tooling as Fortune 500 operators. RegEngine starts at $425/mo (billed annually), not $50K/year.",
  },
  {
    Icon: Shield,
    title: "Verifiable, not just claimed",
    description:
      "Every compliance record is cryptographically hashed. Audit trails are immutable. You can verify our work independently with open-source tooling.",
  },
  {
    Icon: Lightbulb,
    title: "Transparent operations",
    description:
      "Published pricing. Public trust center. Open security posture. No enterprise sales gates hiding what you actually get.",
  },
  {
    Icon: Sparkles,
    title: "AI-augmented, human-directed",
    description:
      "AI accelerates development velocity. Every regulatory mapping, validation rule, and compliance decision is reviewed and approved by a human.",
  },
];

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* ── Hero ── */}
      <section className="max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-12 sm:pb-16 text-center">
        <p className="text-xs font-mono uppercase tracking-[0.15em] text-[var(--re-brand)] mb-4">
          About
        </p>
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-bold text-[var(--re-text-primary)] leading-tight mb-5">
          Compliance shouldn&apos;t require{" "}
          <span className="text-[var(--re-brand)]">a six-figure platform</span>
        </h1>
        <p className="text-lg text-[var(--re-text-muted)] max-w-xl mx-auto leading-relaxed">
          RegEngine is FSMA 204 compliance infrastructure built for mid-market
          food companies&mdash;by someone who saw the gap from inside government,
          enterprise sales, and the regulatory stack itself.
        </p>
      </section>

      {/* ── Founder Section ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 sm:p-8"
          style={{
            boxShadow:
              "0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)",
          }}
        >
          <div className="flex flex-col sm:flex-row items-start gap-6">
            {/* Initials Avatar */}
            <div className="w-16 h-16 rounded-xl bg-[var(--re-brand)] flex items-center justify-center flex-shrink-0">
              <span className="text-xl font-bold text-white font-display">
                CS
              </span>
            </div>

            <div className="flex-1">
              <h2 className="font-display text-xl font-bold text-[var(--re-text-primary)]">
                Christopher Sellers
              </h2>
              <p className="text-sm font-mono text-[var(--re-brand)] mt-1">
                Founder &amp; Builder
              </p>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-4">
                I built RegEngine because I kept seeing the same pattern: FSMA
                204 compliance tools priced for enterprises, sold through
                six-month procurement cycles, and designed for teams with
                dedicated compliance departments. The companies that actually
                needed help&mdash;regional distributors, mid-size processors,
                growing food brands&mdash;were stuck choosing between
                spreadsheets and software they couldn&apos;t afford.
              </p>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-3">
                My path here wasn&apos;t typical for a founder. I served in
                AmeriCorps, worked in the U.S. Senate where I watched regulatory
                policy get written, then moved to tech sales where I saw how
                that policy became a compliance burden for the companies it was
                supposed to protect. RegEngine is what happens when you combine
                those perspectives with modern infrastructure.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── The Path Here ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          The path here
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          Each step shaped how RegEngine approaches compliance differently.
        </p>

        <div className="grid sm:grid-cols-2 gap-5">
          {TIMELINE.map((step) => (
            <div
              key={step.period}
              className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 flex items-start gap-4"
            >
              <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20 flex-shrink-0">
                <step.Icon className="w-5 h-5 text-[var(--re-brand)]" />
              </div>
              <div>
                <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                  {step.period}
                </p>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-1">
                  {step.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Solo Founder + AI Transparency ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <div
          className="rounded-2xl border-2 border-[var(--re-brand)]/20 p-5 sm:p-8"
          style={{
            background: "var(--re-brand-muted)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
          }}
        >
          <div className="flex items-start gap-4 mb-4">
            <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20 flex-shrink-0">
              <Users className="w-6 h-6 text-[var(--re-brand)]" />
            </div>
            <div>
              <h2 className="font-display text-xl font-bold text-[var(--re-text-primary)]">
                Solo founder, AI-augmented team
              </h2>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-2">
                RegEngine is built by one person leveraging modern AI tooling as
                a development multiplier. This isn&apos;t a limitation&mdash;it&apos;s
                a feature.
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-4 mt-6">
            <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-4">
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                Lower overhead
              </p>
              <p className="text-xs text-[var(--re-text-muted)] mt-1 leading-relaxed">
                No bloated org chart means savings passed directly to customers.
                Enterprise features at mid-market pricing.
              </p>
            </div>
            <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-4">
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                Faster iteration
              </p>
              <p className="text-xs text-[var(--re-text-muted)] mt-1 leading-relaxed">
                No committee approvals. Customer feedback on Monday ships by
                Friday. Regulatory updates deploy in hours, not quarters.
              </p>
            </div>
            <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-4">
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                Human accountability
              </p>
              <p className="text-xs text-[var(--re-text-muted)] mt-1 leading-relaxed">
                AI writes code and drafts documentation. Every regulatory rule,
                compliance mapping, and customer deliverable is human-reviewed.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Mission / Principles ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          What we believe
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          These principles shape every product decision at RegEngine.
        </p>

        <div className="grid sm:grid-cols-2 gap-5">
          {PRINCIPLES.map((principle) => (
            <div
              key={principle.title}
              className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5"
              style={{
                borderTop: "3px solid var(--re-brand)",
                boxShadow:
                  "0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)",
              }}
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20">
                  <principle.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                </div>
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">
                  {principle.title}
                </h3>
              </div>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                {principle.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-20 sm:pb-28 text-center">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3">
          Ready to talk compliance?
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] max-w-md mx-auto mb-8 leading-relaxed">
          Book a free gap analysis call. We&apos;ll review your current FSMA 204
          posture, identify coverage gaps, and show you exactly what RegEngine
          handles&mdash;no commitment required.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--re-brand)] px-6 py-3 text-sm font-semibold text-white hover:bg-[var(--re-brand-dark)] transition-all hover:-translate-y-0.5"
            style={{ boxShadow: "0 4px 16px var(--re-brand-muted)" }}
          >
            Book a free gap analysis call
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--re-surface-border)] px-6 py-3 text-sm font-semibold text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-colors"
          >
            View pricing
          </Link>
        </div>
      </section>
    </main>
  );
}
