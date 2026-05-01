import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Database, FileCode2, Hash, KeyRound, Lock, ShieldCheck, Terminal } from "lucide-react";

export const metadata: Metadata = {
  title: "Security | RegEngine",
  description:
    "RegEngine security is built around tenant isolation, immutable evidence, cryptographic hashes, and independently verifiable exports.",
  openGraph: {
    title: "Security | RegEngine",
    description: "Tenant isolation, immutable evidence, and independent verification for FSMA 204 records.",
    url: "https://regengine.co/security",
    type: "website",
  },
};

const verified = [
  { title: "Tenant isolation", body: "PostgreSQL row-level policies and authenticated tenant context prevent cross-tenant reads.", icon: Lock },
  { title: "Immutable evidence", body: "Committed compliance records are append-oriented and corrections preserve lineage.", icon: Database },
  { title: "Hash verification", body: "SHA-256 verification lets exported evidence be checked outside the product UI.", icon: Hash },
  { title: "Operational gates", body: "Secrets, SAST, DAST, dependency, container, and SBOM checks run in CI.", icon: ShieldCheck },
];

const controls = [
  ["Encryption", "AES-256 at rest, TLS in transit"],
  ["Identity", "JWT sessions, API keys, CSRF protection"],
  ["Isolation", "Tenant-scoped database access"],
  ["Audit", "Tamper-evident records and export manifests"],
  ["Verification", "Open verifier script for chain checks"],
  ["Disclosure", "security.txt and vulnerability intake"],
];

const links = [
  { icon: Terminal, label: "Open verifier", href: "/verify" },
  { icon: FileCode2, label: "Security details", href: "/trust/architecture" },
  { icon: KeyRound, label: "Contact security", href: "/contact" },
];

export default function SecurityPage() {
  return (
    <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
      <section className="re-container grid gap-10 pb-14 pt-12 md:grid-cols-[0.85fr_1fr] md:pb-20 md:pt-18">
        <div>
          <p className="re-label mb-5">Security</p>
          <h1 className="max-w-[680px] text-[clamp(42px,7vw,78px)] font-semibold leading-[0.96]">
            Do not trust the dashboard. Verify the record.
          </h1>
          <p className="mt-6 max-w-[590px] text-[17px] leading-7 text-[var(--re-text-muted)]">
            Compliance security should be mechanical: isolate tenants, preserve lineage, hash the evidence, and make verification possible without asking anyone to believe the UI.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/verify" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]">
              See verification <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/trust" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]">
              Trust center
            </Link>
          </div>
        </div>
        <div className="re-panel overflow-hidden">
          <div className="border-b border-[var(--re-surface-border)] p-4">
            <p className="re-label">Verifier output</p>
          </div>
          <div className="bg-[var(--re-text-primary)] p-5 font-mono text-[12px] leading-6 text-[var(--re-surface-base)]">
            <p>$ python verify_chain.py --export fsma_package.json</p>
            <p className="mt-3 text-[#8fd19e]">verified: 430 records</p>
            <p className="text-[#8fd19e]">failed: 0 records</p>
            <p className="text-[#f1c36d]">manifest: merkle root matched</p>
            <p className="mt-3 text-[#d8d2c5]">result: evidence package intact</p>
          </div>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-4">
          {verified.map(({ title, body, icon: Icon }) => (
            <article key={title} className="re-panel p-5">
              <Icon className="mb-8 h-5 w-5 text-[var(--re-text-primary)]" />
              <h2 className="text-lg font-semibold">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-8 md:grid-cols-[0.75fr_1fr]">
          <div>
            <p className="re-label mb-4">Control surface</p>
            <h2 className="text-3xl font-semibold leading-tight">Security claims expressed as checks.</h2>
          </div>
          <div className="re-panel overflow-hidden">
            <table className="re-rule-table">
              <tbody>
                {controls.map(([label, detail], index) => (
                  <tr key={label}>
                    <td className="w-1/3 font-mono text-[12px] uppercase text-[var(--re-text-muted)]">
                      <span className="inline-flex items-center gap-2">
                        <span className="re-signal" style={{ color: index % 3 === 0 ? "var(--re-info)" : index % 3 === 1 ? "var(--re-warning)" : "var(--re-success)" }} />
                        {label}
                      </span>
                    </td>
                    <td className="text-[var(--re-text-primary)]">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-3">
          {links.map(({ icon: Icon, label, href }) => (
            <Link key={label} href={href} className="re-panel flex min-h-[120px] flex-col justify-between p-5 no-underline">
              <Icon className="h-5 w-5 text-[var(--re-text-muted)]" />
              <span className="flex items-center justify-between text-lg font-semibold text-[var(--re-text-primary)]">
                {label}
                <ArrowRight className="h-4 w-4" />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
