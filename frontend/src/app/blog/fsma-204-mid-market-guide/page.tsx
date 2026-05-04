import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, Leaf, Users, Zap } from 'lucide-react';

export const metadata: Metadata = {
  title: 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
  description: 'Mid-market food companies (10-500 employees) face unique FSMA 204 challenges. Learn how to implement traceability without overwhelming your operations.',
  openGraph: {
    title: 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
    description: 'Mid-market food companies (10-500 employees) face unique FSMA 204 challenges. Learn how to implement traceability without overwhelming your operations.',
    type: 'article',
  },
};

export default function FSMA204MidMarketGuide() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* Hero */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-8 sm:pb-12">
        <div className="mb-8">
          <Link
            href="/blog"
            className="inline-flex items-center gap-2 text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors duration-200 text-sm font-medium mb-6"
          >
            ← Back to Blog
          </Link>
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
            FSMA 204 for Growing Companies
          </p>
          <h1 className="font-serif text-[clamp(2rem,5vw,3rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight mb-6">
            FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies
          </h1>
          <p className="text-[1.1rem] text-[var(--re-text-secondary)] leading-relaxed mb-4">
            How mid-market food companies navigate FSMA 204 without disrupting operations.
          </p>
          <div className="flex gap-6 text-sm text-[var(--re-text-muted)] pt-4 border-t border-[var(--re-surface-border)]">
            <span>April 2026</span>
            <span>10 min read</span>
          </div>
        </div>
      </section>

      {/* Content */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <article className="prose max-w-none prose-headings:text-[var(--re-text-primary)] prose-p:text-[var(--re-text-secondary)] prose-strong:text-[var(--re-text-primary)] prose-li:text-[var(--re-text-secondary)] prose-a:text-[var(--re-brand)]">
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-6">
              Mid-market food companies—those with 10 to 500 employees—occupy a unique position in the food supply chain. You're large enough that spreadsheets and manual processes are breaking down. You're small enough that you can't afford the enterprise-scale compliance platforms built for Fortune 500 companies. And you're caught in the middle: complex enough to have multiple suppliers and customers, but lean enough that compliance can't become a full-time job for an entire team.
            </p>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              FSMA 204 compliance by July 2028 is non-negotiable. But implementing it right—efficiently, affordably, and without grinding your operations to a halt—requires a different approach than either a small startup or a multinational corporation. This guide walks mid-market food businesses through the unique challenges you face and practical strategies to meet FSMA 204 requirements.
            </p>
          </div>

          {/* The Mid-Market Challenge */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6 mt-12">
              The Mid-Market Challenge: Too Big for Spreadsheets, Too Small for Enterprise
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              Mid-market companies face a specific set of obstacles that don't affect smaller or larger competitors:
            </p>
            <div className="space-y-5 mb-8">
              {[
                {
                  name: 'Complex Supply Networks',
                  desc: 'You have multiple suppliers, multiple distribution channels, and multiple SKUs. Manual data collection breaks at this scale.',
                },
                {
                  name: 'Legacy Systems',
                  desc: 'You likely have an ERP, but it wasn\'t designed for FSMA 204. Integration is complex without API support.',
                },
                {
                  name: 'Lean Operations Teams',
                  desc: 'You can\'t hire five full-time compliance staff. You need automation to do the heavy lifting.',
                },
                {
                  name: 'Cost Constraints',
                  desc: 'Enterprise platforms cost $100K+ annually. You need a platform that doesn\'t break your budget.',
                },
                {
                  name: 'Supply Chain Collaboration',
                  desc: 'Your suppliers and customers need to share data with you. They\'re on different systems. Integration is messy.',
                },
              ].map((challenge, idx) => (
                <div
                  key={idx}
                  className="flex gap-4 p-4 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/30 transition-colors duration-200"
                >
                  <div className="flex-shrink-0">
                    <AlertCircle className="w-5 h-5 text-[var(--re-brand)] mt-0.5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-[var(--re-text-primary)] mb-1">
                      {challenge.name}
                    </h4>
                    <p className="text-sm text-[var(--re-text-secondary)]">
                      {challenge.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Build vs Buy */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Build vs. Buy: The Mid-Market Decision
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              At a certain scale, you face a critical decision: should you build your own FSMA 204 system in-house, or buy an off-the-shelf platform?
            </p>
            <div className="space-y-6 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-[var(--re-brand)]" />
                  Building In-House
                </h4>
                <div className="space-y-3 text-[var(--re-text-secondary)] text-sm mb-4">
                  <p className="font-medium text-[var(--re-text-primary)]">Pros:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Perfect fit for your specific workflow</li>
                    <li>• Full control over your data and roadmap</li>
                    <li>• No ongoing vendor dependency</li>
                  </ul>
                  <p className="font-medium text-[var(--re-text-primary)] pt-2">Cons:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• 4-8 months of development time</li>
                    <li>• 2-3 engineering FTEs required</li>
                    <li>• Ongoing maintenance and FDA regulatory updates</li>
                    <li>• Total cost: $300K-$600K+ by July 2028</li>
                  </ul>
                </div>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-4 flex items-center gap-2">
                  <Users className="w-5 h-5 text-[var(--re-brand)]" />
                  Buying a Platform
                </h4>
                <div className="space-y-3 text-[var(--re-text-secondary)] text-sm mb-4">
                  <p className="font-medium text-[var(--re-text-primary)]">Pros:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Ready in weeks, not months</li>
                    <li>• Vendor manages FDA compliance updates</li>
                    <li>• Built-in best practices and integrations</li>
                    <li>• Lower total cost of ownership</li>
                  </ul>
                  <p className="font-medium text-[var(--re-text-primary)] pt-2">Cons:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Workflow compromise—features may not fit perfectly</li>
                    <li>• Vendor lock-in (data portability concerns)</li>
                    <li>• Ongoing licensing costs ($5K-$50K annually)</li>
                  </ul>
                </div>
              </div>
            </div>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              For most mid-market companies, buying a purpose-built FSMA 204 platform is the better path. You get faster time-to-compliance, lower risk, and better total cost of ownership. Focus your engineering team on your core product, not compliance infrastructure.
            </p>
          </div>

          {/* Implementation Roadmap */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Mid-Market Implementation Roadmap
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              Here's a realistic timeline for mid-market companies to implement FSMA 204 compliance without disrupting core operations:
            </p>
            <div className="space-y-6 mb-8">
              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  Q2-Q3 2026: Assessment & Planning (3 months)
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm pl-4">
                  <li>• Audit current data capture across your supply chain</li>
                  <li>• Map CTEs and KDEs for your products and operations</li>
                  <li>• Identify system integration requirements (ERP, WMS, supplier systems)</li>
                  <li>• Evaluate platform options and get implementation quotes</li>
                  <li>• Assign a compliance lead (1 FTE, can be shared role)</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  Q3-Q4 2026: Pilot & Integration (4 months)
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm pl-4">
                  <li>• Begin platform implementation with IT and operations</li>
                  <li>• Set up initial data capture workflows for one product line</li>
                  <li>• Test supplier/customer data exchange</li>
                  <li>• Start training warehouse and production staff</li>
                  <li>• Run mock 24-hour FDA response drills</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  Q1 2027: Scale & Refinement (6 months)
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm pl-4">
                  <li>• Roll out to all FTL product lines</li>
                  <li>• Integrate with all major suppliers and customers</li>
                  <li>• Refine processes based on pilot learnings</li>
                  <li>• Conduct enterprise-wide training</li>
                  <li>• Perform full-chain compliance validation</li>
                </ul>
              </div>

              <div className="p-6 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)]">
                <h4 className="font-semibold text-[var(--re-text-primary)] mb-3">
                  Q3 2027-Q2 2028: Hardening & Readiness (12 months)
                </h4>
                <ul className="space-y-2 text-[var(--re-text-secondary)] text-sm pl-4">
                  <li>• Lock in final CTE/KDE definitions</li>
                  <li>• Achieve consistent 24-hour response times</li>
                  <li>• Complete FDA audit readiness checks</li>
                  <li>• Document all compliance processes</li>
                  <li>• Go-live by July 20, 2028</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Critical Success Factors */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Critical Success Factors for Mid-Market Implementation
            </h2>
            <div className="space-y-5 mb-8">
              {[
                {
                  title: 'Executive Sponsorship',
                  desc: 'FSMA 204 compliance requires cross-functional alignment. Your CFO, COO, and Chief Operations team need to prioritize it.',
                },
                {
                  title: 'Dedicated Compliance Lead',
                  desc: 'Assign 1 FTE to own FSMA 204 compliance. This person coordinates with operations, IT, suppliers, and your software vendor.',
                },
                {
                  title: 'Tight Vendor Integration',
                  desc: 'Choose a platform vendor that understands mid-market constraints and will work closely with your team during implementation.',
                },
                {
                  title: 'Supplier Collaboration',
                  desc: 'You can\'t achieve compliance alone. Give suppliers clear data requirements and templates. Use the platform to simplify their participation.',
                },
                {
                  title: 'Early Testing & Iteration',
                  desc: 'Run 24-hour response drills early and often. Refine your data capture based on what you learn.',
                },
              ].map((factor, idx) => (
                <div
                  key={idx}
                  className="flex gap-4 p-4 rounded-lg bg-[var(--re-surface-secondary)] border border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/30 transition-colors duration-200"
                >
                  <div className="flex-shrink-0">
                    <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] mt-0.5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-[var(--re-text-primary)] mb-1">
                      {factor.title}
                    </h4>
                    <p className="text-sm text-[var(--re-text-secondary)]">
                      {factor.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Evaluating Platforms */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              How to Evaluate FSMA 204 Platforms for Mid-Market
            </h2>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
              When comparing platforms, focus on these mid-market priorities:
            </p>
            <ul className="space-y-3 mb-8 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>ERP/WMS Integration</strong> — Does it connect to your existing systems without expensive consulting?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Supplier Portal</strong> — Can your suppliers easily submit traceability data without needing accounts?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Real-Time Response</strong> — Can you generate a 24-hour response in under 10 minutes?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Pricing Predictability</strong> — No per-user or per-transaction fees. Fixed annual cost that scales with your business.
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Implementation Support</strong> — Does the vendor provide onboarding, training, and compliance validation?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Data Portability</strong> — Can you export your data in open formats if you ever need to switch vendors?
                </span>
              </li>
            </ul>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="font-serif text-2xl font-bold text-[var(--re-text-primary)] mb-6">
              Key Takeaways for Mid-Market
            </h2>
            <ul className="space-y-3 text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed">
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Mid-market companies face unique challenges: complex supply chains, legacy systems, lean teams, and cost constraints.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>For most mid-market companies, buying a purpose-built platform is faster and more cost-effective than building in-house.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Plan for 18-24 months of implementation, starting now. Early assessment and pilot are critical.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Supplier collaboration is non-negotiable. Choose a platform that makes it easy for them to participate.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <span>Assign a dedicated compliance lead and get executive sponsorship. FSMA 204 is a business priority, not just an IT project.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <div className="p-8 sm:p-12 rounded-xl border border-[var(--re-brand)]/20 bg-gradient-to-br from-[var(--re-brand)]/5 to-cyan-600/5">
            <h3 className="font-serif text-xl font-bold text-[var(--re-text-primary)] mb-4">
              Ready to assess your mid-market FSMA 204 readiness?
            </h3>
            <p className="text-[var(--re-text-secondary)] mb-8">
              RegEngine is built for mid-market companies. See how far you are from compliance and what you need to do.
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
