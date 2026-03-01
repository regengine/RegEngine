import Link from "next/link";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [{ vertical: "food-safety" }, { vertical: "energy" }, { vertical: "healthcare" }];
};

const VERTICAL_CONTENT: Record<
  string,
  {
    title: string;
    subtitle: string;
    focus: string;
    primaryHref: string;
    primaryLabel: string;
    secondaryHref: string;
    secondaryLabel: string;
  }
> = {
  "food-safety": {
    title: "Food Safety Compliance",
    subtitle: "FSMA 204 traceability readiness from supplier intake to FDA response export.",
    focus: "FTL coverage, CTE/KDE completeness, and recall response execution.",
    primaryHref: "/tools/ftl-checker",
    primaryLabel: "Run FTL Coverage Checker",
    secondaryHref: "/demo/recall-simulation",
    secondaryLabel: "Open Recall Simulation",
  },
  energy: {
    title: "Energy Compliance",
    subtitle: "Operational controls and documentation support for critical infrastructure teams.",
    focus: "NERC CIP workflows, evidence packaging, and control attestation.",
    primaryHref: "/docs/energy/nerc-cip",
    primaryLabel: "View NERC CIP Guide",
    secondaryHref: "/controls",
    secondaryLabel: "Open Controls Workspace",
  },
  healthcare: {
    title: "Healthcare Compliance",
    subtitle: "Program oversight for regulated healthcare operations and policy workflows.",
    focus: "Risk visibility, policy controls, and audit-ready reporting.",
    primaryHref: "/docs/healthcare",
    primaryLabel: "View Healthcare Docs",
    secondaryHref: "/dashboard/compliance",
    secondaryLabel: "Open Compliance Dashboard",
  },
};

type PageProps = {
  params: Promise<{ vertical: string }>;
};

export default async function VerticalPage({ params }: PageProps) {
  const { vertical } = await params;
  const content =
    VERTICAL_CONTENT[vertical] ??
    VERTICAL_CONTENT["food-safety"];

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[1040px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.12em] text-[var(--re-brand)] mb-3">Vertical Overview</p>
        <h1 className="text-[clamp(32px,4.2vw,48px)] font-bold leading-tight text-[var(--re-text-primary)] max-w-[760px]">
          {content.title}
        </h1>
        <p className="mt-4 text-lg text-[var(--re-text-muted)] max-w-[740px] leading-relaxed">
          {content.subtitle}
        </p>

        <div className="mt-8 p-6 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <p className="text-sm uppercase tracking-[0.1em] text-[var(--re-text-disabled)] mb-2">Current Focus</p>
          <p className="text-base text-[var(--re-text-primary)]">{content.focus}</p>
        </div>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href={content.primaryHref}
            className="inline-flex items-center justify-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold"
          >
            {content.primaryLabel}
          </Link>
          <Link
            href={content.secondaryHref}
            className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold"
          >
            {content.secondaryLabel}
          </Link>
        </div>
      </section>
    </main>
  );
}
