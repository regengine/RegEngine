import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { ArrowRight, Shield } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs FoodReady | RegEngine",
  description: "Fair comparison of RegEngine and FoodReady for FSMA 204 recordkeeping. Beta, pre-revenue RegEngine facts only; confirm each vendor yourself.",
  openGraph: {
    title: "RegEngine vs FoodReady | RegEngine",
    description: "Fair comparison of RegEngine and FoodReady for FSMA 204 recordkeeping. Beta, pre-revenue RegEngine facts only; confirm each vendor yourself.",
    url: "https://regengine.co/compare/foodready",
    type: "website",
  },
};

export default function CompareFoodReadyPage() {
  return (
    <Container width="marketing" as="main" className="py-16">
      <PageHeader
        size="hero"
        className="mb-10"
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            Comparison
          </span>
        }
        title={<>RegEngine vs FoodReady</>}
        description={
          <>
            Fair, cited comparison. RegEngine is Beta and pre-revenue. Not legal advice. Not a partnership claim.
          </>
        }
      />

      <article>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine is Beta and pre-revenue. FoodReady is a separate company. This page uses public product pages and RegEngine site and repo facts only. Confirm current capabilities with each vendor before you buy.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Who each product is for</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady positions itself as food safety, quality, and compliance software plus consulting for food and beverage manufacturers and processors. Its public FSMA 204 page highlights lot level forward and backward tracing, mock recalls, CTE and KDE capture, supplier document workflows, barcode and mobile scanning, and certified food safety consultants. Source: <a href="https://foodready.ai/fsma-204-software/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/fsma-204-software/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine positions itself as FSMA 204 recordkeeping software for the Food Traceability Rule. The homepage states design partner and pre-revenue. Live intake today is CSV upload and a JSON events API. Free tools cover FTL, CTE, KDE, TLC, and self reported checklists. Sample exports and a verifier live on <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link>. RegEngine helps with recordkeeping. It is not FDA approved, not FDA certified, not FDA endorsed, and it does not guarantee compliance.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Side by side (fair read)</h2>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Product center of gravity</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: Broad food safety QMS plus consulting, with FSMA 204 presented as part of that suite. Pricing packages also list HACCP, SOP, GFSI, SQF, and BRC oriented features. Sources: <a href="https://foodready.ai/fsma-204-software/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/fsma-204-software/</a> and <a href="https://foodready.ai/pricing/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/pricing/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Focused on FSMA 204 recordkeeping, Inflow preflight, commit gating, and export packages operators can re check. Sources: <Link href="/" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/</Link> and <Link href="/product" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/product</Link>
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: FSMA 204 date posture</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: Public FSMA page states compliance takes effect July 20, 2028. Source: <a href="https://foodready.ai/fsma-204-software/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/fsma-204-software/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Site states FDA will not enforce before July 20, 2028. Source: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link> and <Link href="/fsma-204" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/fsma-204</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FDA: Congress directed FDA not to enforce the Food Traceability Rule before July 20, 2028, and FDA intends to comply. Source: <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods</a>
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: How you start</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: Guided implementation with food safety specialists; public FAQ says most teams move through mapping, import, and a validating mock recall in weeks, not months, scaling with facilities and SKUs. Source: <a href="https://foodready.ai/fsma-204-software/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/fsma-204-software/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Self serve free tools with no account required for the tool pages, plus design partner Beta product work. Upload path for product records is CSV. JSON events API is also live. EPCIS shaped export is Preview. Sources: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link> and <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link> and prior published RegEngine copy that matches live /verify and /proof
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Proof you can inspect without a sales call</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: Public site emphasizes demos and consultant led scoping. No public hash verified export bundle found on the pages cited above.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link> publishes a synthetic FDA oriented sortable CSV sample, an EPCIS 2.0 JSON-LD sample (Preview), a Merkle rooted audit bundle, and verify_chain.py so you can recompute hashes yourself.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Pricing</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: No public dollar list. Packages are Restaurant / Grocery / Food Service, Manufacturer / Processor, and Enterprise, each with Get A Quote. Annual plans and multi facility via sales. Source: <a href="https://foodready.ai/pricing/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/pricing/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Pre-revenue Beta. Do not treat older compare pages as a live price sheet. Ask for current design partner terms on <Link href="/contact" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/contact</Link> if you need commercial terms.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Free tools</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady: Not positioned as a free FSMA 204 tool hub on the pages reviewed.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link> ranks for free FSMA 204 tools in the 2026-11-03 SERP read and lists FTL List Checker, CTE Mapper, KDE Field Checklist, TLC Format Check, Self Reported Checklist, and Records Request Checklist.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">When FoodReady is the better fit</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Choose FoodReady when you want one vendor for HACCP or PCQI consulting, SOP libraries, GFSI oriented document control, and FSMA 204 records in the same suite. That is the story their pricing and FSMA pages tell.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">When RegEngine is the better fit</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Choose RegEngine (Beta) when you want a FSMA 204 first recordkeeping workbench, free list and field check tools, CSV or JSON intake, and exports you can hash check on /proof before you commit to a network or a full QMS. RegEngine is not a substitute for a full GFSI audit program.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Honest limits</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine is Beta and pre-revenue. Rule enforcement in production is described on the product page as currently advisory and being promoted to blocking. Cross tenant hardening is in active rollout. EPCIS shaped export is Preview. Buyer programs are separate from the FDA clock and must be confirmed with your buyer.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady and RegEngine both change. Re read each vendor site before a purchase decision.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Sources</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady FSMA page: <a href="https://foodready.ai/fsma-204-software/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/fsma-204-software/</a> (fetched 2026-11-03)
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady pricing page: <a href="https://foodready.ai/pricing/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://foodready.ai/pricing/</a> (fetched 2026-11-03)
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine home (pre-revenue / Beta framing): <Link href="/" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine product: <Link href="/product" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/product</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine tools: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine proof: <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine FSMA pillar: <Link href="/fsma-204" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/fsma-204</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FDA Food Traceability Rule page (July 20, 2028 enforcement direction): <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Workspace competitor baseline (checked 2026-10-08, updated 2026-10-12): /workspace/competitors/regengine-foodready.md
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            SEO plan SERP note for free FSMA 204 tools: /workspace/seo/regengine-google-page-one-2026-11-03.md
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FoodReady and its marks belong to their owners. This comparison reflects publicly available information and RegEngine interpretation.
          </p>
      </article>

      <div className="mt-14 flex flex-wrap gap-3">
        <Button asChild size="lg">
          <Link href="/tools">
            Free FSMA 204 tools
            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          </Link>
        </Button>
        <Button asChild variant="secondary" size="lg">
          <Link href="/proof">Open /proof</Link>
        </Button>
        <Button asChild variant="secondary" size="lg">
          <Link href="/contact">Contact RegEngine</Link>
        </Button>
      </div>
    </Container>
  );
}
