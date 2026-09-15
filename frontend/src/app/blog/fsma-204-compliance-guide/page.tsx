import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, Leaf } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
  title: 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
  description: 'FDA FSMA 204 requirements, deadlines, CTEs, KDEs, and what your food business must do to comply with food traceability rules by July 2028.',
  openGraph: {
    url: 'https://regengine.co/blog/fsma-204-compliance-guide',
    siteName: 'RegEngine',
    title: 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
    description: 'FDA FSMA 204 requirements, deadlines, CTEs, KDEs, and what your food business must do to comply with food traceability rules by July 2028.',
    type: 'article',
  },
};

export default function FSMA204ComplianceGuide() {
  return (
    <div className="bg-re-surface-base">
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-2 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          ← Back to Blog
        </Link>
        <PageHeader
          eyebrow="FSMA 204 Regulations"
          title="FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)"
          description="What you need to know about FDA food traceability rules, deadlines, and how to prepare your business."
          meta={
            <>
              <span>April 2026</span>
              <span>8 min read</span>
            </>
          }
        />
        <div>
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-body text-re-text-secondary mb-6">
              FDA's Food Safety Modernization Act (FSMA) 204 rule requires covered food businesses across the supply chain, from farms and manufacturers to distributors and retailers, to provide traceability records within 24 hours of an FDA request. The original compliance date was January 20, 2026; FDA has proposed a 30-month extension, and Congress directed FDA not to enforce before July 20, 2028.
            </p>
            <p className="text-body text-re-text-secondary">
              This is not optional. Non-compliance can result in FDA enforcement action, product recalls, and loss of retailer partnerships. The good news: understanding FSMA 204 requirements is straightforward, and with the right approach, compliance is achievable.
            </p>
          </div>

          {/* What is FSMA 204 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6 mt-12">
              What Is FSMA 204?
            </h2>
            <p className="text-body text-re-text-secondary mb-6">
              FSMA 204 is the FDA's Food Traceability Rule. It requires covered food businesses to keep records identifying the immediate previous sources and immediate recipients of their products. When the FDA needs your traceability data—due to a foodborne illness outbreak, contamination, or suspected intentional adulteration—you have 24 hours to provide it.
            </p>
            <p className="text-body text-re-text-secondary mb-6">
              The rule applies to foods specifically listed on the FDA's Food Traceability List (FTL), including leafy greens, berry crops, bivalve mollusks, soft cheeses, and more. If your business handles an FTL product, FSMA 204 traceability obligations may apply.
            </p>
            <p className="text-body text-re-text-secondary">
              The FDA designed FSMA 204 around two core concepts: Critical Tracking Events (CTEs) and Key Data Elements (KDEs). These are the data points your business must capture and retain for 2 years.
            </p>
          </div>

          {/* The 7 CTEs */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              The 7 Critical Tracking Events (CTEs)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              CTEs are the moments in the food supply chain where you must capture traceability data. Every covered food business must track all applicable CTEs for their product flow:
            </p>
            <div className="space-y-5 mb-8">
              {[
                { name: 'Harvesting', desc: 'When crops are harvested from the field' },
                { name: 'Cooling', desc: 'When produce is cooled after harvest (for produce that requires cooling)' },
                { name: 'Initial Packing', desc: 'When product is first packed in its final consumer-facing or commercial container' },
                { name: 'Transformation', desc: 'When raw ingredients are converted into a new product (e.g., juice from apples, canned goods)' },
                { name: 'Shipping', desc: 'When product leaves your facility to be sent to a customer' },
                { name: 'Receiving', desc: 'When your business receives product from a supplier' },
                { name: 'First Land-Based Receiving', desc: 'When aquaculture or bivalve products are brought to the first land-based facility' },
              ].map((cte, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <Leaf className="h-4 w-4 text-re-text-tertiary mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <div>
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {cte.name}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {cte.desc}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
            <p className="text-body text-re-text-secondary">
              Not every CTE applies to every business. A produce distributor tracks Receiving, Shipping, and First Land-Based Receiving. A manufacturer tracks Initial Packing and Transformation. Understanding which CTEs apply to your operation is the first step toward compliance.
            </p>
          </div>

          {/* Key Data Elements */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Key Data Elements (KDEs): What You Must Record
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              For each CTE, you must record specific Key Data Elements. These identify the product, when the event occurred, and who was involved:
            </p>
            <ul className="space-y-3 mb-8 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Traceability Lot Code (TLC)</strong> — A unique identifier that links the product through the supply chain</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Product Description</strong> — Name, variety, and any identifying information</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Quantity and Unit of Measure</strong> — How much product, in what units</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Location Information</strong> — Farm name, facility address, or geographic location</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Date/Time of CTE</strong> — When the event occurred</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span><strong>Immediate Previous Source or Recipient</strong> — Who you received from or sent to</span>
              </li>
            </ul>
            <p className="text-body text-re-text-secondary">
              EPCIS 2.0 (Electronic Product Code Information Services) can support trading-partner interoperability across the supply chain. FDA requests may require records, including an electronic sortable spreadsheet under 21 CFR 1.1455(c)(3), unless an exemption or agreed alternative applies.
            </p>
          </div>

          {/* The 24-Hour Rule */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              The 24-Hour Response Requirement
            </h2>
            <Callout tone="info" className="mb-8">
              <h4 className="text-subheading text-re-text-primary">The Core Deadline</h4>
              <p className="mt-1">When the FDA requests your traceability records, you have 24 hours to provide a complete list of the immediate previous sources and immediate recipients of the product in question. Failure to respond in time can result in enforcement action.</p>
            </Callout>
            <p className="text-body text-re-text-secondary mb-6">
              This is why your traceability system cannot rely on manual processes or spreadsheets. When the FDA calls, you need to generate a complete, review-ready report in minutes, not days.
            </p>
            <p className="text-body text-re-text-secondary">
              You must also retain all traceability records for 2 years from the date you created or obtained them under 21 CFR §1.1455(d), unless another provision of subpart S specifies otherwise. This means your system needs robust backup, archival, and retrieval capabilities to ensure data integrity over time.
            </p>
          </div>

          {/* Who Is Covered */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Who Is Covered by FSMA 204?
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              FSMA 204 applies to covered businesses that handle foods specifically listed on the FDA's Food Traceability List, including:
            </p>
            <ul className="space-y-2 mb-8 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Produce (leafy greens, berries, melons, and more)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Seafood (bivalve mollusks, certain finfish)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Certain cheeses and dairy products</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Spices and dried fruits</span>
              </li>
            </ul>
            <p className="text-body text-re-text-secondary mb-6">
              This includes farms, packers, manufacturers, distributors, retailers, and importers. If your business is part of the food supply chain for an FTL product, you are covered.
            </p>
            <p className="text-body text-re-text-secondary">
              Want to check if your specific products are on the FTL? Use RegEngine's free <Link href="/tools/ftl-checker" className="text-re-brand hover:text-re-brand underline transition-colors duration-120">FTL Coverage Checker</Link>.
            </p>
          </div>

          {/* Compliance Timeline */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              FSMA 204 Compliance Timeline
            </h2>
            <div className="space-y-4 mb-8">
              {[
                { year: 'July 20, 2028', desc: 'Earliest enforcement date under current congressional direction; FDA has proposed a 30-month extension' },
              ].map((item, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-2 h-2 w-2 rounded-full bg-re-text-tertiary" />
                  </div>
                  <div>
                    <p className="text-subheading text-re-text-primary">
                      {item.year}
                    </p>
                    <p className="text-re-text-secondary">
                      {item.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-body text-re-text-secondary">
              The current public posture points to July 20, 2028 as the earliest enforcement date under congressional direction, with FDA also proposing a 30-month extension. That may sound far away, but implementation typically takes 3-6 months depending on your current systems and supply chain complexity. Starting early gives you time to test, train, and refine your processes before enforcement resumes.
            </p>
          </div>

          {/* How to Prepare */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              How to Prepare for FSMA 204 Compliance
            </h2>
            <div className="space-y-6 mb-8">
              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  1. Audit Your Current Data Collection
                </h4>
                <p className="text-re-text-secondary">
                  Map out all the data you currently collect at each step of your supply chain. Identify gaps where CTEs or KDEs are missing. Do you have timestamps? Traceability lot codes? Supplier information?
                </p>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  2. Standardize Your Traceability Lot Code
                </h4>
                <p className="text-re-text-secondary">
                  Implement a consistent, unique TLC format across your supply chain. This doesn't need to be complex—it just needs to identify the product, lot, and date. Work with your suppliers and customers to ensure compatibility.
                </p>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  3. Choose a Traceability System
                </h4>
                <p className="text-re-text-secondary">
                  Options range from improved spreadsheets to specialized FSMA 204 software. Consider integration with your ERP, supplier connectivity, electronic sortable spreadsheet support, EPCIS 2.0 interoperability for trading partners, and your budget. A dedicated platform is typically faster and more reliable than manual processes.
                </p>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  4. Test Your 24-Hour Response
                </h4>
                <p className="text-re-text-secondary">
                  Run a mock FDA records request. Pick a product and TLC, and practice generating a complete traceability report from your system. Can you do it in under 24 hours? Under 1 hour? Document your process.
                </p>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  5. Train Your Team
                </h4>
                <p className="text-re-text-secondary">
                  Your warehouse, production, and logistics teams need to understand CTEs and KDEs. Make sure they know what data to capture and why it matters. Good training prevents compliance gaps.
                </p>
              </Card>
            </div>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Key Takeaways
            </h2>
            <ul className="space-y-3 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>FSMA 204 is mandatory for all food businesses handling foods on the FDA's Food Traceability List.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>§1.1455(c) requires you to provide a sortable electronic spreadsheet to FDA as soon as possible, and not later than 24 hours after a request.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Identify which Critical Tracking Events occur at your operation (§§1.1325–1.1350) and capture the KDEs the rule requires for each one — not every CTE applies to every business.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Retain all traceability records for 2 years.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>The original compliance date was January 20, 2026; FDA has proposed a 30-month extension and Congress directed FDA not to enforce before July 20, 2028. Start planning and implementation now.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <Card padding="spacious">
            <h3 className="text-heading text-re-text-primary">
              Ready to implement FSMA 204 compliance?
            </h3>
            <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
              RegEngine helps prepare CTE/KDE evidence, hash-chained ingestion records, and FDA-oriented sortable export packages aligned to 21 CFR 1.1455 where applicable. Run a free self-check to see where you stand.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/retailer-readiness">
                  Get Your Readiness Score
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/blog">Back to Blog</Link>
              </Button>
            </div>
          </Card>
        </div>
      </Container>
    </div>
  );
}
