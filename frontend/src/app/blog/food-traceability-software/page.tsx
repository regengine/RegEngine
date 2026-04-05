import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, TrendingUp, BarChart3, Zap } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Food Traceability Software: How to Choose the Right Solution | RegEngine',
  description: 'Evaluate food traceability platforms by capability, integration, compliance coverage, and total cost of ownership. A practical guide to selecting FSMA 204 software.',
  openGraph: {
    title: 'Food Traceability Software: How to Choose the Right Solution | RegEngine',
    description: 'Evaluate food traceability platforms by capability, integration, compliance coverage, and total cost of ownership. A practical guide to selecting FSMA 204 software.',
    type: 'website',
  },
};

export default function FoodTraceabilitySoftwarePage() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      {/* Back to Blog */}
      <div className="max-w-[900px] mx-auto px-4 sm:px-6 pt-8 pb-4">
        <Link href="/blog" className="inline-flex items-center gap-2 text-[var(--re-brand)] hover:text-[var(--re-brand)]/80 transition-colors text-sm font-medium">
          <ArrowRight className="w-4 h-4 rotate-180" />
          Back to Blog
        </Link>
      </div>

      {/* Hero Section */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <div className="mb-6">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-3">
            Food Traceability Platform Guide
          </p>
          <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold leading-[1.2] tracking-tight mb-4">
            Food Traceability Software: How to Choose the Right Solution
          </h1>
          <p className="text-lg text-[var(--re-text-secondary)] leading-relaxed mb-6 max-w-[700px]">
            Selecting a food traceability platform is one of the most critical decisions you'll make for FSMA 204 compliance. With dozens of vendors and competing feature sets, how do you know which one will actually work for your business?
          </p>
          <div className="flex flex-wrap gap-4 text-sm text-[var(--re-text-muted)]">
            <span>April 2026</span>
            <span>•</span>
            <span>10 min read</span>
          </div>
        </div>
      </section>

      {/* Main Content */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
        <article className="prose prose-invert max-w-none">
          {/* Section 1: The Selection Challenge */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">The Selection Challenge</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Food traceability software ranges from basic Excel-based tracking to enterprise-grade platforms with AI-powered supply chain visibility. Some vendors pitch themselves as FSMA 204 specialists. Others are generic supply chain tools retrofitted with compliance features. Many promise integration with your ERP—until you learn the integration costs $50K+ and takes six months.
            </p>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The problem: most vendor comparison tools are written by vendors. They highlight features that make their product look best, not features that matter most for your compliance deadline or your budget.
            </p>
            <p className="text-[var(--re-text-secondary)] leading-relaxed">
              This guide breaks down the four core evaluation criteria that food businesses should use to select a platform: capability alignment with FSMA 204, integration with existing systems, compliance feature depth, and total cost of ownership.
            </p>
          </div>

          {/* Section 2: Capability Alignment */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">1. Capability Alignment: Does It Solve Your Actual Problem?</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              The first evaluation criterion is straightforward: can the platform capture the data you actually need?
            </p>
            
            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)]" />
                Critical Tracking Event Capture
              </h3>
              <p className="text-[var(--re-text-secondary)] text-sm mb-4">
                Can the platform record all 7 CTEs specific to your commodity? Harvesting, Cooling, Initial Packing, Transformation, Shipping, Receiving, and First Land-Based Receiving have different data requirements. A platform that's optimized for Receiving but weak on Transformation might not fit a processor.
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-secondary)]">
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Ask: Which CTEs does your business execute?</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Request a demo focused on those specific CTEs</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Verify the platform captures all required Key Data Elements for each</span></li>
              </ul>
            </div>

            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-[var(--re-brand)]" />
                Scale to Your Business Size
              </h3>
              <p className="text-[var(--re-text-secondary)] text-sm mb-4">
                Enterprise platforms designed for 500+ SKUs become unwieldy for mid-size businesses. Conversely, small-business platforms won't scale if you're planning growth. Evaluate the platform's sweet spot.
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-secondary)]">
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Number of users and concurrent records</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>SKU and supplier capacity limits</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Multi-location and multi-facility support</span></li>
              </ul>
            </div>

            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-[var(--re-brand)]" />
                Audit-Ready Reporting
              </h3>
              <p className="text-[var(--re-text-secondary)] text-sm mb-4">
                FSMA 204 compliance isn't just about tracking events—it's about proving you did it. Ensure the platform generates audit-ready reports that FDA investigators will accept: traceback records showing product movement, deviation logs, verification records, and tamper-evident timestamps.
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-secondary)]">
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Automated traceback report generation</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Chain-of-custody documentation</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Data export in EPCIS 2.0 or FDA-accepted formats</span></li>
              </ul>
            </div>
          </div>

          {/* Section 3: Integration */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">2. Integration: Will It Connect to Your Existing Systems?</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              A food traceability platform doesn't live in isolation. It needs to pull data from your ERP, WMS, inventory system, or supplier networks—and push compliance data to FDA systems, retailers, or auditors.
            </p>
            
            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4">Integration Complexity Tiers</h3>
              <div className="space-y-4">
                <div>
                  <p className="font-semibold text-sm text-[var(--re-brand)] mb-1">Tier 1: Native Connectors (Low Cost)</p>
                  <p className="text-sm text-[var(--re-text-secondary)]">Pre-built integrations to popular ERPs (SAP, NetSuite, Salesforce). Usually $0–$5K setup, 2–4 weeks implementation.</p>
                </div>
                <div>
                  <p className="font-semibold text-sm text-[var(--re-brand)] mb-1">Tier 2: API-Based Integration (Medium Cost)</p>
                  <p className="text-sm text-[var(--re-text-secondary)]">RESTful or SOAP APIs requiring custom development. $10K–$30K, 4–8 weeks. Your IT team or a consultant builds the bridge.</p>
                </div>
                <div>
                  <p className="font-semibold text-sm text-[var(--re-brand)] mb-1">Tier 3: Manual Data Entry or Middleware (High Cost)</p>
                  <p className="text-sm text-[var(--re-text-secondary)]">No direct integration; data is manually entered or requires expensive middleware tools. $50K+, ongoing labor costs.</p>
                </div>
              </div>
            </div>

            <div className="bg-[rgba(168,85,247,0.1)] border border-[rgba(168,85,247,0.3)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-3 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-purple-400" />
                Red Flag: "We support integration"
              </h3>
              <p className="text-sm text-[var(--re-text-secondary)]">
                When a vendor says "we support integration," dig deeper. Ask: Is it a native connector or does it require custom development? What does implementation cost? How long does it take? How much ongoing maintenance is required? A vendor's vague answers often signal integration challenges ahead.
              </p>
            </div>

            <p className="text-[var(--re-text-secondary)] leading-relaxed">
              Evaluate your current tech stack and determine which integration tier you need. A small business using QuickBooks might be happy with manual CSV imports. A mid-market distributor using SAP needs a native connector or robust API layer.
            </p>
          </div>

          {/* Section 4: Compliance Coverage */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">3. Compliance Feature Depth: Does It Enforce FSMA 204 Requirements?</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Not all platforms enforce FSMA 204 compliance equally. Some are passive trackers—they record what you tell them to record. Better platforms actively enforce data validation, deviation tracking, and 24-hour response requirements.
            </p>

            <div className="space-y-4 mb-8">
              <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6">
                <h3 className="font-semibold text-[var(--re-text-primary)] mb-3">Data Validation and Standardization</h3>
                <p className="text-sm text-[var(--re-text-secondary)] mb-3">
                  FSMA 204 requires standardized data formats (GS1 codes, lot/traceability identifiers, location names). Does the platform enforce these standards or allow free-form entry? Enforcement prevents audit failures caused by inconsistent data.
                </p>
              </div>

              <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6">
                <h3 className="font-semibold text-[var(--re-text-primary)] mb-3">Deviation and Discrepancy Tracking</h3>
                <p className="text-sm text-[var(--re-text-secondary)] mb-3">
                  If a shipment arrives 6 hours late or with missing documentation, can the platform flag it as a deviation? Can you document and close deviations in accordance with your corrective action plan? This is critical for FDA audits.
                </p>
              </div>

              <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6">
                <h3 className="font-semibold text-[var(--re-text-primary)] mb-3">24-Hour Response Capability</h3>
                <p className="text-sm text-[var(--re-text-secondary)] mb-3">
                  FSMA 204 requires you to respond to FDA traceability requests within 24 hours. Does the platform generate compliant tracebacks automatically or do you need to manually compile them? Automation is non-negotiable at scale.
                </p>
              </div>

              <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6">
                <h3 className="font-semibold text-[var(--re-text-primary)] mb-3">Record Retention and Proof</h3>
                <p className="text-sm text-[var(--re-text-secondary)] mb-3">
                  FSMA 204 requires 2-year data retention with tamper-evident proof. Does the platform use cryptographic hashing or blockchain-style verification to prove records haven't been altered? This matters for audits.
                </p>
              </div>
            </div>

            <p className="text-[var(--re-text-secondary)] leading-relaxed">
              Ask vendors for evidence of these features. Request a demo or case study showing how their platform was used in a successful FDA inspection.
            </p>
          </div>

          {/* Section 5: Total Cost of Ownership */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">4. Total Cost of Ownership: What Will This Actually Cost?</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Food traceability software pricing ranges from $500/month for startups to $10K+/month for enterprise deployments. But the published price tag rarely tells the whole story.
            </p>

            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4">Hidden Costs to Factor In</h3>
              <ul className="space-y-3">
                <li className="flex gap-3">
                  <span className="text-[var(--re-brand)] font-semibold">Setup & Onboarding</span>
                  <span className="text-[var(--re-text-secondary)] text-sm">Configuration, data migration, user training: $5K–$50K depending on platform and complexity.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-[var(--re-brand)] font-semibold">Integration Development</span>
                  <span className="text-[var(--re-text-secondary)] text-sm">Connecting to your ERP or supplier systems: $10K–$100K+ if custom development is required.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-[var(--re-brand)] font-semibold">Per-User or Per-Transaction Fees</span>
                  <span className="text-[var(--re-text-secondary)] text-sm">Some platforms charge extra for each user account or charge per data record ingested. This scales unpredictably.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-[var(--re-brand)] font-semibold">Custom Development & Support</span>
                  <span className="text-[var(--re-text-secondary)] text-sm">Premium support tiers, custom reporting, or feature development: $100–$500/hour or flat retainers.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-[var(--re-brand)] font-semibold">Data Storage & Archival</span>
                  <span className="text-[var(--re-text-secondary)] text-sm">2-year retention for FSMA 204 compliance adds up; clarify if storage is included or charged separately.</span>
                </li>
              </ul>
            </div>

            <div className="bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-6 mb-6">
              <h3 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-[var(--re-brand)]" />
                ROI and Break-Even Analysis
              </h3>
              <p className="text-[var(--re-text-secondary)] text-sm mb-4">
                Good traceability software should pay for itself. Calculate the ROI by estimating:
              </p>
              <ul className="space-y-2 text-sm text-[var(--re-text-secondary)]">
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Time saved in compliance reporting and audits</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Reduced risk of fines or recalls</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Faster traceback response (24 hours instead of days)</span></li>
                <li className="flex gap-2"><span className="text-[var(--re-brand)]">•</span> <span>Improved supplier relationships and transparency</span></li>
              </ul>
              <p className="text-[var(--re-text-secondary)] text-sm mt-4">
                If the platform saves your team 5–10 hours/week in compliance work, that alone justifies the cost.
              </p>
            </div>

            <p className="text-[var(--re-text-secondary)] leading-relaxed">
              Request a detailed cost breakdown from every vendor. Ask for references—especially from companies of similar size—and ask them directly about hidden costs.
            </p>
          </div>

          {/* Section 6: The Selection Process */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">The Selection Process: A Practical Checklist</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Here's a step-by-step process to evaluate vendors:
            </p>
            
            <ol className="space-y-4 text-[var(--re-text-secondary)] mb-8">
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">1.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Define Your Requirements</p>
                  <p>List your CTEs, current systems, team size, and budget. This focuses vendor conversations.</p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">2.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Shortlist 3–5 Vendors</p>
                  <p>Request demos focused on your specific use cases, not generic feature tours.</p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">3.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Request Detailed Proposals</p>
                  <p>Include implementation timeline, full cost breakdown, integration requirements, and support terms.</p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">4.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Contact References</p>
                  <p>Speak to 2–3 companies using each platform. Ask about implementation reality vs. promises, hidden costs, and support quality.</p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">5.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Pilot or Trial Period</p>
                  <p>If possible, request a 30-day trial with real data from your business. This reveals integration friction early.</p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="font-bold text-[var(--re-brand)] flex-shrink-0">6.</span>
                <div>
                  <p className="font-semibold text-[var(--re-text-primary)] mb-1">Negotiate the Contract</p>
                  <p>With your preferred vendor, negotiate SLAs, implementation timelines, and penalties for missed compliance features.</p>
                </div>
              </li>
            </ol>
          </div>

          {/* Section 7: Key Takeaways */}
          <div className="mb-12 bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] rounded-lg p-8">
            <h2 className="text-xl font-bold mb-6 text-[var(--re-text-primary)]">Key Takeaways</h2>
            <ul className="space-y-3">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span className="text-[var(--re-text-secondary)]"><strong className="text-[var(--re-text-primary)]">Capability matters most.</strong> Choose a platform that captures your specific CTEs and generates audit-ready reports. Feature breadth is less important than depth in the areas you need.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span className="text-[var(--re-text-secondary)]"><strong className="text-[var(--re-text-primary)]">Integration costs are hidden costs.</strong> Factor in setup, development, and ongoing maintenance—not just monthly SaaS fees.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span className="text-[var(--re-text-secondary)]"><strong className="text-[var(--re-text-primary)]">Compliance enforcement beats passive tracking.</strong> A platform that enforces data standards, deviation tracking, and tamper-evident records will save you during audits.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span className="text-[var(--re-text-secondary)]"><strong className="text-[var(--re-text-primary)]">References are invaluable.</strong> Talk to customers using each platform. They'll tell you the truth about implementation timelines and hidden costs.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span className="text-[var(--re-text-secondary)]"><strong className="text-[var(--re-text-primary)]">You have time, but not much.</strong> With the July 2028 deadline, start evaluation now. The right platform will take 3–6 months to implement properly.</span>
              </li>
            </ul>
          </div>

          {/* Section 8: Next Steps */}
          <div className="mb-12">
            <h2 className="text-2xl font-bold mb-4 text-[var(--re-text-primary)]">Next Steps</h2>
            <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Selecting a food traceability platform is one of the most important decisions you'll make for FSMA 204 compliance. Take time to evaluate vendors thoroughly. A good platform will accelerate your compliance timeline and reduce risk. A poor fit will drain budget and cause delays.
            </p>
            <p className="text-[var(--re-text-secondary)] leading-relaxed">
              <Link href="/tools/ftl-checker" className="text-[var(--re-brand)] hover:text-[var(--re-brand)]/80 transition-colors font-semibold">
                Use our free FTL Compliance Checker
              </Link>
              {' '}to assess your current readiness. Then shortlist vendors and request demos based on the criteria in this guide.
            </p>
          </div>
        </article>
      </section>

      {/* CTA Section */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[var(--re-brand)]/10 to-cyan-600/5 p-8 sm:p-12 border border-[var(--re-brand)]/20">
          <div className="relative z-10 max-w-[600px]">
            <h2 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--re-text-primary)] mb-4">
              Ready to evaluate solutions?
            </h2>
            <p className="text-[var(--re-text-secondary)] mb-8 leading-relaxed">
              RegEngine automates the platform selection and implementation process. We ingest your supplier data, verify compliance, and export audit-ready records in days, not months.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px]"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">See How RegEngine Compares</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/blog"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                Read More Resources
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
