import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, Leaf } from 'lucide-react';

export const metadata: Metadata = {
  title: 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
  description: 'FDA FSMA 204 requirements, deadlines, CTEs, KDEs, and what your food business must do to comply with food traceability rules by July 2028.',
  openGraph: {
    title: 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
    description: 'FDA FSMA 204 requirements, deadlines, CTEs, KDEs, and what your food business must do to comply with food traceability rules by July 2028.',
    type: 'article',
  },
};

export default function FSMA204ComplianceGuide() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* Hero */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-8 sm:pb-12">
        <div className="mb-8">
          <Link
            href="/blog"
            className="inline-flex items-center gap-2 text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors duration-200 text-sm font-medium mb-6"
          >
            ← Back to Blog
          </Link>
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            FSMA 204 Regulations
          </p>
          <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight mb-6">
            FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)
          </h1>
          <p className="text-[1.1rem] text-[var(--re-text-secondary)] leading-relaxed mb-4">
            What you need to know about FDA food traceability rules, deadlines, and how to prepare your business.
          </p>
          <div className="flex gap-6 text-sm text-[var(--re-text-muted)] pt-4 border-t border-[var(--re-surface-border)]">
            <span>April 2026</span>
            <span>8 min read</span>
          </div>
        </div>
      </section>

      {/* Content */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <article className="prose prose-invert max-w-none">
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              On July 20, 2028, the FDA's Food Safety Modernization Act (FSMA) 204 compliance deadline arrives. Food businesses across the supply chain—from farms and manufacturers to distributors and retailers—must be able to provide complete traceability records within 24 hours of an FDA request.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              This is not optional. Non-compliance can result in FDA enforcement action, product recalls, and loss of retailer partnerships. The good news: understanding FSMA 204 requirements is straightforward, and with the right approach, compliance is achievable.
            </p>
          </div>

          {/* What is FSMA 204 */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6 mt-12">
              What Is FSMA 204?
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              FSMA 204 is the FDA's Food Traceability Rule. It requires covered food businesses to keep records identifying the immediate previous sources and immediate recipients of their products. When the FDA needs your traceability data—due to a foodborne illness outbreak, contamination, or suspected intentional adulteration—you have 24 hours to provide it.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The rule applies to foods on the FDA's Food Traceability List (FTL), which includes 26 categories of high-risk foods: leafy greens, berry crops, bivalve mollusks, soft cheeses, and more. If your business handles any FTL product, FSMA 204 compliance is mandatory.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              The FDA designed FSMA 204 around two core concepts: Critical Tracking Events (CTEs) and Key Data Elements (KDEs). These are the data points your business must capture and retain for 2 years.
            </p>
          </div>

          {/* The 7 CTEs */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              The 7 Critical Tracking Events (CTEs)
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
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
                <div key={idx} className="flex gap-4 p-4 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/30 transition-colors duration-200">
                  <div className="flex-shrink-0">
                    <Leaf className="w-5 h-5 text-[var(--re-brand)] mt-0.5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-[var(--re-text-primary)] mb-1">
                      {cte.name}
                    </h4>
                    <p className="text-sm text-[var(--re-text-secondary)]">
                      {cte.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              Not every CTE applies to every business. A produce distributor tracks Receiving, Shipping, and First Land-Based Receiving. A manufacturer tracks Initial Packing and Transformation. Understanding which CTEs apply to your operation is the first step toward compliance.
            </p>
          </div>

          {/* Key Data Elements */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Key Data Elements (KDEs): What You Must Record
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              For each CTE, you must record specific Key Data Elements. These identify the product, when the event occurred, and who was involved:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Traceability Lot Code (TLC)</strong> — A unique identifier that links the product through the supply chain</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Product Description</strong> — Name, variety, and any identifying information</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Quantity and Unit of Measure</strong> — How much product, in what units</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Location Information</strong> — Farm name, facility address, or geographic location</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Date/Time of CTE</strong> — When the event occurred</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Immediate Previous Source or Recipient</strong> — Who you received from or sent to</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              The FDA prefers EPCIS 2.0 (Electronic Product Code Information Services) as the data exchange format. This standardized format ensures interoperability across the supply chain, making it easier to share data with suppliers, customers, and the FDA.
            </p>
          </div>

          {/* The 24-Hour Rule */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              The 24-Hour Response Requirement
            </h2>
            <div className="p-6 rounded-lg bg-[var(--re-brand)]/5 border border-[var(--re-brand)]/20 mb-8">
              <div className="flex gap-4">
                <AlertCircle className="w-6 h-6 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-[var(--re-text-primary)] mb-2">
                    The Core Deadline
                  </h4>
                  <p className="text-[var(--re-text-secondary)]">
                    When the FDA requests your traceability records, you have 24 hours to provide a complete list of the immediate previous sources and immediate recipients of the product in question. Failure to respond in time can result in enforcement action.
                  </p>
                </div>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              This is why your traceability system cannot rely on manual processes or spreadsheets. When the FDA calls, you need to generate a complete, audit-ready report in minutes, not days.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              You must also retain all traceability records for 2 years. This means your system needs robust backup, archival, and retrieval capabilities to ensure data integrity over time.
            </p>
          </div>

          {/* Who Is Covered */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Who Is Covered by FSMA 204?
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              FSMA 204 applies to any business that handles foods on the FDA's Food Traceability List, which includes 26 categories across:
            </p>
            <ul className="space-y-2 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Produce (leafy greens, berries, melons, and more)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Seafood (bivalve mollusks, certain finfish)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Certain cheeses and dairy products</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Spices and dried fruits</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              This includes farms, packers, manufacturers, distributors, retailers, and importers. If your business is part of the food supply chain for an FTL product, you are covered.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              Want to check if your specific products are on the FTL? Use RegEngine's free <Link href="/tools/ftl-checker" className="text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] underline transition-colors duration-200">FTL Coverage Checker</Link>.
            </p>
          </div>

          {/* Compliance Timeline */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              FSMA 204 Compliance Timeline
            </h2>
            <div className="space-y-4 mb-8">
              {[
                { year: 'July 20, 2028', desc: 'Deadline for all covered food businesses' },
              ].map((item, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex-shrink-0">
                    <div className="w-3 h-3 rounded-full bg-[var(--re-brand)] mt-2" />
                  </div>
                  <div>
                    <p className="font-semibold text-[var(--re-text-primary)]">
                      {item.year}
                    </p>
                    <p className="text-[var(--re-text-secondary)]">
                      {item.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              You have until July 20, 2028 to implement FSMA 204 compliance. That may sound far away, but implementation typically takes 3–6 months depending on your current systems and supply chain complexity. Starting early gives you time to test, train, and refine your processes before the deadline.
            </p>
          </div>

          {/* How to Prepare */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              How to Prepare for FSMA 204 Compliance
            </h2>
            <div className="space-y-6 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  1. Audit Your Current Data Collection
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Map out all the data you currently collect at each step of your supply chain. Identify gaps where CTEs or KDEs are missing. Do you have timestamps? Traceability lot codes? Supplier information?
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  2. Standardize Your Traceability Lot Code
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Implement a consistent, unique TLC format across your supply chain. This doesn't need to be complex—it just needs to identify the product, lot, and date. Work with your suppliers and customers to ensure compatibility.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  3. Choose a Traceability System
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Options range from improved spreadsheets to specialized FSMA 204 software. Consider integration with your ERP, supplier connectivity, FDA data format support (EPCIS 2.0), and your budget. A dedicated platform is typically faster and more reliable than manual processes.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  4. Test Your 24-Hour Response
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Run a mock FDA records request. Pick a product and TLC, and practice generating a complete traceability report from your system. Can you do it in under 24 hours? Under 1 hour? Document your process.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  5. Train Your Team
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Your warehouse, production, and logistics teams need to understand CTEs and KDEs. Make sure they know what data to capture and why it matters. Good training prevents compliance gaps.
                </p>
              </div>
            </div>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Key Takeaways
            </h2>
            <ul className="space-y-3 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>FSMA 204 is mandatory for all food businesses handling foods on the FDA's Food Traceability List.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You must respond to FDA records requests within 24 hours with complete traceability data.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Track 7 CTEs and associated KDEs at each step of your supply chain.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Retain all traceability records for 2 years.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>The compliance deadline is July 20, 2028. Start planning and implementation now.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <div className="p-8 sm:p-12 rounded-xl border border-[var(--re-brand)]/20 bg-gradient-to-br from-[var(--re-brand)]/5 to-cyan-600/5">
            <h3 className="font-serif text-xl font-bold text-[var(--re-text-primary)] mb-4">
              Ready to implement FSMA 204 compliance?
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-8">
              RegEngine automates FSMA 204 data capture, verification, and FDA-ready reporting. Get your free readiness score to see where you stand.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px] max-w-fit"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Get Your Readiness Score</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/blog"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                Back to Blog
              </Link>
            </div>
          </div>
        </article>
      </section>
    </div>
  );
}
