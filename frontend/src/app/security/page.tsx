import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Database, Download, FileCode2, Hash, KeyRound, Lock, ShieldCheck, Terminal } from "lucide-react";

export const metadata: Metadata = {
  title: "Security | RegEngine",
  description:
    "RegEngine security posture: tenant isolation, evidence integrity after ingest, verifiable export manifests, and exportability.",
  openGraph: {
    title: "Security | RegEngine",
    description: "Tenant isolation, evidence integrity, and verification posture for FSMA 204 records.",
    url: "https://regengine.co/security",
    type: "website",
  },
};

const verified = [
  { title: "Tenant isolation", body: "PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict cross-tenant access on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in active rollout; details available under NDA.", icon: Lock },
  { title: "Append-oriented evidence", body: "Committed compliance records are append-oriented after ingest, and corrections preserve lineage rather than mutating prior records.", icon: Database },
  { title: "Hash verification", body: "Export bundles ship with a SHA-256 manifest so records can be checked outside the product UI. Legacy Kafka-compatible signing exists only for opt-in deployments.", icon: Hash },
  { title: "Operational gates", body: "CI includes secrets, SAST, and dependency checks. DAST, SBOM, and container scans run when configured or on scheduled/main-branch workflows.", icon: ShieldCheck },
];

const controls = [
  ["Encryption", "Encrypted transport in transit; encryption at rest provided by managed database and storage providers (see subprocessors)"],
  ["Identity", "JWT sessions, API keys, CSRF protection"],
  ["Isolation", "Tenant-scoped database access via PostgreSQL row-level policies on core PostgreSQL-backed paths"],
  ["Audit", "Tamper-evident export manifests covering records after ingest; upstream entry is not cryptographically attested"],
  ["Verification", "Open verifier script for export-bundle chain checks"],
  ["Disclosure", "security.txt and vulnerability intake"],
];

const links = [
  { icon: Terminal, label: "Open verifier", href: "/verify" },
  { icon: Download, label: "Download proof artifacts", href: "/proof" },
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
            Verify the evidence, not just the dashboard.
          </h1>
          <p className="mt-6 max-w-[590px] text-[17px] leading-7 text-[var(--re-text-muted)]">
            Compliance security should be mechanical: isolate tenants, preserve lineage, hash the evidence, and make verification possible without asking anyone to believe the UI.
          </p>
          <p className="mt-4 max-w-[590px] text-sm leading-6 text-[var(--re-text-muted)]">
            These statements describe controls verified in source and pre-production staging. Production
            validation requires a release-evidence record bound to the deployed frontend and backend commits.
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
          <div className="flex items-center justify-between border-b border-[var(--re-surface-border)] p-4">
            <p className="re-label">Verifier output</p>
            <p className="re-label text-[var(--re-text-muted)]">Sample · illustrative</p>
          </div>
          <div className="bg-[var(--re-text-primary)] p-5 font-mono text-[12px] leading-6 text-[var(--re-surface-base)]">
            <p>$ python verify_chain.py --export fsma_package.json</p>
            <p className="mt-3 text-[#8fd19e]">verified: 430 records</p>
            <p className="text-[#8fd19e]">failed: 0 records</p>
            <p className="text-[#f1c36d]">manifest: hash matched</p>
            <p className="mt-3 text-[#d8d2c5]">result: evidence package intact</p>
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-3">
            <div>
              <p className="re-label mb-1">Bundle</p>
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">fsma_package.json</p>
              <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">Export package selected by the customer workflow.</p>
            </div>
            <div>
              <p className="re-label mb-1">Manifest</p>
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">SHA-256</p>
              <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">Integrity check for records after ingest, not upstream entry proof.</p>
            </div>
            <div>
              <p className="re-label mb-1">Review path</p>
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">Outside the UI</p>
              <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">A supported bundle can be checked independently.</p>
            </div>
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
        <div className="re-container grid gap-5 md:grid-cols-4">
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
