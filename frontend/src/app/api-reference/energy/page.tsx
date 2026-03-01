import Link from "next/link";

export default function EnergyApiReferencePage() {
  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[840px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">API Reference</p>
        <h1 className="text-[clamp(30px,4vw,46px)] font-bold text-[var(--re-text-primary)] leading-tight">
          Energy Compliance API
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] leading-relaxed">
          Use RegEngine endpoints to ingest control evidence, track validation status, and export audit packages.
        </p>

        <div className="mt-8 p-6 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <p className="text-sm text-[var(--re-text-muted)]">
            Full endpoint examples are available in the main API docs while energy-specific endpoint groups are finalized.
          </p>
          <Link href="/docs/api" className="inline-flex mt-4 h-10 px-5 rounded-xl bg-[var(--re-brand)] text-white items-center font-semibold">
            Open API Documentation
          </Link>
        </div>
      </section>
    </main>
  );
}
