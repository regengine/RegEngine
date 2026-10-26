import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Shield } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = {
  title: "RegEngine Comparisons: FSMA 204 Compliance",
  description:
    "Compare RegEngine with FoodLogiQ (Aptean), ReposiTrak, and TraceGains for FSMA 204 compliance.",
  alternates: {
    canonical: "https://regengine.co/compare",
  },
  openGraph: {
    title: "RegEngine Comparisons: FSMA 204 Compliance",
    description: "Compare RegEngine with FoodLogiQ (Aptean), ReposiTrak, and TraceGains for FSMA 204 compliance.",
    url: "https://regengine.co/compare",
    type: "website",
  },
};

// One entry per page under /compare. Summaries are taken from each page's own metadata.
const COMPARISONS = [
  {
    href: "/compare/foodlogiq",
    title: "RegEngine vs FoodLogiQ (Aptean)",
    desc: "See how self-serve setup, rule evaluation, and transparent pricing differ from enterprise-only deployment.",
  },
  {
    href: "/compare/repositrak",
    title: "RegEngine vs ReposiTrak",
    desc: "Deep rule validation vs retailer compliance tracking.",
  },
  {
    href: "/compare/tracegains",
    title: "RegEngine vs TraceGains",
    desc: "Supplier document management vs CTE-level traceability rule evaluation.",
  },
];

export default function CompareIndexPage() {
  return (
    <Container width="marketing" as="main" className="py-16">
      <PageHeader
        size="hero"
        className="mb-12"
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            Comparison
          </span>
        }
        title="Compare RegEngine"
        description="How RegEngine compares with other FSMA 204 traceability tools."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {COMPARISONS.map((item) => (
          <Card key={item.href} padding="default" className="p-5">
            <h2 className="mb-2 text-subheading text-re-text-primary">
              <Link href={item.href} className="inline-flex items-center gap-1.5 no-underline">
                {item.title} <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </h2>
            <p className="text-small leading-relaxed text-re-text-secondary">{item.desc}</p>
          </Card>
        ))}
      </div>
    </Container>
  );
}
