import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, CheckCircle2, AlertCircle, ClipboardList, BarChart3, Shield } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { JSONLD } from '@/components/seo/json-ld';
import { blogPostingJsonLd } from '@/lib/blog-jsonld';

export const metadata: Metadata = {
  title: 'FSMA 204 Compliance Checklist for 2026: Actionable Steps for July 2028',
  description: 'A complete FSMA 204 compliance checklist for food businesses. What to do now to meet the July 2028 deadline and avoid FDA enforcement.',
  openGraph: {
    url: 'https://regengine.co/blog/fsma-204-compliance-checklist-2026',
    siteName: 'RegEngine',
    title: 'FSMA 204 Compliance Checklist for 2026: Actionable Steps for July 2028',
    description: 'A complete FSMA 204 compliance checklist for food businesses. What to do now to meet the July 2028 deadline and avoid FDA enforcement.',
    type: 'article',
  },
};

export default function FSMA204ComplianceChecklist() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={blogPostingJsonLd('fsma-204-compliance-checklist-2026', 'A complete FSMA 204 compliance checklist for food businesses. What to do now to meet the July 2028 deadline and avoid FDA enforcement.')} />
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-2 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          ← Back to Blog
        </Link>
        <PageHeader
          eyebrow="Action Steps"
          title="FSMA 204 Compliance Checklist for 2026: What to Do Now"
          description="A step-by-step checklist to prepare your food business for the July 2028 FSMA 204 deadline."
          meta={
            <>
              <span>April 2026</span>
              <span>9 min read</span>
            </>
          }
        />
        <div>
          {/* Introduction */}
          <div className="mb-10">
            <p className="text-body text-re-text-secondary mb-6">
              Current public FDA posture points to July 20, 2028 as the earliest enforcement date under congressional direction. That may sound like a long way off, but implementation typically takes 6-18 months depending on your business complexity. The difference between companies that start now and those that wait is the difference between smooth adoption and a last-minute scramble.
            </p>
            <p className="text-body text-re-text-secondary">
              This checklist breaks FSMA 204 compliance into manageable phases. Use it to track your progress, identify gaps, and keep your team aligned. Work through these items over the next 24 months, and you'll be ready well before the deadline.
            </p>
          </div>

          {/* Phase 1 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6 mt-12">
              Phase 1: Assessment (Now - Q2 2026)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Before you can implement FSMA 204, you need to understand your current state. This phase answers the critical question: "Where are we today?"
            </p>
            <div className="space-y-4 mb-8">
              {[
                { task: 'Review the FDA\'s Food Traceability List (FTL)', detail: 'Determine which of your products require FSMA 204 compliance', done: false },
                { task: 'Audit your current data collection', detail: 'Map what traceability data you currently capture at each step of your supply chain', done: false },
                { task: 'Identify gaps in your data', detail: 'Which Critical Tracking Events (CTEs) are you missing? Which Key Data Elements (KDEs) do you need to start collecting?', done: false },
                { task: 'Document your supply chain', detail: 'List all suppliers, distributors, and customers. Where does data flow today?', done: false },
                { task: 'Assess your IT systems', detail: 'What ERP, WMS, or other systems do you use? Can they be integrated with a traceability platform?', done: false },
                { task: 'Estimate implementation cost and timeline', detail: 'Get quotes from 2-3 FSMA 204 platform vendors. Build a budget for 2026-2027', done: false },
                { task: 'Assign a compliance lead', detail: 'Designate one person to own FSMA 204 implementation. This is a significant role, so don\'t dilute it', done: false },
              ].map((item, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-1 h-4 w-4 flex-none rounded-full border border-re-border-strong" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {item.task}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {item.detail}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Phase 2 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Phase 2: Planning & Selection (Q2-Q3 2026)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Now that you understand your current state, it's time to plan your path forward and select the tools you'll use.
            </p>
            <div className="space-y-4 mb-8">
              {[
                { task: 'Define your CTEs and KDEs', detail: 'For each product line or business unit, document exactly which CTEs apply and what KDEs you need to capture', done: false },
                { task: 'Standardize your Traceability Lot Code (TLC)', detail: 'Create a consistent format for TLCs across your business. Document how to generate and track them', done: false },
                { task: 'Choose a compliance platform', detail: 'Select a FSMA 204 platform (RegEngine, others) or decide to build in-house. Secure executive approval and budget', done: false },
                { task: 'Draft a supplier/customer data template', detail: 'Create a simple form or format for suppliers to submit traceability data to you. Test with 2-3 key suppliers', done: false },
                { task: 'Plan your 24-hour response process', detail: 'Document how you\'ll retrieve and report traceability data to the FDA within 24 hours. Who does what? What systems involved?', done: false },
                { task: 'Get IT and Operations buy-in', detail: 'Brief your IT and Operations teams on what\'s coming. Identify integration points and resource needs', done: false },
                { task: 'Identify regulatory and audit requirements', detail: 'Do you need to update your Food Safety Plan? Audit procedures? Documentation requirements?', done: false },
              ].map((item, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-1 h-4 w-4 flex-none rounded-full border border-re-border-strong" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {item.task}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {item.detail}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Phase 3 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Phase 3: Pilot & Implementation (Q3 2026 - Q1 2027)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              This is where FSMA 204 goes live. Start with a pilot, validate, then scale.
            </p>
            <div className="space-y-4 mb-8">
              {[
                { task: 'Select a pilot product line', detail: 'Choose one high-volume or high-risk FTL product to start with. It should be representative of your broader operations', done: false },
                { task: 'Set up the traceability platform', detail: 'Install and configure your chosen platform. Test all integrations with your ERP/WMS', done: false },
                { task: 'Train your team', detail: 'Conduct hands-on training with warehouse, production, and logistics teams. Make sure they understand what data to capture and why', done: false },
                { task: 'Enable supplier data submission', detail: 'Give your key suppliers access to your data template. Test data submissions from at least 3-5 major suppliers', done: false },
                { task: 'Run a 24-hour response test', detail: 'Pick a product lot and simulate an FDA records request. Can you generate a complete response in under 24 hours? Under 1 hour?', done: false },
                { task: 'Identify and fix gaps', detail: 'Review your test results. What data is missing? What processes are slow? Fix these before rolling out broadly', done: false },
                { task: 'Document your standard operating procedures (SOPs)', detail: 'Write step-by-step guides for how to capture CTEs, generate TLCs, handle recalls, etc. Make these available to your team', done: false },
              ].map((item, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-1 h-4 w-4 flex-none rounded-full border border-re-border-strong" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {item.task}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {item.detail}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Phase 4 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Phase 4: Scale & Hardening (Q1-Q2 2027)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Roll out FSMA 204 traceability work to all applicable product lines and refine your processes for consistent, reliable records.
            </p>
            <div className="space-y-4 mb-8">
              {[
                { task: 'Roll out to all FTL products', detail: 'Extend your traceability system to all products on the FDA\'s Food Traceability List', done: false },
                { task: 'Onboard all suppliers and customers', detail: 'Ensure every significant supplier is submitting traceability data. Ensure every customer can receive your data if requested', done: false },
                { task: 'Conduct full 24-hour response drills', detail: 'Simulate FDA records requests for multiple products, scenarios, and business units. Measure your response time. Target: under 2 hours', done: false },
                { task: 'Test data retention and archival', detail: 'Verify that you can retrieve traceability records from 2 years ago. Test your backup and recovery procedures', done: false },
                { task: 'Conduct compliance audits', detail: 'Use a third-party auditor or consultant to validate your FSMA 204 readiness. Address any findings', done: false },
                { task: 'Update your Food Safety Plan', detail: 'Incorporate FSMA 204 compliance into your formal Food Safety Plan and risk management documentation', done: false },
              ].map((item, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-1 h-4 w-4 flex-none rounded-full border border-re-border-strong" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {item.task}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {item.detail}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Phase 5 */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Phase 5: Maintenance & Readiness (Q2 2027 - July 2028)
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Once you reach compliance, the focus shifts to maintaining your system and staying ready for the deadline.
            </p>
            <div className="space-y-4 mb-8">
              {[
                { task: 'Monitor system performance', detail: 'Track response times, error rates, and data quality. Address issues promptly', done: false },
                { task: 'Run quarterly compliance drills', detail: 'Continue to test your 24-hour response capability at least once per quarter', done: false },
                { task: 'Keep traceability records current', detail: 'Ensure all new products are assigned appropriate CTEs and KDEs. Remove obsolete products from your system', done: false },
                { task: 'Stay informed of FDA updates', detail: 'Subscribe to FDA updates and FSMA 204 guidance. Make any necessary adjustments to your system or procedures', done: false },
                { task: 'Conduct annual training', detail: 'Refresh training for all staff involved in data capture. Bring in new team members as needed', done: false },
                { task: 'Maintain supplier relationships', detail: 'Keep communication open with suppliers. Make sure they continue to submit accurate, timely traceability data', done: false },
                { task: 'Target readiness before July 20, 2028', detail: 'Your FSMA 204 traceability workflow is live, tested, and ready for operator review before enforcement resumes', done: false },
              ].map((item, idx) => (
                <Card key={idx} variant="inset" padding="compact" className="flex gap-4 hover:border-re-border-strong transition-colors duration-120 motion-reduce:transition-none">
                  <div className="flex-shrink-0">
                    <div aria-hidden="true" className="mt-1 h-4 w-4 flex-none rounded-full border border-re-border-strong" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1">
                      {item.task}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {item.detail}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Quick Tools Reference */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              RegEngine Tools to Support Your Checklist
            </h2>
            <p className="text-body text-re-text-secondary mb-8">
              Use these free tools throughout your compliance journey:
            </p>
            <div className="space-y-4 mb-8">
              {[
                {
                  name: 'FTL Coverage Checker',
                  desc: 'Verify which of your products are on the FDA\'s Food Traceability List',
                  phase: 'Phase 1',
                  link: '/tools/ftl-checker',
                },
                {
                  name: 'CTE Mapper',
                  desc: 'Map Critical Tracking Events for your supply chain and operations',
                  phase: 'Phase 2',
                  link: '/tools/cte-mapper',
                },
                {
                  name: 'KDE Checker',
                  desc: 'Verify that you\'re capturing all required Key Data Elements',
                  phase: 'Phase 3',
                  link: '/tools/kde-checker',
                },
                {
                  name: 'Readiness Assessment',
                  desc: 'Get a free assessment of your FSMA 204 readiness. Find your gaps and next steps',
                  phase: 'Any Phase',
                  link: '/retailer-readiness',
                },
                {
                  name: 'Records Request Checklist',
                  desc: 'A self reported checklist for an FDA records request. Not a 24 hour test and not a readiness score.',
                  phase: 'Phase 3-4',
                  link: '/tools/records-request-checklist',
                },
                {
                  name: 'Recall drill (Preview)',
                  desc: 'Run FDA records request drills to validate your 24-hour response capability',
                  phase: 'Phase 4-5',
                  link: '/tools/drill-simulator',
                },
              ].map((tool, idx) => (
                <Link
                  key={idx}
                  href={tool.link}
                  className="flex gap-4 p-4 rounded-lg bg-re-surface-inset border border-re-border hover:border-re-border-strong transition-colors duration-120 group"
                >
                  <div className="flex-shrink-0">
                    <Shield className="h-4 w-4 text-re-text-tertiary mt-0.5 group-hover:scale-110 transition-transform duration-120" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <div className="flex-grow">
                    <h4 className="text-subheading text-re-text-primary mb-1 group-hover:text-re-brand transition-colors duration-120">
                      {tool.name}
                    </h4>
                    <p className="text-ui text-re-text-secondary">
                      {tool.desc}
                    </p>
                  </div>
                  <div className="text-xs font-medium text-re-brand whitespace-nowrap ml-2">
                    {tool.phase}
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Key Takeaways */}
          <div className="mb-12">
            <h2 className="text-heading text-re-text-primary mb-6">
              Your FSMA 204 Checklist Summary
            </h2>
            <ul className="space-y-3 text-body text-re-text-secondary">
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Start your assessment now. You have about 24 months to implement.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Work through the phases in order: Assess → Plan → Pilot → Scale → Maintain.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Pilot before you scale. Test your 24-hour response early and often.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Engage suppliers and customers throughout. FSMA 204 is not a solo effort.</span>
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="h-4 w-4 text-re-text-tertiary shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <span>Assign a compliance lead and get executive sponsorship. Make it a priority.</span>
              </li>
            </ul>
          </div>

          {/* CTA */}
          <Card padding="spacious">
            <h3 className="text-heading text-re-text-primary">
              Ready to work through your FSMA 204 checklist?
            </h3>
            <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
              Use RegEngine to track your progress, run compliance drills, and stay on schedule for July 2028.
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
