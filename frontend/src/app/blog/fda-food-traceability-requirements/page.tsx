import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, Leaf, Clock, MapPin } from 'lucide-react';

export const metadata: Metadata = {
  title: 'FDA Food Traceability Requirements: Complete Guide to FSMA 204 Rules',
  description: 'Understand FDA food traceability requirements, FTL products, CTEs, KDEs, and the 24-hour response requirement for FSMA 204 compliance.',
  openGraph: {
    title: 'FDA Food Traceability Requirements: Complete Guide to FSMA 204 Rules',
    description: 'Understand FDA food traceability requirements, FTL products, CTEs, KDEs, and the 24-hour response requirement for FSMA 204 compliance.',
    type: 'article',
  },
};

export default function FDAFoodTraceabilityRequirements() {
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
            FDA Regulations
          </p>
          <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight mb-6">
            FDA Food Traceability Requirements: A Complete Guide
          </h1>
          <p className="text-[1.1rem] text-[var(--re-text-secondary)] leading-relaxed mb-4">
            What the FDA requires, who it applies to, and what you need to track.
          </p>
          <div className="flex gap-6 text-sm text-[var(--re-text-muted)] pt-4 border-t border-[var(--re-surface-border)]">
            <span>April 2026</span>
            <span>11 min read</span>
          </div>
        </div>
      </section>

      {/* Content */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <article className="prose prose-invert max-w-none">
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The FDA's Food Traceability Rule (FSMA 204) represents a fundamental shift in how food businesses must manage supply chain visibility. Rather than relying on recall procedures that can take weeks, the FDA now requires that covered food businesses identify the immediate source and immediate recipients of products within 24 hours of an FDA request.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              This guide walks through the FDA's food traceability requirements in detail: what the rule is, what products are covered, what you must track, and how to implement compliance.
            </p>
          </div>

          {/* The FDA's Authority */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6 mt-12">
              The FDA's Authority and the Food Safety Modernization Act
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The Food Safety Modernization Act (FSMA), signed into law in 2011, gave the FDA broad authority to establish rules that improve food safety and reduce the burden of foodborne illness outbreaks. FSMA 204, the Food Traceability Rule, is one of the most significant rules to emerge from this authority.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The rule was finalized in November 2022 and becomes enforceable on July 20, 2028. Unlike guidance or recommendations, this is a legal requirement. Non-compliance can result in FDA warning letters, consent decrees, recalls, and product seizures.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              The FDA's primary goal is to reduce the time it takes to identify products involved in a foodborne illness outbreak or contamination event. When lives are at stake, speed matters.
            </p>
          </div>

          {/* Foods on the FTL */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Which Foods Are Covered? The Food Traceability List (FTL)
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              FSMA 204 doesn't apply to all food products. The FDA created the Food Traceability List (FTL)—a curated list of 26 product categories that have been identified as high-risk for contamination or foodborne illness. Only foods on the FTL are subject to FSMA 204 compliance.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              The FTL includes:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <Leaf className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Fresh Produce:</strong> Leafy greens, berry crops, melons, cucumbers, tomatoes, peppers, onions, green onions, herbs, and fresh-cut fruits</span>
              </li>
              <li className="flex gap-3">
                <Leaf className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Seafood:</strong> Bivalve mollusks (oysters, mussels, clams), certain finfish species</span>
              </li>
              <li className="flex gap-3">
                <Leaf className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Dairy & Cheese:</strong> Soft cheeses (brie, camembert), certain unpasteurized cheeses</span>
              </li>
              <li className="flex gap-3">
                <Leaf className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Other Foods:</strong> Nut butters, spices, dried fruits, and tropical tree fruits</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              If your product isn't on the FTL, you may not be subject to FSMA 204. However, the FDA is monitoring compliance and may expand the list in the future.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              To check if your products are on the FTL, use RegEngine's free <Link href="/tools/ftl-checker" className="text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] underline transition-colors duration-200">FTL Coverage Checker</Link>.
            </p>
          </div>

          {/* Who Must Comply */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Who Must Comply with FSMA 204?
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              FSMA 204 applies to any business that handles or processes an FTL food at any stage of the supply chain. This includes:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Farms and growers</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Packers and processors</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Manufacturers and ingredient suppliers</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Distributors and wholesalers</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Retail stores and restaurants (for FTL foods they sell)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Food importers</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              The only exemptions are very small businesses with less than $1 million in annual food sales. Even then, you may still need to comply if you import FTL foods.
            </p>
          </div>

          {/* The 7 CTEs */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              What Must You Track? The 7 Critical Tracking Events
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              The FDA identified seven key moments in the food supply chain where products must be tracked. These are called Critical Tracking Events (CTEs). Your business must capture data at each CTE that applies to your operations:
            </p>
            <div className="space-y-5 mb-8">
              {[
                {
                  name: 'Growing',
                  desc: 'For agricultural products, the harvest event and the associated farm information',
                },
                {
                  name: 'Receiving',
                  desc: 'When your business receives product from a supplier or farm',
                },
                {
                  name: 'Transforming',
                  desc: 'When raw materials are processed into a new product (e.g., grinding grain, juicing fruit)',
                },
                {
                  name: 'Creating',
                  desc: 'When you create a new product that combines multiple ingredients or components',
                },
                {
                  name: 'Shipping',
                  desc: 'When product leaves your facility to be sent to a customer or distributor',
                },
                {
                  name: 'First Land-Based Receiving',
                  desc: 'When aquaculture or bivalve products arrive at the first land-based facility',
                },
                {
                  name: 'Initial Packing',
                  desc: 'When product is first placed in its final consumer-facing or commercial container',
                },
              ].map((cte, idx) => (
                <div
                  key={idx}
                  className="flex gap-4 p-4 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/30 transition-colors duration-200"
                >
                  <div className="flex-shrink-0">
                    <Clock className="w-5 h-5 text-[var(--re-brand)] mt-0.5" />
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
              Not every CTE applies to every business. A retail store may only track Receiving and Shipping. A farm tracks Growing and possibly Initial Packing. A manufacturer tracks Receiving, Transforming, and Shipping. Use RegEngine's <Link href="/tools/cte-mapper" className="text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] underline transition-colors duration-200">CTE Mapper</Link> to identify which CTEs apply to your specific operations.
            </p>
          </div>

          {/* Key Data Elements */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              What Specific Data Must You Capture? Key Data Elements
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              For each CTE, the FDA requires you to capture specific Key Data Elements (KDEs). These are the core data points that identify the product and create the link between your immediate supplier and immediate customer:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Product Description:</strong> Name, variety, and any identifying characteristics</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Traceability Lot Code (TLC):</strong> A unique identifier assigned to a product lot</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Quantity and Unit of Measure:</strong> How much product, in what units (pounds, boxes, etc.)</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Location Information:</strong> Farm name, facility address, or geographic coordinates</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Date and Time of CTE:</strong> When the tracking event occurred</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Immediate Previous Source:</strong> Name and identifier of the supplier you received from</span>
              </li>
              <li className="flex gap-3">
                <MapPin className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span><strong>Immediate Recipient:</strong> Name and identifier of the customer you sent to</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              The FDA prefers data in EPCIS 2.0 format (Electronic Product Code Information Services), a standardized data interchange format. This ensures that data can flow automatically between suppliers, your company, and the FDA.
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
                    The Central Requirement
                  </h4>
                  <p className="text-[var(--re-text-secondary)]">
                    When the FDA issues a records request for traceability data, your company has 24 hours to provide a complete list of the immediate previous source and immediate recipients of the product in question.
                  </p>
                </div>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              This is the core requirement that drives everything else. You must be able to:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Receive and understand the FDA's records request</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Query your system to locate all matching products and lots</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Retrieve the immediate source and recipient information from your records</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Format the data according to FDA requirements (typically EPCIS 2.0)</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Deliver the complete report to the FDA</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              This is why spreadsheets and manual processes don't work at scale. You need a system that can retrieve and format traceability data in minutes, not hours or days.
            </p>
          </div>

          {/* Data Retention */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              How Long Must You Keep Records?
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              All traceability records must be retained for 2 years. This means:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You must have secure storage for 2 years of CTE and KDE data</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Data must be retrievable and searchable even after 2 years</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You must have audit trails that show who accessed or modified the data</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Data must be protected against loss, corruption, or tampering</span>
              </li>
            </ul>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              This is another reason why you need a dedicated traceability system. It handles the technical challenges of archival, backup, recovery, and audit logging so you don't have to.
            </p>
          </div>

          {/* Implementation Overview */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Putting It All Together: Your FSMA 204 Implementation
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              Understanding FDA requirements is the first step. Implementation requires:
            </p>
            <div className="space-y-6 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  1. Map Your Operations
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Identify which of your products are on the FTL, which CTEs apply to your business, and what KDEs you need to capture.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  2. Establish Data Capture
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Update your processes, forms, and systems to capture all required KDEs at each CTE.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  3. Build Supply Chain Collaboration
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Create processes for suppliers to submit traceability data to you, and for you to submit it to customers.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  4. Choose a Traceability System
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Invest in a system that can store, query, and format traceability data in compliance with FDA requirements.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  5. Test Your 24-Hour Response
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Run mock FDA records requests. Ensure you can provide complete, accurate traceability data within 24 hours.
                </p>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  6. Train Your Team
                </h4>
                <p className="text-[var(--re-text-secondary)]">
                  Make sure everyone involved in production, logistics, and customer service understands FSMA 204 and their role in compliance.
                </p>
              </div>
            </div>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              FDA Food Traceability Requirements: Key Takeaways
            </h2>
            <ul className="space-y-3 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>FSMA 204 applies to foods on the FDA's Food Traceability List (26 product categories, mostly produce and seafood).</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You must track 7 Critical Tracking Events (CTEs) that apply to your business.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>For each CTE, you must capture Key Data Elements (KDEs) that identify the product and create source-recipient links.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>The core requirement: respond to FDA records requests within 24 hours with complete traceability data.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>You must retain all traceability records for 2 years.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Compliance deadline: July 20, 2028.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <div className="p-8 sm:p-12 rounded-xl border border-[var(--re-brand)]/20 bg-gradient-to-br from-[var(--re-brand)]/5 to-cyan-600/5">
            <h3 className="font-serif text-xl font-bold text-[var(--re-text-primary)] mb-4">
              Ready to assess your FDA food traceability readiness?
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-8">
              Use RegEngine's tools to understand your requirements and plan your implementation.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/tools/ftl-checker"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px] max-w-fit"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Check Your FTL Coverage</span>
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
