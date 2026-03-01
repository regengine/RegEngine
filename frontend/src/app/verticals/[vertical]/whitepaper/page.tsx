import Link from "next/link";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [
    { vertical: "food-safety" },
    { vertical: "energy" },
    { vertical: "healthcare" },
  ];
};

const WHITEPAPER_DOCS: Record<string, Array<{ slug: string; title: string; href: string }>> = {
  "food-safety": [
    {
      slug: "fsma-204",
      title: "FSMA 204 Compliance Playbook",
      href: "/verticals/food-safety/whitepaper/fsma-204",
    },
  ],
  energy: [
    {
      slug: "cip-013",
      title: "CIP-013 Supply Chain Risk Guide",
      href: "/verticals/energy/whitepaper/cip-013",
    },
  ],
  healthcare: [
    {
      slug: "risk-baseline",
      title: "Healthcare Compliance Baseline",
      href: "/resources/whitepapers",
    },
  ],
};

type PageProps = {
  params: Promise<{ vertical: string }>;
};

export default async function WhitepaperListPage({ params }: PageProps) {
  const { vertical } = await params;
  const docs = WHITEPAPER_DOCS[vertical] ?? WHITEPAPER_DOCS["food-safety"];

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[920px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Whitepapers</p>
        <h1 className="text-[clamp(30px,4vw,44px)] font-bold text-[var(--re-text-primary)] leading-tight">
          {vertical.replace("-", " ")} research library
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] leading-relaxed">
          Download implementation guidance and regulatory strategy notes for this vertical.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-3">
          {docs.map((doc) => (
            <Link
              key={doc.slug}
              href={doc.href}
              className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] hover:border-[var(--re-brand-muted)] transition-colors"
            >
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">{doc.title}</p>
              <p className="text-xs text-[var(--re-text-muted)] mt-1">Open document</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
