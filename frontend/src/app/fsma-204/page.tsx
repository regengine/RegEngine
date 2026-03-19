import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle, Clock, FileSpreadsheet, Shield, Upload, Users, AlertTriangle, Truck, Leaf, Anchor } from "lucide-react";

export const metadata: Metadata = {
  title: "FSMA 204 Compliance Guide — What Your Farm Needs to Know | RegEngine",
  description:
    "Plain-English guide to the FDA Food Traceability Rule. Learn what FSMA 204 requires, whether your products are covered, and how to get compliant — no developer needed.",
};

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const FTL_EXAMPLES = [
  { category: "Leafy Greens", examples: "Romaine, spinach, spring mix, kale" },
  { category: "Fruits", examples: "Tomatoes, peppers, melons, berries" },
  { category: "Fresh Herbs", examples: "Cilantro, basil, parsley" },
  { category: "Seafood", examples: "Finfish, crustaceans, mollusks" },
  { category: "Shell Eggs", examples: "All shell eggs" },
  { category: "Nut Butters", examples: "Peanut butter, almond butter" },
  { category: "Cheeses", examples: "Soft and semi-soft cheeses" },
  { category: "Ready-to-Eat Deli", examples: "Pre-made salads" },
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
    name: "Packing",
    icon: FileSpreadsheet,
    who: "Packhouses",
    what: "Record what was packed, when, the lot code, and the quantity.",
  },
  {
    name: "First Land-Based Receiving",
    icon: Anchor,
    who: "First US receiver of imported food",
    what: "Record when imported food first arrives on US soil, the lot code, origin, and entry details.",
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
    desc: "Download our CSV or Excel template, fill in your lot codes, locations, and dates. Upload it to RegEngine. No code, no API — just a spreadsheet.",
    cta: { label: "Download Templates", href: "/onboarding/bulk-upload" },
  },
  {
    num: "3",
    title: "RegEngine maps your events",
    desc: "We automatically organize your data into the 6 Critical Tracking Events the FDA requires. You see a simple dashboard showing what\u2019s covered and what\u2019s missing.",
    cta: null,
  },
  {
    num: "4",
    title: "Be ready when they ask",
    desc: "When the FDA or a retailer like Walmart requests traceability records, RegEngine generates the exact sortable spreadsheet they need — in minutes, not days.",
    cta: null,
  },
];

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function FSMA204BusinessGuidePage() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* — HERO — */}
      <section className="max-w-[960px] mx-auto px-6 pt-20 pb-16">
        <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-5">
          FSMA 204 Compliance Guide
        </p>        <h1 className="font-serif text-[clamp(2rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6 max-w-[720px]">
          The FDA food traceability rule — in plain English.
        </h1>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-4 max-w-[600px]">
          If you grow, pack, ship, or sell food on the FDA&apos;s Food Traceability List, FSMA 204 applies to you. Here&apos;s what it requires, whether you&apos;re a 50-acre farm or a national distributor.
        </p>
        <p className="text-[0.9rem] text-[var(--re-text-muted)] leading-relaxed mb-8 max-w-[600px]">
          No technical background needed. No jargon.
        </p>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/tools/ftl-checker"
            className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-3 rounded-lg text-[0.925rem] font-semibold hover:bg-[var(--re-brand-dark)] transition-all hover:-translate-y-0.5"
          >
            Check If Your Products Are Covered
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="#how-to-comply"
            className="inline-flex items-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-6 py-3 rounded-lg text-[0.925rem] font-medium hover:border-[var(--re-text-muted)] transition-all"
          >
            How to comply
          </Link>
        </div>
      </section>
      {/* — KEY FACTS STRIP — */}
      <div className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[960px] mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-6">
          {[
            { icon: Clock, text: "24 hours to respond to an FDA request" },
            { icon: Shield, text: "Applies to all foods on the FTL" },
            { icon: CheckCircle, text: "Enforcement begins July 20, 2028" },
          ].map((fact) => (
            <div key={fact.text} className="flex items-center gap-3">
              <fact.icon className="h-5 w-5 text-[var(--re-brand)] flex-shrink-0" />
              <span className="text-[0.9rem] text-[var(--re-text-secondary)]">{fact.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* — WHAT IS FSMA 204 — */}
      <section className="max-w-[960px] mx-auto px-6 py-20">
        <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-6">
          What is FSMA 204?
        </h2>
        <div className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed space-y-4 max-w-[680px]">
          <p>
            The FDA&apos;s Food Safety Modernization Act Section 204 — commonly called &ldquo;FSMA 204&rdquo; or the &ldquo;Food Traceability Rule&rdquo; — requires anyone who grows, receives, ships, or transforms certain high-risk foods to keep detailed traceability records.
          </p>          <p>
            The goal is simple: when a foodborne illness outbreak happens, the FDA needs to trace contaminated products from the farm to the store shelf within <strong className="text-[var(--re-text-primary)]">24 hours</strong>. Before this rule, that process took weeks.
          </p>
          <p>
            The rule was finalized in 2022. The original compliance date was January 20, 2026. <strong className="text-[var(--re-text-primary)]">Congress directed FDA not to enforce the rule before July 20, 2028.</strong> The requirements themselves have not changed.
          </p>
        </div>

        {/* Enforcement callout */}
        <div className="mt-8 p-5 rounded-xl border border-[rgba(234,179,8,0.25)] bg-[rgba(234,179,8,0.05)] max-w-[680px]">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-[#D97706] flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-[var(--re-text-primary)] mb-1">The deadline moved — the rule didn&apos;t.</p>
              <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                Congress directed FDA not to enforce before July 2028, but retailers like Walmart, Kroger, and Costco are already requiring traceability data from suppliers. Walmart required ASN compliance by August 2025. Kroger required EDI 856 compliance by June 2025. If you sell to a major retailer, your real deadline has already passed.
              </p>
            </div>
          </div>
        </div>
      </section>
      {/* — ARE YOUR PRODUCTS COVERED? — */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-20 px-6">
        <div className="max-w-[960px] mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            The Food Traceability List (FTL)
          </p>
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
            Are your products covered?
          </h2>
          <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[600px]">
            FSMA 204 only applies to foods on the FDA&apos;s Food Traceability List. Here are the main categories:
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
            {FTL_EXAMPLES.map((item) => (
              <div
                key={item.category}
                className="p-4 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]"
              >
                <p className="font-medium text-[var(--re-text-primary)] text-[0.95rem] mb-1">{item.category}</p>
                <p className="text-[0.82rem] text-[var(--re-text-muted)] leading-relaxed">{item.examples}</p>
              </div>
            ))}
          </div>

          <p className="text-[0.9rem] text-[var(--re-text-muted)] mb-4">
            Not sure if your specific products are on the list?
          </p>          <Link
            href="/tools/ftl-checker"
            className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-5 py-2.5 rounded-lg text-[0.9rem] font-semibold hover:bg-[var(--re-brand-dark)] transition-all"
          >
            Free FTL Checker — takes 30 seconds
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* — WHAT YOU HAVE TO RECORD — */}
      <section className="max-w-[960px] mx-auto px-6 py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          What the FDA requires
        </p>
        <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
          Seven events you need to track.
        </h2>
        <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-10 max-w-[600px]">
          FSMA 204 calls these &ldquo;Critical Tracking Events&rdquo; (CTEs). Each one has specific data points (called KDEs) you must record. Here&apos;s what they mean in practice:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CTES_PLAIN.map((cte) => (
            <div
              key={cte.name}
              className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]"
            >              <div className="flex items-center gap-3 mb-3">
                <div className="w-9 h-9 rounded-lg bg-[var(--re-brand-muted)] flex items-center justify-center">
                  <cte.icon className="h-4.5 w-4.5 text-[var(--re-brand)]" />
                </div>
                <h3 className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)]">{cte.name}</h3>
              </div>
              <p className="text-[0.82rem] text-[var(--re-brand)] font-medium mb-1.5">{cte.who}</p>
              <p className="text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">{cte.what}</p>
            </div>
          ))}
        </div>

        <div className="mt-8 p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] max-w-[680px]">
          <p className="font-medium text-[var(--re-text-primary)] mb-2">Which events apply to you?</p>
          <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
            Most farms need to record <strong className="text-[var(--re-text-primary)]">harvesting, cooling, packing, and shipping</strong>. Distributors typically handle receiving and shipping. Processors handle receiving and transformation. Importers must also record <strong className="text-[var(--re-text-primary)]">first land-based receiving</strong>. You only record the events that happen at your facility.
          </p>
        </div>
      </section>
      {/* — THE 24-HOUR RULE — */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-20 px-6">
        <div className="max-w-[960px] mx-auto">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-danger)] uppercase tracking-[0.08em] mb-4">
            The 24-hour rule
          </p>
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
            When the FDA calls, you have one day.
          </h2>
          <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[600px]">
            During a recall or outbreak investigation, the FDA can request your traceability records. You must provide them in an <strong className="text-[var(--re-text-primary)]">electronic, sortable format</strong> (like a spreadsheet) within <strong className="text-[var(--re-text-primary)]">24 hours</strong>.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-[680px]">
            <div className="p-5 rounded-xl border border-[rgba(220,38,38,0.2)] bg-[rgba(220,38,38,0.03)]">
              <p className="font-mono text-[0.7rem] font-medium text-[var(--re-danger)] uppercase tracking-[0.06em] mb-3">Without a system</p>
              <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                Dig through paper records, spreadsheets across multiple computers, call suppliers for missing info. Typical response: 3-5 days, incomplete.
              </p>
            </div>
            <div className="p-5 rounded-xl border border-[rgba(16,163,74,0.2)] bg-[rgba(16,163,74,0.03)]">
              <p className="font-mono text-[0.7rem] font-medium text-[var(--re-brand-dark)] uppercase tracking-[0.06em] mb-3">With RegEngine</p>
              <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">
                Click &ldquo;Export&rdquo; in your dashboard. RegEngine generates the FDA-required spreadsheet with all your lot codes, dates, and locations. Done in minutes.
              </p>
            </div>
          </div>
        </div>
      </section>
      {/* — HOW TO COMPLY — */}
      <section id="how-to-comply" className="max-w-[960px] mx-auto px-6 py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          Getting started
        </p>
        <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
          How to get compliant with RegEngine.
        </h2>
        <p className="text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-10 max-w-[600px]">
          No IT department required. No six-figure software contract. If you can fill out a spreadsheet, you can use RegEngine.
        </p>

        <div className="space-y-4">
          {STEPS.map((step) => (
            <div
              key={step.num}
              className="flex gap-5 p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]"
            >
              <div className="w-10 h-10 rounded-full bg-[var(--re-brand-muted)] flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="font-serif text-[1.1rem] font-bold text-[var(--re-brand)]">{step.num}</span>
              </div>
              <div className="flex-1">
                <h3 className="font-serif text-[1.1rem] font-medium text-[var(--re-text-primary)] mb-2">{step.title}</h3>
                <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">{step.desc}</p>
                {step.cta && (
                  <Link
                    href={step.cta.href}
                    className="inline-flex items-center gap-1.5 text-[0.85rem] font-medium text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors mt-3"
                  >                    {step.cta.label}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* — FAQ — */}
      <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-20 px-6">
        <div className="max-w-[960px] mx-auto">
          <h2 className="font-serif text-[2rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-10">
            Common questions
          </h2>

          <div className="space-y-8 max-w-[680px]">
            {[
              {
                q: "I\u2019m a small farm. Does this really apply to me?",
                a: "If you grow, harvest, cool, pack, or ship any food on the FDA Food Traceability List, yes. There are limited exemptions for farms that sell directly to consumers, but if you sell to a distributor, retailer, or restaurant, you\u2019re likely covered.",
              },
              {
                q: "I don\u2019t have a developer or IT person. Can I still use RegEngine?",
                a: "Yes. You can upload your data using our CSV or Excel templates \u2014 no code required. Download the template, fill in your lot codes and dates, and upload. RegEngine handles the rest.",
              },
              {
                q: "What if I already track this in spreadsheets?",
                a: "That\u2019s a great start. The challenge is that the FDA requires a specific format and the ability to trace lots forward and backward through your supply chain. RegEngine takes your existing data and organizes it into the structure the FDA expects.",
              },              {
                q: "How is this different from what Walmart already asks for?",
                a: "Walmart and other major retailers have been requiring traceability data ahead of the FDA deadline. If you already supply traceability data to a retailer, you\u2019re partially prepared. RegEngine ensures your records meet both retailer and FDA requirements from one system.",
              },
              {
                q: "What happens if I\u2019m not compliant by July 2028?",
                a: "The FDA can issue warning letters, request voluntary recalls, or in serious cases, pursue injunctions. Beyond enforcement, retailers may drop non-compliant suppliers. The bigger risk for most farms is losing a customer like Walmart over missing traceability data.",
              },
              {
                q: "How much does this cost?",
                a: "We have plans designed for small farms and growers. Start with a free readiness assessment to see where you stand, then we\u2019ll recommend the right plan.",
              },
            ].map((faq) => (
              <div key={faq.q}>
                <h3 className="font-serif text-[1.05rem] font-medium text-[var(--re-text-primary)] mb-2">{faq.q}</h3>
                <p className="text-[0.9rem] text-[var(--re-text-secondary)] leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      {/* — FINAL CTA — */}
      <section className="bg-[var(--re-text-primary)] text-white py-20 px-6">
        <div className="max-w-[960px] mx-auto text-center">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand-light)] uppercase tracking-[0.08em] mb-4">
            FSMA 204 Enforcement: July 20, 2028
          </p>
          <h2 className="font-serif text-[2.25rem] font-bold text-white tracking-tight leading-tight mb-4 max-w-[640px] mx-auto">
            Don&apos;t wait for the deadline.
          </h2>
          <p className="text-[1.05rem] text-[#aaa] max-w-[500px] mx-auto leading-relaxed mb-8">
            Start with a free tool. See where you stand. Get compliant on your schedule — not the FDA&apos;s.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              href="/tools/ftl-checker"
              className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-lg text-[0.95rem] font-semibold hover:bg-[#0BAE78] transition-all hover:-translate-y-0.5"
            >
              Free FTL Checker
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/retailer-readiness"
              className="inline-flex items-center gap-2 border border-[#444] text-white px-7 py-3.5 rounded-lg text-[0.95rem] font-medium hover:border-[#888] transition-all"
            >
              Retailer Readiness Assessment
            </Link>
          </div>

          <p className="text-[0.82rem] text-[#666] mt-8">
            Have a developer?{" "}
            <Link href="/docs/fsma-204" className="text-[var(--re-brand)] hover:underline">
              Read the integration guide →
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}