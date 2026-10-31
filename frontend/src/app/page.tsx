import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { BookCallLink } from "@/components/conversion/BookCallLink";
import { LiveDot } from "@/components/demo-workspace/HueDot";
import { Container } from "@/components/layout/container";
import { HeroWorkbench } from "@/components/marketing/HeroWorkbench";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { capabilities } from "@/lib/capabilities";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "FSMA 204 Recordkeeping Software | RegEngine",
  description:
    "FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
  openGraph: {
    title: "FSMA 204 Recordkeeping Software | RegEngine",
    description:
      "FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 recordkeeping software" }],
  },
};

const ruleStats = [
  {
    value: "24 hrs",
    detail:
      "Time the FDA gives you to produce an electronic sortable spreadsheet under 21 CFR 1.1455(c)(3)(ii), unless it agrees to more.",
  },
  {
    value: "7 CTEs",
    detail:
      "Harvesting, cooling, initial packing, first land-based receiving, shipping, receiving, transformation. Each has its own Key Data Elements.",
  },
  {
    value: "2028",
    detail:
      "The FDA says it will not enforce before July 20, 2028. The requirements did not change, and buyer programs run on their own calendars.",
  },
];

const steps = [
  { label: "Ingest", detail: "CSV upload, or events over the JSON API. EPCIS 2.0 intake is in preview." },
  { label: "Check", detail: "Each record is tested for the CTEs and KDEs its event type requires." },
  { label: "Fix", detail: "Every gap gets a reason, an owner, and a correction link the supplier can answer." },
  {
    label: "Commit",
    detail: "Accepted records enter a hash-chained, append-only ledger. A commit is a record, not a certification.",
    filled: true,
  },
  { label: "Export", detail: "FDA-shaped, buyer-shaped, or internal packets, each with a SHA-256 manifest." },
];

const EYEBROW = "font-mono text-small font-medium uppercase tracking-[0.14em]";
const H2 = "font-display text-heading-lg text-re-text-primary";
const TOOL_CARD =
  "group flex items-center justify-between gap-4 rounded-lg border border-re-border-subtle bg-re-surface-base px-5 py-4 no-underline transition-colors duration-120 hover:border-re-brand motion-reduce:transition-none";

function IngestPathsToday() {
  return (
    <Card padding="compact" className="mt-5 grid gap-5 sm:grid-cols-[auto_1fr_1fr] sm:items-start">
      <p className={cn(EYEBROW, "text-re-text-muted")}>Ingest paths today</p>
      <div>
        <h3 className="text-subheading text-re-text-primary">Live</h3>
        <ul className="mt-2 grid gap-1.5">
          {capabilities.live.map((name) => (
            <li key={name} className="flex items-center gap-2 text-ui text-re-text-secondary">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
              <span>{name}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-subheading text-re-text-primary">Preview</h3>
        <ul className="mt-2 grid gap-1.5">
          {capabilities.preview.map((name) => (
            <li key={name} className="flex items-center justify-between gap-3 text-ui text-re-text-secondary">
              <span>{name}</span>
              <span className="font-mono text-label uppercase text-re-text-muted">Preview</span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

export default function HomePage() {
  return (
    <div className="re-display-outfit min-h-screen bg-re-surface-base text-re-text-primary">
      <Container as="section" width="docs" className="relative overflow-hidden pb-14 pt-12">
        <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-10">
          <div className="min-w-0">
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-re-brand-muted bg-re-brand-muted px-3.5 py-1.5">
              <LiveDot />
              <span className="font-mono text-label font-medium tracking-[0.06em] text-re-brand">
                FSMA 204 · 21 CFR PART 1 SUBPART S
              </span>
            </p>
            <p className="mb-4 max-w-[480px] text-[1.0625rem] leading-relaxed text-re-text-primary">
              <span className="block">
                The FDA can ask for your traceability records on{" "}
                <span className="font-semibold text-re-warning">24 hours&apos; notice</span>.
              </span>
              <span className="block">They come from suppliers, in forty different shapes.</span>
            </p>
            <h1 className="font-display text-display text-re-text-primary [text-wrap:balance]">
              Find the gaps before the FDA does.
            </h1>
            <p className="mt-3.5 max-w-[460px] text-[0.9375rem] leading-relaxed text-re-text-tertiary">
              RegEngine checks each supplier record against the fields the rule requires, routes every gap to an owner,
              and exports the sortable spreadsheet with a hash manifest.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/tools/kde-checker">
                  See the fields your records need
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/demo">Open the demo workspace</Link>
              </Button>
            </div>
          </div>

          <HeroWorkbench />
        </div>
      </Container>

      <section className="border-y border-re-border-subtle bg-re-surface-card">
        <Container width="docs" className="py-16">
          <div className="mb-10 text-center">
            <p className={cn(EYEBROW, "text-re-warning")}>What the rule asks for</p>
            <h2 className={cn(H2, "mx-auto mt-3 max-w-[720px] [text-wrap:balance]")}>
              A sortable spreadsheet, built from records your suppliers keep.
            </h2>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {ruleStats.map((stat) => (
              <div key={stat.value} className="rounded-lg border border-re-border-subtle bg-re-surface-base px-6 py-7">
                <p className="mb-3 font-display text-[2.625rem] font-bold leading-none tracking-[-0.02em] text-re-brand">
                  {stat.value}
                </p>
                <p className="text-ui leading-relaxed text-re-text-tertiary">{stat.detail}</p>
              </div>
            ))}
          </div>
          <IngestPathsToday />
        </Container>
      </section>

      <Container as="section" width="docs" id="how" className="py-20">
        <div className="mb-10">
          <p className={cn(EYEBROW, "text-re-brand")}>How RegEngine works</p>
          <h2 className={cn(H2, "mt-3 max-w-[640px]")}>Five steps. Every record shows which one it is on.</h2>
        </div>
        <ol className="relative grid gap-5 sm:grid-cols-[repeat(auto-fit,minmax(150px,1fr))]">
          <span
            aria-hidden="true"
            className="absolute left-3.5 right-[calc(20%-44px)] top-3.5 hidden border-t border-dashed border-re-border-subtle sm:block"
          />
          {steps.map((step, index) => (
            <li key={step.label} className="relative">
              <span
                className={cn(
                  "mb-4 flex h-7 w-7 items-center justify-center rounded-full border border-re-brand font-mono text-label font-semibold",
                  step.filled ? "bg-re-brand text-re-brand-foreground" : "bg-re-surface-base text-re-brand",
                )}
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="font-display text-heading text-re-text-primary">{step.label}</h3>
              <p className="mt-2 text-ui leading-relaxed text-re-text-tertiary">{step.detail}</p>
            </li>
          ))}
        </ol>
      </Container>

      <section id="tools" className="border-t border-re-border-subtle bg-re-surface-card">
        <Container width="docs" className="py-20">
          <div className="grid items-start gap-10 md:grid-cols-2">
            <div>
              <p className={cn(EYEBROW, "mb-3 text-re-brand")}>Free tools · no signup required</p>
              <h2 className={cn(H2, "mb-4")}>Start with the records you already have.</h2>
              <p className="max-w-[440px] text-body text-re-text-tertiary">
                Three ways in. None needs an account, and nothing you paste is stored.
              </p>
            </div>
            <div className="flex flex-col gap-3.5">
              <Link href="/tools/kde-checker" className={TOOL_CARD}>
                <span>
                  <span className="mb-1 block text-subheading text-re-text-primary">See the fields your records need</span>
                  <span className="block text-[0.8125rem] text-re-text-tertiary">
                    Pick a food on the FTL and an event. Get the fields the record needs. Print or download.
                  </span>
                </span>
                <span aria-hidden="true" className="text-heading text-re-brand">→</span>
              </Link>
              <Link href="/verify" className={TOOL_CARD}>
                <span>
                  <span className="mb-1 block text-subheading text-re-text-primary">Verify an evidence bundle</span>
                  <span className="block text-[0.8125rem] text-re-text-tertiary">
                    Download <span className="font-mono">verify_chain.py</span> and check a bundle&apos;s hashes on your own machine.
                  </span>
                </span>
                <span aria-hidden="true" className="text-heading text-re-brand">→</span>
              </Link>
              <BookCallLink href="/contact" placement="home_free_tools" className={TOOL_CARD}>
                <span>
                  <span className="mb-1 block text-subheading text-re-text-primary">Book a 30-min call</span>
                  <span className="block text-[0.8125rem] text-re-text-tertiary">
                    Thirty minutes with the founder. Bring one supplier file.
                  </span>
                </span>
                <span aria-hidden="true" className="text-heading text-re-brand">→</span>
              </BookCallLink>
            </div>
          </div>
        </Container>
      </section>

      <Container as="section" width="docs" className="pb-12 pt-10">
        <p className="max-w-[960px] text-small leading-relaxed text-re-text-muted">
          RegEngine does not imply FDA endorsement or certification, is not a readiness score, does not claim that any
          workspace meets the 24-hour request, is not a recall clock product, shows no live customer metrics, and is not
          legal advice. Buyer programs are separate from the FDA; confirm them with your buyer.{" "}
          <span>Live today: {capabilities.live.join(" and ")}.</span>{" "}
          <span>In preview: EPCIS 2.0 intake and export.</span>
        </p>
      </Container>
    </div>
  );
}
