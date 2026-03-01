import Link from "next/link";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [
    { slug: ["automotive"] },
    { slug: ["automotive", "ppap"] },
    { slug: ["automotive", "lpa"] },
    { slug: ["automotive", "8d"] },
    { slug: ["construction"] },
    { slug: ["construction", "bim"] },
    { slug: ["construction", "safety"] },
    { slug: ["construction", "toolbox"] },
    { slug: ["gaming"] },
    { slug: ["gaming", "quickstart"] },
    { slug: ["gaming", "surveillance"] },
    { slug: ["gaming", "responsible-gaming"] },
    { slug: ["healthcare", "quickstart"] },
    { slug: ["healthcare", "risk-monitor"] },
    { slug: ["healthcare", "audit-export"] },
    { slug: ["technology", "quickstart"] },
    { slug: ["technology", "drift-detection"] },
    { slug: ["technology", "vendor-tracking"] },
    { slug: ["energy", "verification"] },
    { slug: ["energy", "incident"] },
  ];
};

type PageProps = {
  params: Promise<{ slug: string[] }>;
};

export default async function DocsCatchAllPage({ params }: PageProps) {
  const { slug } = await params;
  const section = slug.join(" /");

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[860px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Documentation</p>
        <h1 className="text-[clamp(30px,4vw,46px)] font-bold text-[var(--re-text-primary)] leading-tight">
          {section}
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] leading-relaxed">
          This documentation section is available through the primary API and implementation guides.
          Use the links below to continue without dead ends.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/docs/api" className="inline-flex items-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold">
            API Reference
          </Link>
          <Link href="/docs" className="inline-flex items-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
            Docs Home
          </Link>
        </div>
      </section>
    </main>
  );
}
