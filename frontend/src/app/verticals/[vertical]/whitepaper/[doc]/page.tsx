import Link from "next/link";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [
    { vertical: "food-safety", doc: "fsma-204" },
    { vertical: "energy", doc: "cip-013" },
  ];
};

const DOC_CONTENT: Record<
  string,
  {
    title: string;
    summary: string;
    ctaHref: string;
    ctaLabel: string;
  }
> = {
  "food-safety/fsma-204": {
    title: "FSMA 204 Compliance Playbook",
    summary:
      "Practical implementation sequence for traceability lot codes, CTE/KDE capture, and FDA request response workflows.",
    ctaHref: "/tools/drill-simulator",
    ctaLabel: "Run Recall Simulation",
  },
  "energy/cip-013": {
    title: "CIP-013 Supply Chain Risk Guide",
    summary:
      "Control mapping and supplier assurance framework for bulk electric system supply chain risk management.",
    ctaHref: "/docs/energy/nerc-cip",
    ctaLabel: "Open NERC CIP Documentation",
  },
};

type PageProps = {
  params: Promise<{ vertical: string; doc: string }>;
};

export default async function WhitepaperDocPage({ params }: PageProps) {
  const { vertical, doc } = await params;
  const content =
    DOC_CONTENT[`${vertical}/${doc}`] ?? {
      title: "Compliance Whitepaper",
      summary: "This document is available through the RegEngine resource library.",
      ctaHref: "/docs/fsma-204",
      ctaLabel: "View FSMA 204 Guide",
    };

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[900px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Whitepaper</p>
        <h1 className="text-[clamp(30px,4vw,44px)] font-bold text-[var(--re-text-primary)] leading-tight">
          {content.title}
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] leading-relaxed">{content.summary}</p>

        <div className="mt-8 p-6 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <Link
            href={content.ctaHref}
            className="inline-flex items-center justify-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold"
          >
            {content.ctaLabel}
          </Link>
        </div>
      </section>
    </main>
  );
}
