import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { ArrowRight, Shield } from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine vs iFoodDS | RegEngine",
  description: "Fair comparison of RegEngine and iFoodDS for FSMA 204 recordkeeping. Beta, pre-revenue RegEngine facts only; confirm each vendor yourself.",
  openGraph: {
    title: "RegEngine vs iFoodDS | RegEngine",
    description: "Fair comparison of RegEngine and iFoodDS for FSMA 204 recordkeeping. Beta, pre-revenue RegEngine facts only; confirm each vendor yourself.",
    url: "https://regengine.co/compare/ifoodds",
    type: "website",
  },
};

export default function CompareIFoodDSPage() {
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
        title={<>RegEngine vs iFoodDS</>}
        description={
          <>
            Fair, cited comparison. RegEngine is Beta and pre-revenue. Not legal advice. Not a partnership claim.
          </>
        }
      />

      <article>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine is Beta and pre-revenue. iFoodDS is a separate company. This page uses public press, iFoodDS pages, and RegEngine site facts only. Confirm current capabilities with each vendor before you buy.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Who each product is for</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS markets Trace Exchange as connected traceability for suppliers, distributors, retailers, and foodservice. TraceApproved is its readiness program with training, label review support, and a readiness badge, included with Trace Exchange Core per its public enrollment and blog pages. Sources: <a href="https://www.ifoodds.com/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/</a> , <a href="https://supplier-trace.ifoodds.com/suppliers/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://supplier-trace.ifoodds.com/suppliers/</a> , and <a href="https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Press in August 2026 reported that Foods Connected acquired the HarvestMark Quality Insights business from iFoodDS, and that iFoodDS continues independently with a focus on Trace Exchange. The same reporting lists Walmart as a customer. Sources: <a href="https://www.globenewswire.com/news-release/2026/08/13/3345027/0/en/foods-connected-acquires-harvestmark-quality-insights-platform-from-ifoodds.html" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.globenewswire.com/news-release/2026/08/13/3345027/0/en/foods-connected-acquires-harvestmark-quality-insights-platform-from-ifoodds.html</a> and <a href="https://www.nwaonline.com/news/2026/aug/12/walmart-food-traceability-provider-to-advance/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.nwaonline.com/news/2026/aug/12/walmart-food-traceability-provider-to-advance/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine positions itself as FSMA 204 recordkeeping software for the Food Traceability Rule. The homepage states design partner and pre-revenue. Live intake today is CSV upload and a JSON events API. Free tools live at <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link>. Sample exports and a verifier live at <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link>. RegEngine provides recordkeeping support; operators remain responsible for their compliance decisions.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Side by side (fair read)</h2>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Product center of gravity</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS: Connected network for sharing traceability data across trading partners, plus TraceApproved readiness training and badges. Source: <a href="https://www.ifoodds.com/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/</a> and <a href="https://supplier-trace.ifoodds.com/suppliers/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://supplier-trace.ifoodds.com/suppliers/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Recordkeeping workbench and free field tools focused on CTE and KDE coverage, preflight, commit gating, and operator verifiable exports. Sources: <Link href="/product" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/product</Link> and <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link>
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Network vs self serve evidence</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS: Value depends on trading partner participation and buyer onboarding paths. Public supplier pages describe sharing shipping data with customers and optional electronic data-interchange add ons for named retail programs. Source: <a href="https://supplier-trace.ifoodds.com/suppliers/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://supplier-trace.ifoodds.com/suppliers/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: You can inspect published proof artifacts without joining a network. Network interchange with any specific retailer is not claimed here.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: FSMA 204 date posture</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS TraceApproved blog cites the July 20, 2028 deadline and stresses early preparation. Source: <a href="https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Site states FDA will not enforce before July 20, 2028. Source: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FDA: Congress directed FDA not to enforce before July 20, 2028, and FDA intends to comply. Source: <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Buyer programs can move on a different clock than FDA enforcement. Confirm each buyer portal yourself. This page does not restate private buyer deadlines.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Proof you can inspect without a sales call</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS: Public marketing emphasizes Trace Exchange enrollment, TraceApproved coursework, and consultation paths. No public Merkle verified export bundle was found on the pages cited above.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link> publishes a synthetic FDA oriented sortable CSV sample, an EPCIS 2.0 JSON-LD sample (Preview), a Merkle rooted audit bundle, and verify_chain.py.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Pricing</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS: No public dollar list found on the pages reviewed. Enrollment and consultation CTAs are the public path.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: Pre-revenue Beta. Ask for current design partner terms on <Link href="/contact" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/contact</Link> if you need commercial terms.
          </p>
          <h3 className="mt-8 text-heading text-re-text-primary">Topic: Free tools</h3>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS: Not positioned as a free public FSMA 204 tool hub on the pages reviewed.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link> for FTL, CTE, KDE, TLC, and self reported checklist pages.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">When iFoodDS is the better fit</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Choose iFoodDS when your buyers already pull you into Trace Exchange, when you need a connected sharing network, or when TraceApproved training and badge signaling matter to your customers. That is the story their site and press support.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">When RegEngine is the better fit</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Choose RegEngine (Beta) when you need a FSMA 204 first recordkeeping layer, free list and field checks, CSV or JSON intake, and exports you can hash check on /proof before or beside any network enrollment. RegEngine does not claim it replaces a retailer required network.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Honest limits</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine is Beta and pre-revenue. Product copy states rule enforcement in production is currently advisory and being promoted to blocking. Cross tenant hardening is in active rollout. EPCIS shaped export is Preview. Interoperation with Trace Exchange is not claimed on this page.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS and RegEngine both change. Re read each vendor site before a purchase decision.
          </p>
          <h2 className="mt-12 text-heading text-re-text-primary">Sources</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS home: <a href="https://www.ifoodds.com/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/</a> (fetched 2026-11-03)
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS supplier enrollment / TraceApproved summary: <a href="https://supplier-trace.ifoodds.com/suppliers/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://supplier-trace.ifoodds.com/suppliers/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS TraceApproved blog: <a href="https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.ifoodds.com/blog-get-ready-for-fsma-204-with-ifoodds-traceapproved/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            GlobeNewswire HarvestMark / Foods Connected release: <a href="https://www.globenewswire.com/news-release/2026/08/13/3345027/0/en/foods-connected-acquires-harvestmark-quality-insights-platform-from-ifoodds.html" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.globenewswire.com/news-release/2026/08/13/3345027/0/en/foods-connected-acquires-harvestmark-quality-insights-platform-from-ifoodds.html</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            NWA Online Walmart customer mention: <a href="https://www.nwaonline.com/news/2026/aug/12/walmart-food-traceability-provider-to-advance/" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.nwaonline.com/news/2026/aug/12/walmart-food-traceability-provider-to-advance/</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine home, product, tools, proof, fsma-204: <Link href="/" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/</Link> , <Link href="/product" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/product</Link> , <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link> , <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link> , <Link href="/fsma-204" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/fsma-204</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FDA Food Traceability Rule page: <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods</a>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Workspace competitor baseline (checked 2026-10-08, updated 2026-10-12): /workspace/competitors/regengine-ifoodds.md
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            iFoodDS, Trace Exchange, TraceApproved, and related marks belong to their owners. This comparison reflects publicly available information and RegEngine interpretation.
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
