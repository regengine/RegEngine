import type { Metadata } from "next";
import Link from "next/link";
import { BookCallLink } from "@/components/conversion/BookCallLink";
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
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "About RegEngine | FSMA 204 Compliance Infrastructure",
  description:
    "RegEngine was built by Christopher Sellers (AmeriCorps alum, former Senate staffer, and solo technical founder) to make FSMA 204 compliance accessible to mid-market food companies without six-figure platforms.",
  openGraph: {
    title: "About RegEngine | FSMA 204 Compliance Infrastructure",
    description:
      "RegEngine was built by Christopher Sellers to make FSMA 204 compliance accessible to mid-market food companies without six-figure platforms.",
    url: "https://regengine.co/about",
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
      "Mid-market food companies deserve modern compliance tooling. List price is $999/mo per facility; founding design partner pricing is $499/mo.",
  },
  {
    Icon: Shield,
    title: "Verifiable, not just claimed",
    description:
      "Compliance records are hash-linked once ingested, so any later change is detectable. You can independently verify export-bundle integrity using our published verify_chain.py script.",
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
      "AI accelerates development velocity. Regulatory mappings and validation rules are reviewed by the founder before they ship to production.",
  },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-re-surface-base">
      {/* ── Hero ── */}
      <Container width="marketing" className="pt-12 sm:pt-16">
        <PageHeader
          size="hero"
          eyebrow={<span className="font-mono uppercase">About</span>}
          title={
            <>
              Compliance shouldn&apos;t require{" "}
              <span>a six-figure platform</span>
            </>
          }
          description={
            <>
              RegEngine is FSMA 204 compliance infrastructure built for mid-market
              food companies, by someone who saw the gap from inside government,
              enterprise sales, and the regulatory stack itself.
            </>
          }
          className="border-b-0 pb-0"
        />
      </Container>

      {/* ── Founder Section ── */}
      <Container width="marketing" className="pt-10">
        <Card padding="spacious">
          <div className="flex flex-col items-start gap-6 sm:flex-row">
            {/* Initials Avatar */}
            <span
              aria-hidden="true"
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border border-re-border bg-re-surface-inset font-mono text-heading text-re-text-secondary"
            >
              CS
            </span>

            <div className="flex-1">
              <h2 className="font-display text-heading text-re-text-primary">
                Christopher Sellers
              </h2>
              <p className="mt-1 font-mono text-label uppercase text-re-text-muted">
                Founder
              </p>
              <p className="mt-4 max-w-[68ch] text-ui text-re-text-secondary">
                I built RegEngine because I kept seeing the same pattern: FSMA
                204 compliance tools priced for enterprises, sold through
                six-month procurement cycles, and designed for teams with
                dedicated compliance departments. The companies that actually
                needed help (regional distributors, mid-size processors,
                growing food brands) were stuck choosing between
                spreadsheets and software they couldn&apos;t afford.
              </p>
              <p className="mt-3 max-w-[68ch] text-ui text-re-text-secondary">
                My path here wasn&apos;t typical for a founder. I served in
                AmeriCorps, worked in the U.S. Senate where I watched regulatory
                policy get written, then moved to tech sales where I saw how
                that policy became a compliance burden for the companies it was
                supposed to protect. RegEngine is what happens when you combine
                those perspectives with modern infrastructure.
              </p>
            </div>
          </div>
        </Card>
      </Container>

      {/* ── The Path Here ── */}
      <Section
        width="marketing"
        title="The path here"
        description="Each step shaped how RegEngine approaches compliance differently."
      >
        <div className="grid gap-5 sm:grid-cols-2">
          {TIMELINE.map((step) => (
            <Card key={step.period} padding="compact" className="flex items-start gap-4">
              <step.Icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <div>
                <p className="text-subheading text-re-text-primary">
                  {step.period}
                </p>
                <p className="mt-1 text-ui text-re-text-secondary">
                  {step.description}
                </p>
              </div>
            </Card>
          ))}
        </div>
      </Section>

      {/* ── Solo Founder + AI Transparency ── */}
      <Section width="marketing">
        <Card padding="spacious">
          <div className="mb-4 flex items-start gap-4">
            <Users className="mt-1 h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <div>
              <h2 className="font-display text-heading text-re-text-primary">
                Solo founder, AI-augmented team
              </h2>
              <p className="mt-2 max-w-[68ch] text-ui text-re-text-secondary">
                RegEngine is built by one person leveraging modern AI tooling as
                a development multiplier. This isn&apos;t a limitation; it&apos;s
                a feature.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <Card variant="inset" padding="compact">
              <p className="text-subheading text-re-text-primary">
                Lower overhead
              </p>
              <p className="mt-1 text-ui text-re-text-secondary">
                No bloated org chart means savings passed directly to you.
                Enterprise features at mid-market pricing.
              </p>
            </Card>
            <Card variant="inset" padding="compact">
              <p className="text-subheading text-re-text-primary">
                Faster iteration
              </p>
              <p className="mt-1 text-ui text-re-text-secondary">
                No committee approvals. Early tester feedback is scoped by
                the founder and ships when the change is ready to verify,
                without waiting on a large release committee.
              </p>
            </Card>
            <Card variant="inset" padding="compact">
              <p className="text-subheading text-re-text-primary">
                Human accountability
              </p>
              <p className="mt-1 text-ui text-re-text-secondary">
                AI writes code and drafts documentation. Regulatory rules and
                compliance mappings are reviewed by the founder before they ship
                to production.
              </p>
            </Card>
          </div>
        </Card>
      </Section>

      {/* ── Mission / Principles ── */}
      <Section
        width="marketing"
        title="What we believe"
        description="These principles shape every product decision at RegEngine."
      >
        <div className="grid gap-5 sm:grid-cols-2">
          {PRINCIPLES.map((principle) => (
            <Card key={principle.title} padding="compact">
              <div className="mb-3 flex items-center gap-2.5">
                <principle.Icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="text-subheading text-re-text-primary">
                  {principle.title}
                </h3>
              </div>
              <p className="text-ui text-re-text-secondary">
                {principle.description}
              </p>
            </Card>
          ))}
        </div>
      </Section>

      {/* ── CTA ── */}
      <Section width="marketing" className="pb-20 sm:pb-24">
        <div className="mx-auto max-w-[640px] text-center">
          <h2 className="font-display text-heading-lg text-re-text-primary">
            Ready to talk compliance?
          </h2>
          <p className="mx-auto mt-4 max-w-[48ch] text-body text-re-text-secondary">
            Book a free gap analysis call. We&apos;ll review your current FSMA 204
            posture, identify coverage gaps, and show you exactly what RegEngine
            handles. No commitment required.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <BookCallLink href="/contact" placement="about_page">
                Book a free gap analysis call
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </BookCallLink>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/pricing">View pricing</Link>
            </Button>
          </div>
        </div>
      </Section>
    </div>
  );
}
