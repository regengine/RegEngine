import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Calendar, Clock } from "lucide-react";

export const metadata: Metadata = {
  title: "FSMA 204 Compliance Blog — Guides & Updates | RegEngine",
  description:
    "Practical guides for FSMA 204 compliance: traceability lot codes, the 24-hour rule, CTE requirements, and FDA enforcement updates.",
};

const POSTS = [
  {
    slug: "24-hour-rule",
    title: "The FSMA 204 24-Hour Rule: What It Really Means for Your Operation",
    excerpt:
      "The FDA can request your traceability records within 24 hours. Here's what that means in practice, what records you need ready, and how to avoid scrambling.",
    date: "2026-03-15",
    readTime: "6 min read",
  },
  {
    slug: "fsma-204-traceability-lot-codes",
    title: "FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide",
    excerpt:
      "Traceability Lot Codes are the backbone of FSMA 204. Learn how to assign, track, and maintain TLCs across your supply chain.",
    date: "2026-03-01",
    readTime: "8 min read",
  },
];

export default function BlogPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <div className="max-w-[900px] mx-auto px-6 py-16 md:py-24">
        {/* Header */}
        <h1
          className="text-3xl md:text-4xl font-bold mb-4"
          style={{ color: "var(--re-text-primary)" }}
        >
          FSMA 204 Compliance Blog
        </h1>
        <p
          className="text-lg mb-12"
          style={{ color: "var(--re-text-secondary)" }}
        >
          Practical guides to help food businesses meet FDA traceability
          requirements — written by compliance practitioners, not lawyers.
        </p>

        {/* Posts */}
        <div className="space-y-8">
          {POSTS.map((post) => (
            <Link
              key={post.slug}
              href={`/blog/${post.slug}`}
              className="block rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 md:p-8 transition-shadow hover:shadow-lg"
            >
              <div className="flex items-center gap-4 text-sm mb-3" style={{ color: "var(--re-text-muted)" }}>
                <span className="flex items-center gap-1">
                  <Calendar className="w-4 h-4" />
                  {new Date(post.date).toLocaleDateString("en-US", {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  {post.readTime}
                </span>
              </div>
              <h2
                className="text-xl md:text-2xl font-semibold mb-2"
                style={{ color: "var(--re-text-primary)" }}
              >
                {post.title}
              </h2>
              <p className="mb-4" style={{ color: "var(--re-text-secondary)" }}>
                {post.excerpt}
              </p>
              <span
                className="inline-flex items-center gap-1 text-sm font-medium"
                style={{ color: "var(--re-brand)" }}
              >
                Read article <ArrowRight className="w-4 h-4" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
