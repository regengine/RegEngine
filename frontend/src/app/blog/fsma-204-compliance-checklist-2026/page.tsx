import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { JSONLD } from "@/components/seo/json-ld";
import { blogPostingJsonLd } from "@/lib/blog-jsonld";

export const metadata: Metadata = {
  title: "FSMA 204 Compliance Checklist for July 20, 2028: What to Do Now | RegEngine Blog",
  description: "A phased checklist to prepare your food business for FDA Food Traceability Rule enforcement that will not begin before July 20, 2028.",
  openGraph: {
    url: "https://regengine.co/blog/fsma-204-compliance-checklist-2026",
    siteName: "RegEngine",
    title: "FSMA 204 Compliance Checklist for July 20, 2028: What to Do Now",
    description: "A phased checklist to prepare your food business for FDA Food Traceability Rule enforcement that will not begin before July 20, 2028.",
    type: "article",
    publishedTime: "2026-11-03T00:00:00Z",
  },
};

export default function Fsma204ComplianceChecklistPage() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={blogPostingJsonLd("fsma-204-compliance-checklist-2026", "A phased checklist to prepare your food business for FDA Food Traceability Rule enforcement that will not begin before July 20, 2028.")} />
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          Back to Blog
        </Link>
        <PageHeader
          size="hero"
          className="mb-10"
          title={<>FSMA 204 Compliance Checklist for July 20, 2028: What to Do Now</>}
          description={<>A phased checklist to prepare your food business for FDA Food Traceability Rule enforcement that will not begin before July 20, 2028.</>}
        />
        <p className="mb-8 text-small text-re-text-muted">Updated November 3, 2026 · RegEngine is Beta and pre-revenue</p>
        <article>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Current public FDA posture is that FDA will not enforce the Food Traceability Rule before July 20, 2028 under congressional direction, and FDA intends to comply. That still leaves a finite window. Implementation for covered operations often takes months, not days, once you map products, suppliers, CTEs, and KDEs.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            This checklist breaks the work into phases you can track. It is not legal advice, not a covered person determination, and not a readiness score. RegEngine (Beta) publishes free tools that echo what you report; they do not decide compliance for you.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Phase 1: Assessment (now through mid 2027)</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Review the FDA Food Traceability List and note which of your products may be in scope. Use <Link href="/tools/ftl-checker" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/ftl-checker</Link> as a list look up aid, then confirm against FDA.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Audit what you already capture at shipping, receiving, transformation, harvesting, cooling, and packing steps.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            List missing Critical Tracking Events and Key Data Elements. The harvesting deep dive at <Link href="/fsma-204/harvesting" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/fsma-204/harvesting</Link> shows how one CTE spells out required fields.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Document suppliers, distributors, and customers and where data flows today.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            List ERP, WMS, or spreadsheet systems that would need to feed a traceability record store.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Name one compliance lead with executive sponsorship. Do not dilute ownership across an unnamed committee.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Phase 2: Planning and selection (through late 2027)</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Define CTEs and KDEs per product line. Use <Link href="/tools/cte-mapper" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/cte-mapper</Link> and <Link href="/tools/kde-checker" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/kde-checker</Link> as field check aids.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Standardize Traceability Lot Code format and how codes are assigned. Use <Link href="/tools/tlc-validator" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/tlc-validator</Link> as a format check aid, then document the real SOP.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Choose whether you will use a platform, a network your buyers require, in house tooling, or a mix. RegEngine is one Beta option focused on FSMA 204 recordkeeping. Broader QMS suites and connected networks exist; compare on facts, not slogans.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Draft a supplier data template and test it with a few real suppliers.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Write the 24 hour records request runbook: who is on call, which system is queried, who signs the package. Pair this with <Link href="/blog/24-hour-rule" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/blog/24-hour-rule</Link> and <Link href="/tools/records-request-checklist" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/records-request-checklist</Link>.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Phase 3: Pilot (late 2027 through early 2028)</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Pick one high volume or high risk FTL product line.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Stand up the chosen record store and connect the minimum CSV or API feeds you need. RegEngine live intake today is CSV upload and a JSON events API. EPCIS shaped export is Preview.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Train warehouse, production, and logistics people on what to capture and why.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Run a records request drill on one lot. Time the response. Fix gaps before you scale.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Write SOPs for CTE capture, TLC assignment, and export packaging.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Phase 4: Scale (early 2028 through mid 2028)</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Extend coverage to remaining in scope products.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Onboard remaining suppliers you depend on for KDEs you cannot create alone.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Run multi product drills. Keep the target honest: produce a sortable electronic package under pressure, not a slide deck about readiness.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Test retrieval of older lots against your retention plan.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Update the Food Safety Plan references so operators know where the FSMA 204 records live.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Phase 5: Maintain through July 20, 2028 and after</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Monitor data quality and fix queue age.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Run quarterly drills.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Keep new SKUs mapped before they ship.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Watch FDA guidance updates. Buyer portals can move on a different clock than FDA enforcement; confirm each buyer yourself.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Refresh training when crews change.
          </p>
          <h2 className="mt-10 text-heading text-re-text-primary">Free RegEngine tools that support this checklist</h2>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            FTL List Checker: <Link href="/tools/ftl-checker" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/ftl-checker</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            CTE Mapper: <Link href="/tools/cte-mapper" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/cte-mapper</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            KDE Field Checklist: <Link href="/tools/kde-checker" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/kde-checker</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            TLC Format Check: <Link href="/tools/tlc-validator" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/tlc-validator</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Self Reported Checklist: <Link href="/tools/self-reported-checklist" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/self-reported-checklist</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Records Request Checklist: <Link href="/tools/records-request-checklist" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools/records-request-checklist</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Tools hub: <Link href="/tools" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/tools</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Proof artifacts you can hash check: <Link href="/proof" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/proof</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Pillar guide: <Link href="/fsma-204" className="text-re-brand underline underline-offset-[3px]">https://regengine.co/fsma-204</Link>
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine helps with recordkeeping. It is not FDA approved, not FDA certified, not FDA endorsed, and it does not guarantee compliance. FDA will not enforce before July 20, 2028, which is time to get records right.
          </p>
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            Primary FDA source for the date: <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods" className="text-re-brand underline underline-offset-[3px]" rel="noopener noreferrer" target="_blank">https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods</a>
          </p>
        </article>
        <div className="mt-12 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/tools">Free FSMA 204 tools</Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/blog">Back to Blog</Link>
          </Button>
        </div>
      </Container>
    </div>
  );
}
