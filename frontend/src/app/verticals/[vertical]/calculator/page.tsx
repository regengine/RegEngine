import Link from "next/link";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [
    { vertical: "food-safety" },
    { vertical: "energy" },
    { vertical: "healthcare" },
  ];
};

const CALCULATOR_LINKS: Record<string, { href: string; label: string; helper: string }> = {
  "food-safety": {
    href: "/tools/roi-calculator",
    label: "Open FSMA ROI Calculator",
    helper: "Estimate labor and recall-response savings from operational traceability.",
  },
  energy: {
    href: "/tools/roi-calculator",
    label: "Open Compliance ROI Calculator",
    helper: "Model control-workflow efficiency gains for critical infrastructure teams.",
  },
  healthcare: {
    href: "/tools/roi-calculator",
    label: "Open Compliance ROI Calculator",
    helper: "Estimate reduced audit prep and policy management overhead.",
  },
};

type PageProps = {
  params: Promise<{ vertical: string }>;
};

export default async function CalculatorPage({ params }: PageProps) {
  const { vertical } = await params;
  const config = CALCULATOR_LINKS[vertical] ?? CALCULATOR_LINKS["food-safety"];

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[920px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Calculator</p>
        <h1 className="text-[clamp(30px,4vw,44px)] font-bold text-[var(--re-text-primary)] leading-tight">
          Value Modeling for {vertical.replace("-", " ")}
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] leading-relaxed">{config.helper}</p>

        <div className="mt-8 p-6 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <Link
            href={config.href}
            className="inline-flex items-center justify-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold"
          >
            {config.label}
          </Link>
        </div>
      </section>
    </main>
  );
}
