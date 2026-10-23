import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight, BookOpen, Leaf, Database, CheckSquare, Users, FileText, BarChart3, Clock, Tag } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { BLOG_POST_TITLES, type BlogPostSlug } from '@/lib/blog-posts';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
  title: 'Blog: FSMA 204 Compliance Guides | RegEngine',
  description: 'Learn about FSMA 204 compliance, food traceability software, CTEs, KDEs, and how to prepare for FDA food traceability deadlines.',
  openGraph: {
    url: 'https://regengine.co/blog',
    siteName: 'RegEngine',
    title: 'Blog: FSMA 204 Compliance Guides | RegEngine',
    description: 'Learn about FSMA 204 compliance, food traceability software, CTEs, KDEs, and how to prepare for FDA food traceability deadlines.',
    type: 'website',
  },
};

type BlogPost = {
  slug: BlogPostSlug;
  excerpt: string;
  icon: LucideIcon;
  date: string;
  readTime: string;
};

// Slugs are typed against BLOG_POST_SLUGS so a post added here without being
// added to the shared list (and therefore the sitemap) fails typecheck.
// Titles live in that shared list too — the social cards render from them.
const BLOG_POSTS: BlogPost[] = [
  {
    slug: 'fsma-204-compliance-guide',
    excerpt: 'What is FSMA 204? Requirements, deadlines, Critical Tracking Events, and what your food business needs to do to comply.',
    icon: BookOpen,
    date: 'April 2026',
    readTime: '8 min read',
  },
  {
    slug: 'fsma-204-mid-market-guide',
    excerpt: 'How mid-market companies (10-500 employees) navigate FSMA 204 without disrupting operations or breaking the budget.',
    icon: Users,
    date: 'April 2026',
    readTime: '10 min read',
  },
  {
    slug: 'fda-food-traceability-requirements',
    excerpt: 'Understand FDA requirements, FTL products, CTEs, KDEs, and the 24-hour response requirement in detail.',
    icon: FileText,
    date: 'April 2026',
    readTime: '11 min read',
  },
  {
    slug: 'fsma-204-compliance-checklist-2026',
    excerpt: 'A step-by-step checklist to prepare for FSMA 204. What to do now before the July 2028 deadline.',
    icon: CheckSquare,
    date: 'April 2026',
    readTime: '9 min read',
  },
  {
    slug: 'regengine-vs-spreadsheets-traceability',
    excerpt: 'Why spreadsheets fail at FSMA 204 compliance and how RegEngine solves the audit trail, scale, and 24-hour response problems.',
    icon: BarChart3,
    date: 'April 2026',
    readTime: '8 min read',
  },
  {
    slug: 'food-traceability-software',
    excerpt: 'Evaluate food traceability platforms by capability, integration, compliance coverage, and total cost of ownership.',
    icon: Database,
    date: 'April 2026',
    readTime: '10 min read',
  },
  {
    slug: 'fsma-204-cte-kde-guide',
    excerpt: 'Deep dive into the 7 Critical Tracking Events and Key Data Elements your system needs to capture.',
    icon: Leaf,
    date: 'April 2026',
    readTime: '12 min read',
  },
  {
    slug: 'fsma-204-traceability-lot-codes',
    excerpt: 'Learn how to assign, track, and maintain Traceability Lot Codes under FSMA 204. Covers TLC requirements, best practices, and common mistakes for food businesses.',
    icon: Tag,
    date: 'March 2026',
    readTime: '7 min read',
  },
  {
    slug: '24-hour-rule',
    excerpt: 'The FDA can request your traceability records within 24 hours of a recall or outbreak. Learn what records you need, how to organize them, and how to respond in time.',
    icon: Clock,
    date: 'March 2026',
    readTime: '6 min read',
  },
];

export default function BlogPage() {
  return (
    <div className="bg-re-surface-base">
      {/* Hero */}
      <Container width="marketing" className="pt-12 sm:pt-16">
        <PageHeader
          size="hero"
          eyebrow="FSMA 204 Resources"
          title="FSMA 204 Compliance Resources for Food Businesses"
          description="Learn the fundamentals of FDA food traceability rules, food safety compliance software, and how to prepare your business for the July 2028 deadline."
          className="border-b-0 pb-0"
        />
      </Container>

      {/* Blog list */}
      <Container width="marketing" className="pb-16 sm:pb-20">
        <ul className="border-t border-re-border-subtle">
          {BLOG_POSTS.map((post) => {
            const Icon = post.icon;
            return (
              <li key={post.slug} className="border-b border-re-border-subtle">
                <Link
                  href={`/blog/${post.slug}`}
                  className="group -mx-3 flex flex-col gap-2 rounded-md px-3 py-5 transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring sm:flex-row sm:items-start sm:gap-6 motion-reduce:transition-none"
                >
                  <Icon
                    className="mt-0.5 h-5 w-5 shrink-0 text-re-text-tertiary"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <h3 className="text-subheading text-re-text-primary sm:text-heading">
                      {BLOG_POST_TITLES[post.slug]}
                    </h3>
                    <p className="mt-1.5 max-w-[68ch] text-ui text-re-text-secondary">
                      {post.excerpt}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 sm:w-52 sm:justify-end">
                    <span className="font-mono text-label uppercase text-re-text-muted">{post.date}</span>
                    <span className="font-mono text-label uppercase text-re-text-muted">{post.readTime}</span>
                    <ArrowRight
                      className="h-4 w-4 shrink-0 text-re-text-tertiary transition-transform duration-120 group-hover:translate-x-0.5 motion-reduce:transition-none"
                      strokeWidth={1.75}
                      aria-hidden="true"
                    />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </Container>

      {/* CTA Section */}
      <Container width="marketing" className="pb-16 sm:pb-20">
        <Card padding="spacious">
          <div className="max-w-[600px]">
            <h2 className="font-display text-heading-lg text-re-text-primary">
              Need hands-on help?
            </h2>
            <p className="mt-4 text-body text-re-text-secondary">
              RegEngine helps turn supplier data into FSMA 204 traceability evidence in minutes, not months. Get your free readiness score and see what needs attention.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/retailer-readiness">
                  Get Your Readiness Score
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/fsma-204">Read Our FSMA 204 Guide</Link>
              </Button>
            </div>
          </div>
        </Card>
      </Container>
    </div>
  );
}
