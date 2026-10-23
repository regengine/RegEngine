import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, Leaf, Users, Zap } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { JSONLD } from '@/components/seo/json-ld';
import { blogPostingJsonLd } from '@/lib/blog-jsonld';

export const metadata: Metadata = {
  title: 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
  description: 'Mid-market food companies (10-500 employees) face unique FSMA 204 challenges. Learn how to implement traceability without overwhelming your operations.',
  openGraph: {
    url: 'https://regengine.co/blog/fsma-204-mid-market-guide',
    siteName: 'RegEngine',
    title: 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
    description: 'Mid-market food companies (10-500 employees) face unique FSMA 204 challenges. Learn how to implement traceability without overwhelming your operations.',
    type: 'article',
  },
};

export default function FSMA204MidMarketGuide() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={blogPostingJsonLd('fsma-204-mid-market-guide', 'Mid-market food companies (10-500 employees) face unique FSMA 204 challenges. Learn how to implement traceability without overwhelming your operations.')} />
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-2 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          ← Back to Blog
        </Link>
        <PageHeader
          eyebrow="FSMA 204 for Growing Companies"
          title="FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies"
          description="How mid-market food companies navigate FSMA 204 without disrupting operations."
          meta={
            <>
              <span>April 2026</span>
              <span>10 min read</span>
            </>
          }
        />
        <div>
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-body text-re-text-secondary mb-6">
              Mid-market food companies (those with 10 to 500 employees) occupy a unique position in the food supply chain. You're large enough that spreadsheets and manual processes are breaking down. You're small enough that you can't afford the enterprise-scale compliance platforms built for Fortune 500 companies. And you're caught in the middle: complex enough to have multiple suppliers and customers, but lean enough that compliance can't become a full-time job for an entire team.
            </p>
            <p className="text-body text-re-text-secondary">
              FSMA 204 compliance by July 2028 is non-negotiable. But implementing it right (efficiently, affordably, and without grinding your operations to a halt) requires a different approach than either a small startup or a multinational corporation. This guide walks mid-market food businesses through the unique challenges you face and practical strategies to meet FSMA 204 requirements.
            </p>
          </div>

          {/* The Mid-Market Challenge */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6 mt-12">
              The Mid-Market Challenge: Too Big for Spreadsheets, Too Small for Enterprise
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
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
                <Card
                  key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <AlertCircle className="h-4 w-4 text-re-text-tertiary mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <div>
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {challenge.name}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {challenge.desc}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Build vs Buy */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Build vs. Buy: The Mid-Market Decision
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              At a certain scale, you face a critical decision: should you build your own FSMA 204 system in-house, or buy an off-the-shelf platform?
            </p>
            <div className="space-y-6 mb-8">
              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-4 flex items-center gap-2">
                  <Zap className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  Building In-House
                </h4>
                <div className="space-y-3 text-re-text-secondary text-sm mb-4">
                  <p className="text-subheading text-re-text-primary">Pros:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Perfect fit for your specific workflow</li>
                    <li>• Full control over your data and roadmap</li>
                    <li>• No ongoing vendor dependency</li>
                  </ul>
                  <p className="text-subheading text-re-text-primary pt-2">Cons:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• 4-8 months of development time</li>
                    <li>• 2-3 engineering FTEs required</li>
                    <li>• Ongoing maintenance and FDA regulatory updates</li>
                    <li>• Total cost: $300K-$600K+ by July 2028</li>
                  </ul>
                </div>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-4 flex items-center gap-2">
                  <Users className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  Buying a Platform
                </h4>
                <div className="space-y-3 text-re-text-secondary text-sm mb-4">
                  <p className="text-subheading text-re-text-primary">Pros:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Ready in weeks, not months</li>
                    <li>• Vendor manages FDA compliance updates</li>
                    <li>• Built-in best practices and integrations</li>
                    <li>• Lower total cost of ownership</li>
                  </ul>
                  <p className="text-subheading text-re-text-primary pt-2">Cons:</p>
                  <ul className="space-y-2 pl-4">
                    <li>• Workflow compromise: features may not fit perfectly</li>
                    <li>• Vendor lock-in (data portability concerns)</li>
                    <li>• Ongoing licensing costs ($5K-$50K annually)</li>
                  </ul>
                </div>
              </Card>
            </div>
            <p className="text-body text-re-text-secondary">
              For most mid-market companies, buying a purpose-built FSMA 204 platform is the better path. You get faster time-to-compliance, lower risk, and better total cost of ownership. Focus your engineering team on your core product, not compliance infrastructure.
            </p>
          </div>

          {/* Implementation Roadmap */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Mid-Market Implementation Roadmap
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Here's a realistic timeline for mid-market companies to implement FSMA 204 compliance without disrupting core operations:
            </p>
            <div className="space-y-6 mb-8">
              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  Q2-Q3 2026: Assessment & Planning (3 months)
                </h4>
                <ul className="space-y-2 text-re-text-secondary text-sm pl-4">
                  <li>• Audit current data capture across your supply chain</li>
                  <li>• Map CTEs and KDEs for your products and operations</li>
                  <li>• Identify system integration requirements (ERP, WMS, supplier systems)</li>
                  <li>• Evaluate platform options and get implementation quotes</li>
                  <li>• Assign a compliance lead (1 FTE, can be shared role)</li>
                </ul>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  Q3-Q4 2026: Pilot & Integration (4 months)
                </h4>
                <ul className="space-y-2 text-re-text-secondary text-sm pl-4">
                  <li>• Begin platform implementation with IT and operations</li>
                  <li>• Set up initial data capture workflows for one product line</li>
                  <li>• Test supplier/customer data exchange</li>
                  <li>• Start training warehouse and production staff</li>
                  <li>• Run mock 24-hour FDA response drills</li>
                </ul>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  Q1 2027: Scale & Refinement (6 months)
                </h4>
                <ul className="space-y-2 text-re-text-secondary text-sm pl-4">
                  <li>• Roll out to all FTL product lines</li>
                  <li>• Integrate with all major suppliers and customers</li>
                  <li>• Refine processes based on pilot learnings</li>
                  <li>• Conduct enterprise-wide training</li>
                  <li>• Perform full-chain compliance validation</li>
                </ul>
              </Card>

              <Card variant="inset" padding="spacious">
                <h4 className="text-subheading text-re-text-primary mb-3">
                  Q3 2027-Q2 2028: Hardening & Readiness (12 months)
                </h4>
                <ul className="space-y-2 text-re-text-secondary text-sm pl-4">
                  <li>• Lock in final CTE/KDE definitions</li>
                  <li>• Achieve consistent 24-hour response times</li>
                  <li>• Complete FDA-oriented record request drills</li>
                  <li>• Document all compliance processes</li>
                  <li>• Target operational readiness before July 20, 2028</li>
                </ul>
              </Card>
            </div>
          </div>

          {/* Critical Success Factors */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
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
                <Card
                  key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <CheckCircle2 className="h-4 w-4 text-re-text-tertiary mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <div>
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {factor.title}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {factor.desc}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Evaluating Platforms */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              How to Evaluate FSMA 204 Platforms for Mid-Market
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              When comparing platforms, focus on these mid-market priorities:
            </p>
            <ul className="space-y-3 mb-8 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>ERP/WMS Integration:</strong> Does it connect to your existing systems without expensive consulting?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>Supplier Portal:</strong> Can your suppliers easily submit traceability data without needing accounts?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>Real-Time Response:</strong> Can you generate a 24-hour response in under 10 minutes?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>Pricing Predictability:</strong> No per-user or per-transaction fees. Fixed annual cost that scales with your business.
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>Implementation Support:</strong> Does the vendor provide onboarding, training, and compliance validation?
                </span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  <strong>Data Portability:</strong> Can you export your data in open formats if you ever need to switch vendors?
                </span>
              </li>
            </ul>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Key Takeaways for Mid-Market
            </h2>
            <ul className="space-y-3 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Mid-market companies face unique challenges: complex supply chains, legacy systems, lean teams, and cost constraints.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>For most mid-market companies, buying a purpose-built platform is faster and more cost-effective than building in-house.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Plan for 18-24 months of implementation, starting now. Early assessment and pilot are critical. That timeline covers the full organization-wide compliance program (supplier onboarding, process changes, and data cleanup), while getting a traceability tool like RegEngine running takes days.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Supplier collaboration is non-negotiable. Choose a platform that makes it easy for them to participate.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Assign a dedicated compliance lead and get executive sponsorship. FSMA 204 is a business priority, not just an IT project.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <Card padding="spacious">
            <h3 className="text-heading text-re-text-primary">
              Ready to assess your mid-market FSMA 204 readiness?
            </h3>
            <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
              RegEngine is built for mid-market companies. See how far you are from compliance and what you need to do.
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
