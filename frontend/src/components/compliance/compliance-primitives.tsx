import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  Fingerprint,
  LockKeyhole,
  PackageCheck,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getComplianceStateStyle, type ComplianceObjectState } from "@/lib/compliance-os";
import { cn } from "@/lib/utils";

type PrimitiveSize = "sm" | "md";

export function ComplianceStateBadge({
  state,
  className,
}: {
  state: ComplianceObjectState;
  className?: string;
}) {
  const style = getComplianceStateStyle(state);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2.5 py-1 font-mono text-[11px] font-medium uppercase leading-none",
        className,
      )}
      style={{
        color: style.colorVar,
        backgroundColor: style.backgroundVar,
        borderColor: style.borderVar,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: style.colorVar }} />
      {style.label}
    </span>
  );
}

export function EvidenceCard({
  title,
  description,
  state,
  meta,
  icon: Icon = FileCheck2,
  children,
  className,
}: {
  title: string;
  description: string;
  state: ComplianceObjectState;
  meta?: string;
  icon?: LucideIcon;
  children?: ReactNode;
  className?: string;
}) {
  const style = getComplianceStateStyle(state);

  return (
    <article
      className={cn("re-evidence-card flex h-full flex-col border bg-[var(--re-surface-elevated)] p-4", className)}
      style={{ borderColor: style.borderVar }}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center border"
          style={{ color: style.colorVar, backgroundColor: style.backgroundVar, borderColor: style.borderVar }}
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <ComplianceStateBadge state={state} />
      </div>
      <div className="mt-5">
        {meta ? <p className="re-label">{meta}</p> : null}
        <h3 className="mt-2 text-lg font-semibold leading-tight text-[var(--re-text-primary)]">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{description}</p>
      </div>
      {children ? <div className="mt-4 border-t border-[var(--re-border-subtle)] pt-4">{children}</div> : null}
    </article>
  );
}

export function ReadinessScore({
  score,
  label,
  description,
  blockers = 0,
  size = "md",
}: {
  score: number;
  label: string;
  description: string;
  blockers?: number;
  size?: PrimitiveSize;
}) {
  const normalized = Math.min(100, Math.max(0, score));
  const tone = normalized >= 90 ? "var(--re-success)" : normalized >= 75 ? "var(--re-warning)" : "var(--re-danger)";
  const ringSize = size === "sm" ? "h-20 w-20" : "h-28 w-28";

  return (
    <section
      className={cn(
        "re-readiness-score grid self-start gap-4 border bg-[var(--re-surface-elevated)] p-4",
        size === "md" ? "sm:grid-cols-[auto_1fr]" : "",
      )}
    >
      <div
        className={cn("grid shrink-0 place-items-center rounded-full", ringSize)}
        style={{
          background: `conic-gradient(${tone} ${normalized * 3.6}deg, var(--re-surface-card) 0deg)`,
        }}
        aria-label={`${label}: ${normalized}% ready`}
      >
        <div className="grid h-[calc(100%-14px)] w-[calc(100%-14px)] place-items-center rounded-full bg-[var(--re-surface-elevated)]">
          <span className="text-2xl font-semibold text-[var(--re-text-primary)]">{normalized}%</span>
        </div>
      </div>
      <div className={cn("min-w-0", size === "md" ? "self-center" : "")}>
        <p className="re-label">{blockers === 1 ? "1 blocker" : `${blockers} blockers`}</p>
        <h3 className="mt-2 text-xl font-semibold leading-tight text-[var(--re-text-primary)]">{label}</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{description}</p>
      </div>
    </section>
  );
}

export function HashVerificationStrip({
  hash,
  algorithm = "SHA-256",
  verifiedAt,
  state = "committed",
}: {
  hash: string;
  algorithm?: string;
  verifiedAt: string;
  state?: ComplianceObjectState;
}) {
  return (
    <div className="re-hash-strip grid gap-3 border bg-[var(--re-surface-card)] p-3 text-sm">
      <div className="flex items-center gap-2 font-semibold text-[var(--re-text-primary)]">
        <Fingerprint className="h-4 w-4 text-[var(--re-evidence)]" aria-hidden="true" />
        Hash verified
      </div>
      <code className="min-w-0 break-all font-mono text-[12px] text-[var(--re-text-muted)]">
        {algorithm}:{hash}
      </code>
      <div className="flex flex-wrap items-center gap-2">
        <ComplianceStateBadge state={state} />
        <span className="font-mono text-[11px] uppercase text-[var(--re-text-muted)]">{verifiedAt}</span>
      </div>
    </div>
  );
}

export function CommitGate({
  status,
  title,
  description,
  criteria,
  actionLabel,
}: {
  status: "eligible" | "blocked" | "committed";
  title: string;
  description: string;
  criteria: Array<{ label: string; passed: boolean; detail?: string }>;
  actionLabel?: string;
}) {
  const state: ComplianceObjectState =
    status === "eligible" ? "ready" : status === "committed" ? "committed" : "blocked";
  const Icon = status === "blocked" ? AlertTriangle : status === "committed" ? LockKeyhole : ShieldCheck;

  return (
    <section className="re-commit-gate border bg-[var(--re-surface-elevated)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)]">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <ComplianceStateBadge state={state} />
            <h3 className="mt-3 text-lg font-semibold leading-tight text-[var(--re-text-primary)]">{title}</h3>
            <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{description}</p>
          </div>
        </div>
        {actionLabel ? (
          <span className="hidden shrink-0 items-center gap-2 border border-[var(--re-border-strong)] px-3 py-2 text-[12px] font-semibold text-[var(--re-text-primary)] sm:inline-flex">
            {actionLabel}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
        ) : null}
      </div>
      <div className="mt-4 grid gap-2">
        {criteria.map((item) => (
          <div key={item.label} className="flex items-start gap-3 border-t border-[var(--re-border-subtle)] pt-3">
            {item.passed ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--re-success)]" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--re-warning)]" aria-hidden="true" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">{item.label}</p>
              {item.detail ? <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">{item.detail}</p> : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function EvidencePackagePreview({
  packageId,
  status,
  records,
  kdeCoverage,
  generatedAt,
  items,
}: {
  packageId: string;
  status: ComplianceObjectState;
  records: number;
  kdeCoverage: number;
  generatedAt: string;
  items: string[];
}) {
  return (
    <section className="re-package-preview border bg-[var(--re-surface-elevated)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="re-label">Evidence package</p>
          <h3 className="mt-2 text-lg font-semibold text-[var(--re-text-primary)]">{packageId}</h3>
        </div>
        <ComplianceStateBadge state={status} />
      </div>
      <div className="mt-4 grid grid-cols-3 border-y border-[var(--re-border-subtle)]">
        <MetricCell label="Records" value={records.toLocaleString()} />
        <MetricCell label="KDEs" value={`${kdeCoverage}%`} />
        <MetricCell label="Built" value={generatedAt} />
      </div>
      <ul className="mt-4 grid gap-2">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-2 text-sm text-[var(--re-text-secondary)]">
            <PackageCheck className="h-4 w-4 shrink-0 text-[var(--re-success)]" aria-hidden="true" />
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RegulatoryCitationBlock({
  citation,
  title,
  children,
}: {
  citation: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <aside className="re-citation-block border-l-4 border-[var(--re-evidence)] bg-[var(--re-evidence-bg)] p-4">
      <p className="font-mono text-[11px] font-medium uppercase text-[var(--re-evidence)]">{citation}</p>
      <h3 className="mt-2 text-base font-semibold text-[var(--re-text-primary)]">{title}</h3>
      <div className="mt-2 text-sm leading-6 text-[var(--re-text-secondary)]">{children}</div>
    </aside>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-r border-[var(--re-border-subtle)] px-3 py-3 last:border-r-0">
      <p className="re-label">{label}</p>
      <p className="mt-1 text-base font-semibold text-[var(--re-text-primary)]">{value}</p>
    </div>
  );
}
