import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle, Clock, FileSpreadsheet, Shield, Upload, Users, Truck, Leaf, Anchor } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "FSMA 204 Compliance Guide: What Your Farm Needs to Know | RegEngine",
  description:
    "Plain-English guide to the FDA Food Traceability Rule. Learn what FSMA 204 requires, whether your products are covered, and how to get compliant. No developer needed.",
  openGraph: {
    title: 'FSMA 204 Compliance Guide: What Your Farm Needs to Know',
    description: 'Plain-English guide to the FDA Food Traceability Rule: what it requires, whether your products are covered, and how to comply.',
    url: 'https://regengine.co/fsma-204',
    type: 'article',
  },
};

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const FTL_EXAMPLES = [
  { category: "Leafy Greens", examples: "Romaine, spinach, spring mix, kale" },
  { category: "Fruits", examples: "Tomatoes, peppers, melons, berries" },
  { category: "Fresh Herbs", examples: "Cilantro, basil, parsley" },
  { category: "Seafood", examples: "Finfish, crustaceans, mollusks" },
  { category: "Shell Eggs", examples: "Shell eggs (per FDA FTL definition)" },
  { category: "Nut Butters", examples: "Peanut butter, almond butter" },
  { category: "Cheeses", examples: "Cheeses other than hard cheese (per FTL)" },
  { category: "Ready-to-Eat Deli Salads", examples: "RTE deli salads (per FTL)" },
];
const CTES_PLAIN = [
  {
    name: "Harvesting",
    icon: Leaf,
    who: "Farms & growers",
    what: "Record when and where you harvested, the lot code, and what product it is.",
  },
  {
    name: "Cooling",
    icon: Clock,
    who: "Farms & coolers",
    what: "Record when the product was cooled after harvest, where, and under what lot code.",
  },
  {
    name: "Initial Packing",
    icon: FileSpreadsheet,
    who: "Packhouses",
    what: "Record what was packed, when, the lot code, and the quantity.",
  },
  {
    name: "First Land-Based Receiving",
    icon: Anchor,
    who: "Receivers of seafood from a fishing vessel",
    what: "Under §1.1335, record when seafood was received from a fishing vessel, the lot code, the harvest and landing location, and the receiving facility. This is distinct from generic imported-food entry.",
  },
  {
    name: "Shipping",
    icon: Truck,
    who: "Anyone sending product",
    what: "Record who shipped, who received, the lot code, carrier, and date.",
  },
  {
    name: "Receiving",
    icon: Upload,
    who: "Anyone receiving product",
    what: "Record what arrived, from where, the lot code, quantity, and date.",
  },
  {
    name: "Transformation",
    icon: Users,
    who: "Processors",
    what: "Record what went in (input lots) and what came out (new lot), with dates and location.",
  },
];
const STEPS = [
  {
    num: "1",
    title: "Check your products",
    desc: "Use our free FTL Checker to see which of your products are on the FDA Food Traceability List. Takes 30 seconds.",
    cta: { label: "FTL Checker", href: "/tools/ftl-checker" },
  },
  {
    num: "2",
    title: "Upload your data",
    desc: "Download our CSV or Excel template, fill in your lot codes, locations, and dates. Upload it to RegEngine. No code, no API, just a spreadsheet.",
    cta: { label: "Download Templates", href: "/onboarding/bulk-upload" },
  },
  {
    num: "3",
    title: "RegEngine maps your events",
    desc: "We map your data to the 7 Critical Tracking Events defined in the FSMA 204 rule: harvesting, cooling, initial packing, first land-based receiving, shipping, receiving, and transformation. You only record the events that occur at your operation. The dashboard shows what’s covered and what’s missing.",
    cta: null,
  },
  {
    num: "4",
    title: "Be ready when they ask",
    desc: "When the FDA or a retailer requests traceability records, RegEngine produces a sortable electronic spreadsheet structured to FDA's §1.1455 format, populated from the lot codes, dates, and locations you've uploaded. Compliance remains your operation's legal responsibility.",
    cta: null,
  },
];

const KEY_FACTS = [
  { icon: Clock, text: "24 hours to respond to an FDA request" },
  { icon: Shield, text: "Applies to all foods on the FTL" },
  { icon: CheckCircle, text: "FDA enforcement not before July 20, 2028" },
];

const FAQS = [
  {
    q: "I’m a small farm. Does this really apply to me?",
    a: "If you grow, harvest, cool, pack, or ship any food on the FDA Food Traceability List, yes. There are limited exemptions for farms that sell directly to consumers, but if you sell to a distributor, retailer, or restaurant, you’re likely covered.",
  },
  {
    q: "I don’t have a developer or IT person. Can I still use RegEngine?",
    a: "Yes. You can upload your data using our CSV or Excel templates, with no code required. Download the template, fill in your lot codes and dates, and upload. RegEngine handles the rest.",
  },
  {
    q: "What if I already track this in spreadsheets?",
    a: "That’s a great start. The challenge is that the FDA requires a specific format and the ability to trace lots forward and backward through your supply chain. RegEngine takes your existing data and organizes it into the structure the FDA expects.",
  },
  {
    q: "How is this different from what Walmart already asks for?",
    a: "Major retailers have their own traceability requirements and supplier timelines. If you already supply traceability data to a retailer, you’re partially prepared. RegEngine helps you produce records structured to meet retailer schemas and FDA’s §1.1455 sortable-spreadsheet format from one system.",
  },
  {
    q: "What are the risks of missing traceability records?",
    a: "FDA enforcement under §1.1455 focuses on producing the required records on request. Beyond direct enforcement, major retailers may drop non-compliant suppliers. The bigger risk for most farms is losing a key retail customer over missing traceability data.",
  },
  {
    q: "How much does this cost?",
    a: "We have plans designed for small farms and growers. Start with a free readiness assessment to see where you stand, then we’ll recommend the right plan.",
  },
];

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function FSMA204BusinessGuidePage() {
  return (
    <div className="bg-re-surface-base">
      {/* - HERO - */}
      <Container width="marketing" className="pt-12 sm:pt-16">
        <PageHeader
          size="hero"
          eyebrow="FSMA 204 Compliance Guide"
          title="The FDA food traceability rule, in plain English."
          description={
            <>
              <span className="block">
                If you grow, pack, ship, or sell food on the FDA&apos;s Food Traceability List, FSMA 204 applies to you. Here&apos;s what it requires, whether you&apos;re a 50-acre farm or a national distributor.
              </span>
              <span className="mt-3 block text-small text-re-text-muted">
                No technical background needed. No jargon.
              </span>
            </>
          }
          primaryAction={
            <Button asChild size="lg">
              <Link href="/tools/ftl-checker">
                Check If Your Products Are Covered
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
          }
          secondaryActions={
            <Button asChild variant="secondary" size="lg">
              <Link href="#how-to-comply">How to comply</Link>
            </Button>
          }
          className="border-b-0 pb-0"
        />

        {/* - KEY FACTS STRIP - */}
        <ul className="mt-10 flex flex-col divide-y divide-re-border-subtle border-y border-re-border-subtle sm:flex-row sm:divide-x sm:divide-y-0">
          {KEY_FACTS.map((fact) => (
            <li key={fact.text} className="flex flex-1 items-center gap-3 py-4 sm:px-5 sm:first:pl-0 sm:last:pr-0">
              <fact.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <span className="text-ui text-re-text-secondary">{fact.text}</span>
            </li>
          ))}
        </ul>
      </Container>

      {/* - WHAT IS FSMA 204 - */}
      <Section width="marketing" flush title="What is FSMA 204?">
        <div className="max-w-[68ch] space-y-4 text-body text-re-text-secondary">
          <p>
            The FDA&apos;s Food Safety Modernization Act Section 204 (commonly called &ldquo;FSMA 204&rdquo; or the &ldquo;Food Traceability Rule&rdquo;) requires anyone who grows, receives, ships, or transforms certain high-risk foods to keep detailed traceability records.
          </p>
          <p>
            The goal is simple: when a foodborne illness outbreak happens, FDA can request your traceability records and you must produce a sortable electronic spreadsheet within <strong className="font-medium text-re-text-primary">24 hours</strong>. Before this rule, that process could take weeks.
          </p>
          <p>
            The rule was finalized in 2022. The compliance date under the rule remains January 20, 2026 (87 FR 70910). The 30-month extension is only proposed (90 FR 38084). <strong className="font-medium text-re-text-primary">FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.</strong> The requirements themselves have not changed.
          </p>
        </div>

        {/* Enforcement callout */}
        <Callout tone="warning" className="mt-8 max-w-[68ch]">
          <p className="font-medium text-re-text-primary">The compliance date and enforcement timing are distinct.</p>
          <p className="mt-1">
            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Major retailers have published supplier traceability programs with their own timelines. If you sell to a major retailer, check your supplier portal: your supplier deadline may already have passed.
          </p>
        </Callout>
      </Section>

      {/* - ARE YOUR PRODUCTS COVERED? - */}
      <Section
        width="marketing"
        eyebrow="The Food Traceability List (FTL)"
        title="Are your products covered?"
        description="FDA&apos;s Food Traceability List identifies covered foods and certain foods containing listed ingredients in the same form. Examples are below; verify each product against FDA&apos;s current FTL and applicable exemptions."
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FTL_EXAMPLES.map((item) => (
            <Card key={item.category} variant="inset" padding="compact">
              <p className="text-subheading text-re-text-primary">{item.category}</p>
              <p className="mt-1 text-ui text-re-text-tertiary">{item.examples}</p>
            </Card>
          ))}
        </div>

        <p className="mt-8 text-ui text-re-text-muted">
          Not sure if your specific products are on the list?
        </p>
        <div className="mt-4">
          <Button asChild size="lg">
            <Link href="/tools/ftl-checker">
              Free FTL Checker (takes 30 seconds)
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </Section>

      {/* - WHAT YOU HAVE TO RECORD - */}
      <Section
        width="marketing"
        eyebrow="What the FDA requires"
        title="Seven events you need to track."
        description={<>FSMA 204 calls these &ldquo;Critical Tracking Events&rdquo; (CTEs). Each one has specific data points (called KDEs) you must record. Here&apos;s what they mean in practice:</>}
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CTES_PLAIN.map((cte) => (
            <Card key={cte.name} padding="compact">
              <div className="flex items-center gap-2.5">
                <cte.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="text-subheading text-re-text-primary">{cte.name}</h3>
              </div>
              <p className="mt-2 font-mono text-label uppercase text-re-text-muted">{cte.who}</p>
              <p className="mt-2 text-ui text-re-text-secondary">{cte.what}</p>
            </Card>
          ))}
        </div>

        <Card padding="compact" className="mt-8 max-w-[68ch]">
          <p className="text-subheading text-re-text-primary">Which events apply to you?</p>
          <p className="mt-2 text-ui text-re-text-secondary">
            Most farms need to record <strong className="font-medium text-re-text-primary">harvesting, cooling, packing, and shipping</strong>. Distributors typically handle receiving and shipping. Processors handle receiving and transformation. Importers must also record <strong className="font-medium text-re-text-primary">first land-based receiving</strong>. You only record the events that happen at your facility.
          </p>
        </Card>
      </Section>

      {/* - THE 24-HOUR RULE - */}
      <Section
        width="marketing"
        eyebrow="The 24-hour rule"
        title="When the FDA calls, you have one day."
        description={<>During a recall or outbreak investigation, the FDA can request your traceability records. You must provide them in an <strong className="font-medium text-re-text-primary">electronic, sortable format</strong> (like a spreadsheet) within <strong className="font-medium text-re-text-primary">24 hours</strong>.</>}
      >
        <div className="grid max-w-[68ch] grid-cols-1 gap-4 md:grid-cols-2">
          <Card variant="inset" padding="compact">
            <p className="font-mono text-label uppercase text-re-text-muted">Without a system</p>
            <p className="mt-3 text-ui text-re-text-secondary">
              Dig through paper records, spreadsheets across multiple computers, call suppliers for missing info. Typical response: 3-5 days, incomplete.
            </p>
          </Card>
          <Card padding="compact">
            <p className="font-mono text-label uppercase text-re-text-muted">With RegEngine</p>
            <p className="mt-3 text-ui text-re-text-secondary">
              Click &ldquo;Export&rdquo; in your dashboard. RegEngine produces a sortable electronic spreadsheet structured to FDA&apos;s §1.1455 format, populated from your uploaded lot codes, dates, and locations. Done in minutes.
            </p>
          </Card>
        </div>
      </Section>

      {/* - HOW TO COMPLY - */}
      <Section
        id="how-to-comply"
        width="marketing"
        eyebrow="Getting started"
        title="How RegEngine supports your FSMA 204 program."
        description="No IT department required. No six-figure software contract. If you can fill out a spreadsheet, you can use RegEngine."
      >
        <ol className="space-y-4">
          {STEPS.map((step) => (
            <li key={step.num}>
              <Card padding="compact" className="flex gap-5">
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-re-border font-mono text-ui tabular-nums text-re-text-muted"
                >
                  {step.num}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-subheading text-re-text-primary">{step.title}</h3>
                  <p className="mt-2 text-ui text-re-text-secondary">{step.desc}</p>
                  {step.cta && (
                    <Link
                      href={step.cta.href}
                      className="mt-3 inline-flex items-center gap-1.5 text-ui font-medium text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                    >
                      {step.cta.label}
                      <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                    </Link>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ol>
      </Section>

      {/* - FAQ - */}
      <Section width="marketing" title="Common questions">
        <div className="max-w-[68ch] space-y-8">
          {FAQS.map((faq) => (
            <div key={faq.q}>
              <h3 className="text-subheading text-re-text-primary">{faq.q}</h3>
              <p className="mt-2 text-ui text-re-text-secondary">{faq.a}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* - FINAL CTA - */}
      <Section width="marketing" tone="inset">
        <div className="mx-auto max-w-[640px] text-center">
          <p className="font-mono text-label uppercase text-re-text-muted">
            FDA enforcement not before July 20, 2028
          </p>
          <h2 className="mt-4 font-display text-heading-lg text-re-text-primary">
            Don&apos;t wait to prepare.
          </h2>
          <p className="mx-auto mt-4 max-w-[500px] text-body text-re-text-secondary">
            Start with a free tool. See where you stand. Build the records your operation and customers need.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <Link href="/tools/ftl-checker">
                Free FTL Checker
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/retailer-readiness">Retailer Readiness Assessment</Link>
            </Button>
          </div>

          <p className="mt-8 text-small text-re-text-muted">
            Have a developer?{" "}
            <Link href="/docs/fsma-204" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">
              Read the integration guide →
            </Link>
          </p>
          <p className="mt-3 text-small text-re-text-muted">
            Try it:{" "}
            <Link href="/proof" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">/proof</Link>
            {" "}→{" "}
            <Link href="/verify" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">/verify</Link>.
          </p>
        </div>
      </Section>
    </div>
  );
}
