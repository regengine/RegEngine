import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Clock, Hash } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export const metadata: Metadata = {
  title: 'Blog | RegEngine',
  description:
    'Practical guides to FSMA 204 compliance, food traceability, and FDA records requirements. Written for food safety professionals and developers.',
  openGraph: {
    title: 'Blog | RegEngine',
    description:
      'Practical guides to FSMA 204 compliance, food traceability, and FDA records requirements.',
    url: 'https://www.regengine.co/blog',
    type: 'website',
  },
  keywords: [
    'FSMA 204',
    'food traceability',
    'FDA compliance',
    'food safety blog',
    'traceability lot codes',
    'FDA 24 hour response',
  ],
};

const posts = [
  {
    slug: '24-hour-rule',
    title: 'The 24-Hour Rule: How Fast Must You Respond to an FDA Records Request?',
    description:
      'FSMA 204 requires you to produce traceability records within 24 hours of an FDA request. Most companies using spreadsheets take 3-7 days. Here is what a compliant response actually looks like.',
    icon: Clock,
    tags: ['FSMA 204', 'FDA Compliance', 'Records Requests'],
    date: '2026-03-27',
  },
  {
    slug: 'fsma-204-traceability-lot-codes',
    title: 'FSMA 204 Traceability Lot Codes (TLCs): The Complete Technical Guide',
    description:
      'A deep technical reference for Traceability Lot Codes under 21 CFR Part 1, Subpart S. Covers TLC assignment rules, GTIN structures, source references, and how TLCs flow through each Critical Tracking Event.',
    icon: Hash,
    tags: ['FSMA 204', 'Traceability Lot Codes', 'Technical Guide'],
    date: '2026-03-27',
  },
];

export default function BlogIndexPage() {
  return (
    <div className="re-page">
      {/* Header */}
      <div
        style={{
          borderBottom: `1px solid ${T.border}`,
          padding: '48px 24px',
          background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, transparent 50%)',
        }}
      >
        <div className="max-w-[900px] mx-auto">
          <h1 className="re-heading-xl mb-3">Blog</h1>
          <p style={{ color: T.textMuted, fontSize: '17px', maxWidth: '600px', lineHeight: 1.6 }}>
            Practical guides to FSMA 204 compliance, food traceability regulations, and building
            audit-ready systems. Written for food safety professionals and developers.
          </p>
        </div>
      </div>

      {/* Post Grid */}
      <div style={{ padding: T.sectionPadding }}>
        <div className="max-w-[900px] mx-auto grid gap-8 md:grid-cols-2">
          {posts.map((post) => {
            const Icon = post.icon;
            return (
              <Link
                key={post.slug}
                href={`/blog/${post.slug}`}
                style={{
                  display: 'block',
                  background: T.surface,
                  border: `1px solid ${T.border}`,
                  borderRadius: T.cardRadius,
                  padding: T.cardPadding,
                  textDecoration: 'none',
                  transition: 'border-color 0.2s, background 0.2s',
                }}
                className="hover:border-emerald-500/30 hover:bg-white/[0.03]"
              >
                <div className="flex items-center gap-2 mb-3">
                  <Icon className="w-5 h-5 text-emerald-500" />
                  <span style={{ color: T.textDim, fontSize: '13px' }}>{post.date}</span>
                </div>

                <h2
                  style={{
                    color: T.heading,
                    fontSize: '18px',
                    fontWeight: 600,
                    lineHeight: 1.4,
                    marginBottom: '12px',
                  }}
                >
                  {post.title}
                </h2>

                <p
                  style={{
                    color: T.textMuted,
                    fontSize: '14px',
                    lineHeight: 1.65,
                    marginBottom: '16px',
                  }}
                >
                  {post.description}
                </p>

                <div className="flex flex-wrap gap-2 mb-4">
                  {post.tags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        background: T.accentBg,
                        color: T.accent,
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: '4px',
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <span
                  className="flex items-center gap-1"
                  style={{ color: T.accent, fontSize: '14px', fontWeight: 500 }}
                >
                  Read more <ArrowRight className="w-4 h-4" />
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
