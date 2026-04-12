import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, BookOpen, Leaf, Database, CheckSquare, Users, FileText, BarChart3 } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Blog — FSMA 204 Compliance Guides | RegEngine',
  description: 'Learn about FSMA 204 compliance, food traceability software, CTEs, KDEs, and how to prepare for FDA food traceability deadlines.',
  openGraph: {
    title: 'Blog — FSMA 204 Compliance Guides | RegEngine',
    description: 'Learn about FSMA 204 compliance, food traceability software, CTEs, KDEs, and how to prepare for FDA food traceability deadlines.',
    type: 'website',
  },
};

const BLOG_POSTS = [
  {
    slug: 'fsma-204-compliance-guide',
    title: 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
    excerpt: 'What is FSMA 204? Requirements, deadlines, Critical Tracking Events, and what your food business needs to do to comply.',
    icon: BookOpen,
    date: 'April 2026',
    readTime: '8 min read',
  },
  {
    slug: 'fsma-204-mid-market-guide',
    title: 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
    excerpt: 'How mid-market companies (10-500 employees) navigate FSMA 204 without disrupting operations or breaking the budget.',
    icon: Users,
    date: 'April 2026',
    readTime: '10 min read',
  },
  {
    slug: 'fda-food-traceability-requirements',
    title: 'FDA Food Traceability Requirements: Complete Guide to FSMA 204 Rules',
    excerpt: 'Understand FDA requirements, FTL products, CTEs, KDEs, and the 24-hour response requirement in detail.',
    icon: FileText,
    date: 'April 2026',
    readTime: '11 min read',
  },
  {
    slug: 'fsma-204-compliance-checklist-2026',
    title: 'FSMA 204 Compliance Checklist for 2026: Actionable Steps for July 2028',
    excerpt: 'A step-by-step checklist to prepare for FSMA 204. What to do now before the July 2028 deadline.',
    icon: CheckSquare,
    date: 'April 2026',
    readTime: '9 min read',
  },
  {
    slug: 'regengine-vs-spreadsheets-traceability',
    title: 'RegEngine vs Spreadsheets: Why Food Companies Outgrow Excel for Traceability',
    excerpt: 'Why spreadsheets fail at FSMA 204 compliance and how RegEngine solves the audit trail, scale, and 24-hour response problems.',
    icon: BarChart3,
    date: 'April 2026',
    readTime: '8 min read',
  },
  {
    slug: 'food-traceability-software',
    title: 'Food Traceability Software: How to Choose the Right Platform',
    excerpt: 'Evaluate food traceability platforms by capability, integration, compliance coverage, and total cost of ownership.',
    icon: Database,
    date: 'April 2026',
    readTime: '10 min read',
  },
  {
    slug: 'fsma-204-cte-kde-guide',
    title: 'CTEs and KDEs Explained: A Practical Guide to FSMA 204 Data Requirements',
    excerpt: 'Deep dive into the 7 Critical Tracking Events and Key Data Elements your system needs to capture.',
    icon: Leaf,
    date: 'April 2026',
    readTime: '12 min read',
  },
];

export default function BlogPage() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">
      {/* Hero */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-12 sm:pb-16">
        <div className="max-w-[700px]">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-5">
            FSMA 204 Resources
          </p>
          <h1 className="font-serif text-[clamp(1.75rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
            FSMA 204 Compliance Resources for Food Businesses
          </h1>
          <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
            Learn the fundamentals of FDA food traceability rules, food safety compliance software, and how to prepare your business for the July 2028 deadline.
          </p>
        </div>
      </section>

      {/* Blog Grid */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {BLOG_POSTS.map((post) => {
            const Icon = post.icon;
            return (
              <Link
                key={post.slug}
                href={`/blog/${post.slug}`}
                className="group relative overflow-hidden rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-secondary)] transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:shadow-[0_8px_30px_rgba(16,185,129,0.15)] hover:-translate-y-1"
              >
                <div className="p-6 sm:p-8 flex flex-col h-full">
                  {/* Icon */}
                  <div className="mb-6">
                    <div className="w-12 h-12 rounded-lg bg-[var(--re-brand)]/10 flex items-center justify-center group-hover:bg-[var(--re-brand)]/20 transition-colors duration-300">
                      <Icon className="w-6 h-6 text-[var(--re-brand)]" />
                    </div>
                  </div>

                  {/* Content */}
                  <h3 className="text-lg sm:text-xl font-semibold text-[var(--re-text-primary)] mb-3 group-hover:text-[var(--re-brand)] transition-colors duration-300 line-clamp-3">
                    {post.title}
                  </h3>
                  <p className="text-[var(--re-text-secondary)] leading-relaxed mb-6 flex-grow line-clamp-2">
                    {post.excerpt}
                  </p>

                  {/* Meta */}
                  <div className="flex items-center justify-between pt-6 border-t border-[var(--re-surface-border)] group-hover:border-[var(--re-brand)]/30 transition-colors duration-300">
                    <div className="flex gap-4 text-xs text-[var(--re-text-muted)]">
                      <span>{post.date}</span>
                      <span>{post.readTime}</span>
                    </div>
                    <ArrowRight className="w-4 h-4 text-[var(--re-brand)] group-hover:translate-x-1 transition-transform duration-300" />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* CTA Section */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[var(--re-brand)]/10 to-cyan-600/5 p-8 sm:p-12 border border-[var(--re-brand)]/20">
          <div className="relative z-10 max-w-[600px]">
            <h2 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--re-text-primary)] mb-4">
              Need hands-on help?
            </h2>
            <p className="text-[var(--re-text-secondary)] mb-8 leading-relaxed">
              RegEngine automates FSMA 204 compliance in minutes, not months. Get your free readiness score and see what you need to do.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px]"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">Get Your Readiness Score</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/fsma-204"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                Read Our FSMA 204 Guide
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
