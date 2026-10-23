'use client';

import { useMemo, useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge } from '@/components/ui/status-badge';

import { useAuth } from '@/lib/auth-context';
import {
  useIssueCorrectionLink,
  useReleaseManifest,
  useRemediationManifest,
  useRemediationManifests,
  useRemediationMetrics,
  useRemediationOutbox,
  type ManifestRecord,
  type ManifestSummary,
  type OutboxPreview,
} from '@/hooks/use-remediation';

import { Check, Copy, FileWarning, Link2, Mail, PackageCheck } from 'lucide-react';
import { NOT_SET, NO_DATA_YET } from '@/lib/empty-values';

const CASE_STATUS_LABEL: Record<string, string> = {
  detected: 'Detected',
  auto_resolution_attempted: 'Auto-resolution attempted',
  supplier_action_required: 'Supplier action required',
  notification_ready: 'Notification ready',
  awaiting_supplier: 'Awaiting supplier',
  correction_submitted: 'Correction submitted',
  revalidating: 'Revalidating',
  released: 'Released',
  buyer_review: 'Buyer review',
  escalated: 'Escalated',
};

// Delivery lifecycle of an outbox entry (fsma.notification_outbox.status).
// 'pending'/'previewed' predate automatic delivery and are never emailed.
const DELIVERY_LABEL: Record<string, string> = {
  pending: 'Preview (not emailed)',
  previewed: 'Preview (not emailed)',
  queued: 'Email queued',
  sending: 'Sending',
  sent: 'Emailed',
  failed: 'Email failed',
  skipped: 'Email skipped',
};

const DELIVERY_TONE: Record<string, BadgeTone> = {
  pending: 'neutral',
  previewed: 'neutral',
  queued: 'info',
  sending: 'info',
  sent: 'success',
  failed: 'danger',
  skipped: 'warning',
};

function DeliveryBadge({ status, reason }: { status: string; reason?: string | null }) {
  const label = DELIVERY_LABEL[status] ?? status;
  return (
    <Badge tone={DELIVERY_TONE[status] ?? 'neutral'} size="sm" title={reason ?? undefined}>
      {label}
    </Badge>
  );
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return NO_DATA_YET;
  return `${Math.round(value * 100)}%`;
}

/**
 * One-time secret reveal. The correction URL is shown once and only its hash is
 * stored, so the warning copy is load-bearing and must not be softened.
 */
function IssuedLinkPanel({ url, email }: { url: string; email: string | null }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard denied (insecure context, permission) - the URL is on screen.
    }
  };

  return (
    <Card variant="inset" padding="compact" className="mt-4">
      {email ? (
        <>
          <p className="text-ui font-medium text-re-text-primary">
            Link issued. It is being emailed to {email} automatically (usually within a minute).
          </p>
          <p className="mt-1 text-small text-re-text-tertiary">
            Do not share the copy below: sending re-issues the link, so this copy stops working the
            moment the email goes out. Only its hash is stored.
          </p>
        </>
      ) : (
        <p className="text-ui font-medium text-re-text-primary">
          No supplier email given, so this link will NOT be emailed. Copy it now and deliver it
          yourself (shown once; only its hash is stored):
        </p>
      )}
      <div className="mt-2 flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border border-re-border-subtle bg-re-surface-card px-2 py-1.5 font-mono text-small text-re-text-secondary">
          {url}
        </code>
        <Button
          variant="ghost"
          size="icon"
          onClick={copy}
          aria-label={copied ? 'Correction link copied' : 'Copy correction link'}
        >
          {copied
            ? <Check className="h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
            : <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
        </Button>
      </div>
    </Card>
  );
}

export default function RemediationPage() {
  const { tenantId } = useAuth();
  const tid = tenantId || '';

  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [issued, setIssued] = useState<{ url: string; email: string | null } | null>(null);
  const [supplierEmail, setSupplierEmail] = useState('');

  const manifests = useRemediationManifests(tid);
  const detail = useRemediationManifest(tid, selectedRun);
  const metrics = useRemediationMetrics(tid);
  const outbox = useRemediationOutbox(tid);
  const releaseManifest = useReleaseManifest(tid);
  const issueLink = useIssueCorrectionLink(tid);

  // Latest outbox entry per case (list is newest-first) - the per-case
  // delivery state shown in the manifest detail table.
  const outboxByCase = useMemo(() => {
    const byCase = new Map<string, OutboxPreview>();
    for (const n of outbox.data?.notifications ?? []) {
      if (n.case_id && !byCase.has(n.case_id)) byCase.set(n.case_id, n);
    }
    return byCase;
  }, [outbox.data]);

  const rows = manifests.data?.manifests ?? [];
  const m = metrics.data;

  const pageHeader = (
    <PageHeader
      title="Supplier Remediation"
      description="Manifest intake, blocked-line correction links, and evidence. Suppliers fix their own data."
    />
  );


  if (manifests.error) {
    return (
      <PageContainer>
        {pageHeader}
        <Callout
          tone="danger"
          role="alert"
          title="Unable to load supplier remediation data."
          action={
            <Button variant="secondary" size="sm" onClick={() => manifests.refetch()}>
              Retry
            </Button>
          }
        >
          {(manifests.error as Error).message}
        </Callout>
      </PageContainer>
    );
  }

  const manifestColumns: DataTableColumn<ManifestSummary>[] = [
    {
      key: 'original_filename',
      header: 'File',
      cell: (row) => (
        <button
          type="button"
          aria-pressed={selectedRun === row.ingestion_run_id}
          onClick={() => setSelectedRun(row.ingestion_run_id)}
          className="rounded-sm text-left font-medium text-re-text-primary transition-colors duration-120 hover:text-re-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring aria-pressed:text-re-brand motion-reduce:transition-none"
        >
          {row.original_filename}
        </button>
      ),
    },
    { key: 'total_rows', header: 'Rows', align: 'right', width: '6rem' },
    { key: 'ready_to_release', header: 'Ready', align: 'right', width: '6rem' },
    { key: 'blocked', header: 'Blocked', align: 'right', width: '6rem' },
    { key: 'released', header: 'Released', align: 'right', width: '7rem' },
    {
      key: 'data_hold',
      header: 'Status',
      width: '10rem',
      cell: (row) =>
        row.data_hold
          ? <StatusBadge state="blocked" label="Data hold" size="sm" />
          : <StatusBadge state="compliant" label="Clear" size="sm" />,
    },
    {
      key: 'release',
      header: 'Release',
      align: 'right',
      width: '13rem',
      cell: (row) =>
        row.ready_to_release > 0 ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={releaseManifest.isPending}
            leadingIcon={<PackageCheck strokeWidth={1.75} aria-hidden="true" />}
            onClick={(e) => {
              e.stopPropagation();
              releaseManifest.mutate(row.ingestion_run_id);
            }}
          >
            Release passing rows
          </Button>
        ) : null,
    },
  ];

  const recordColumns: DataTableColumn<ManifestRecord>[] = [
    { key: 'row_number', header: 'Row', align: 'right', width: '5rem' },
    {
      key: 'validation_status',
      header: 'Validation',
      width: '9.5rem',
      cell: (record) =>
        record.validation_status === 'passed'
          ? <StatusBadge state="compliant" label="Passed" size="sm" />
          : <StatusBadge state="blocked" label="Blocked" size="sm" />,
    },
    {
      key: 'release_status',
      header: 'Release',
      width: '7rem',
      cell: (record) => <span className="text-re-text-secondary">{record.release_status}</span>,
    },
    {
      key: 'case',
      header: 'Case',
      width: '12.5rem',
      cell: (record) => {
        if (!record.case) return <span className="text-re-text-muted">{NOT_SET}</span>;
        const delivery = outboxByCase.get(record.case.case_id);
        return (
          <span className="flex flex-wrap items-center gap-2 text-ui text-re-text-secondary">
            {CASE_STATUS_LABEL[record.case.case_status] ?? record.case.case_status}
            {delivery ? (
              <DeliveryBadge status={delivery.status} reason={delivery.last_error} />
            ) : record.case.notified ? (
              <Mail
                className="h-3.5 w-3.5 text-re-text-muted"
                strokeWidth={1.75}
                role="img"
                aria-label="Supplier notified"
              />
            ) : null}
          </span>
        );
      },
    },
    {
      key: 'due',
      header: 'Due',
      width: '7rem',
      cell: (record) => (
        <span className="text-re-text-tertiary">
          {record.case?.due_at ? new Date(record.case.due_at).toLocaleDateString() : NOT_SET}
        </span>
      ),
    },
    {
      key: 'why_blocked',
      header: 'Why blocked',
      cell: (record) => (
        <span className="block max-w-[20ch] text-re-text-tertiary">
          {(record.failures ?? []).map((f) => f.why_failed).join('; ') || NOT_SET}
        </span>
      ),
    },
    {
      key: 'issue',
      header: 'Correction',
      align: 'right',
      width: '9.5rem',
      cell: (record) => {
        if (
          !record.remediation_case_id ||
          !record.case ||
          ['released'].includes(record.case.case_status)
        ) {
          return null;
        }
        return (
          <Button
            size="sm"
            variant="secondary"
            disabled={issueLink.isPending}
            leadingIcon={<Link2 strokeWidth={1.75} aria-hidden="true" />}
            onClick={() => {
              const email = supplierEmail.trim();
              issueLink.mutate(
                {
                  caseId: record.remediation_case_id as string,
                  supplierEmail: email || undefined,
                },
                {
                  onSuccess: (data) =>
                    setIssued({ url: data.correction_url, email: email || null }),
                },
              );
            }}
          >
            Issue link
          </Button>
        );
      },
    },
  ];

  return (
    <PageContainer>
      {pageHeader}

      {/* Metrics (FR-12) */}
      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        {metrics.isLoading ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <StatTile label="Records processed" value={String(m?.total_records_processed ?? 0)} />
            <StatTile label="First-pass acceptance" value={pct(m?.first_pass_acceptance_rate)} />
            <StatTile
              label="Resolved without buyer work"
              value={pct(m?.resolved_without_buyer_intervention_rate)}
            >
              <p className="text-small text-re-text-tertiary">The pilot headline metric</p>
            </StatTile>
            <StatTile
              label="Supplier corrections"
              value={String(m?.supplier_corrections_submitted ?? 0)}
            />
          </>
        )}
      </div>

      {/* Manifest list (FR-9) */}
      <Section
        spacing="app"
        title="Manifests"
        description="A data hold withholds blocked lines from release. It never rejects physical shipments."
      >
        <DataTable
          caption="Ingested supplier manifests"
          columns={manifestColumns}
          data={rows}
          minWidth="1000px"
          rowKey={(row) => row.ingestion_run_id}
          status={manifests.isLoading ? 'loading' : rows.length === 0 ? 'empty' : 'idle'}
          empty={{ icon: FileWarning, title: 'No manifests ingested yet.' }}
        />
      </Section>

      {/* Manifest detail */}
      {selectedRun && (
        <Card className="mt-8">
          <CardHeader>
            <div className="min-w-0">
              <CardTitle>{detail.data?.original_filename ?? 'Manifest detail'}</CardTitle>
              <CardDescription className="mt-1">
                SHA-256 {detail.data?.source_sha256?.slice(0, 16)}… (original bytes preserved verbatim)
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSelectedRun(null)}>
              Close
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="max-w-md">
              <Field
                label="Supplier email"
                htmlFor="remediation-supplier-email"
                hint="Correction links are emailed here automatically when issued. Leave empty to deliver a link manually instead."
              >
                <Input
                  id="remediation-supplier-email"
                  type="email"
                  placeholder="supplier@company.com"
                  value={supplierEmail}
                  onChange={(e) => setSupplierEmail(e.target.value)}
                />
              </Field>
            </div>

            <DataTable
              caption="Manifest rows and their remediation state"
              columns={recordColumns}
              data={detail.data?.records ?? []}
              minWidth="900px"
              rowKey={(record) => record.record_id}
              status={
                detail.isLoading
                  ? 'loading'
                  : (detail.data?.records ?? []).length === 0
                    ? 'empty'
                    : 'idle'
              }
              empty={{ title: 'No rows in this manifest.' }}
            />

            {issued && <IssuedLinkPanel url={issued.url} email={issued.email} />}

            {issueLink.error ? (
              <Callout tone="danger" role="alert">
                {(issueLink.error as Error).message}
              </Callout>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Notification outbox - queued link emails are delivered by the drainer */}
      <Section
        spacing="app"
        className="mt-8"
        title="Notifications"
        description={
          <>
            Correction-link emails send automatically for entries with a recipient. &ldquo;Preview&rdquo;
            entries predate automatic delivery or are buyer-facing and are never emailed.
          </>
        }
      >
        {(outbox.data?.notifications ?? []).length === 0 ? (
          <EmptyState icon={Mail} title="No notifications queued." size="sm" />
        ) : (
          <ul className="rounded-lg border border-re-border bg-re-surface-card">
            {(outbox.data?.notifications ?? []).slice(0, 10).map((n) => (
              <li
                key={n.id}
                className="flex flex-wrap items-center gap-2 border-b border-re-border-subtle px-4 py-2.5 text-ui last:border-0"
              >
                <DeliveryBadge status={n.status} reason={n.last_error} />
                <span className="font-medium text-re-text-primary">{n.subject}</span>
                {n.recipient && <span className="text-re-text-tertiary">→ {n.recipient}</span>}
                <span className="text-small text-re-text-tertiary">
                  {n.sent_at
                    ? `sent ${new Date(n.sent_at).toLocaleString()}`
                    : n.created_at
                      ? new Date(n.created_at).toLocaleString()
                      : ''}
                </span>
                {(n.status === 'failed' || n.status === 'skipped') && n.last_error && (
                  <span className="text-small text-re-danger">{n.last_error}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </PageContainer>
  );
}
