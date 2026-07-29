'use client';

import { useMemo, useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import {
  useIssueCorrectionLink,
  useReleaseManifest,
  useRemediationManifest,
  useRemediationManifests,
  useRemediationMetrics,
  useRemediationOutbox,
  type OutboxPreview,
} from '@/hooks/use-remediation';

import { FileWarning, Link2, Mail, PackageCheck, ShieldCheck } from 'lucide-react';

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
  pending: 'Preview — not emailed',
  previewed: 'Preview — not emailed',
  queued: 'Email queued',
  sending: 'Sending',
  sent: 'Emailed',
  failed: 'Email failed',
  skipped: 'Email skipped',
};

function DeliveryBadge({ status, reason }: { status: string; reason?: string | null }) {
  const label = DELIVERY_LABEL[status] ?? status;
  const title = reason ?? undefined;
  if (status === 'sent') {
    return <Badge variant="secondary" className="text-re-success" title={title}>{label}</Badge>;
  }
  if (status === 'failed') {
    return <Badge variant="destructive" title={title}>{label}</Badge>;
  }
  if (status === 'queued' || status === 'sending') {
    return <Badge variant="secondary" title={title}>{label}</Badge>;
  }
  return <Badge variant="outline" className="text-muted-foreground" title={title}>{label}</Badge>;
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value * 100)}%`;
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      {hint ? <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent> : null}
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

  // Latest outbox entry per case (list is newest-first) — the per-case
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

  if (manifests.error) {
    return (
      <PageContainer>
        <div className="p-8 text-center">
          <p className="text-muted-foreground">Unable to load supplier remediation data.</p>
          <p className="text-sm text-muted-foreground/60 mt-2">{(manifests.error as Error).message}</p>
          <button onClick={() => manifests.refetch()} className="mt-4 text-sm text-primary hover:underline">
            Retry
          </button>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-re-success" />
          Supplier Remediation
        </h1>
        <p className="text-muted-foreground mt-1">
          Manifest intake, blocked-line correction links, and evidence — suppliers fix their own data.
        </p>
      </div>

      {/* Metrics (FR-12) */}
      <div className="grid gap-4 md:grid-cols-4 mb-8">
        {metrics.isLoading ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <MetricCard label="Records processed" value={String(m?.total_records_processed ?? 0)} />
            <MetricCard label="First-pass acceptance" value={pct(m?.first_pass_acceptance_rate)} />
            <MetricCard
              label="Resolved without buyer work"
              value={pct(m?.resolved_without_buyer_intervention_rate)}
              hint="The pilot headline metric"
            />
            <MetricCard label="Supplier corrections" value={String(m?.supplier_corrections_submitted ?? 0)} />
          </>
        )}
      </div>

      {/* Manifest list (FR-9) */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileWarning className="h-5 w-5" /> Manifests
          </CardTitle>
          <CardDescription>
            A data hold withholds blocked lines from release — it never rejects physical shipments.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {manifests.isLoading ? (
            <Skeleton className="h-32" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No manifests ingested yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Ready</TableHead>
                  <TableHead>Blocked</TableHead>
                  <TableHead>Released</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.ingestion_run_id}
                    className="cursor-pointer"
                    onClick={() => setSelectedRun(row.ingestion_run_id)}
                  >
                    <TableCell className="font-medium">{row.original_filename}</TableCell>
                    <TableCell>{row.total_rows}</TableCell>
                    <TableCell>{row.ready_to_release}</TableCell>
                    <TableCell>{row.blocked}</TableCell>
                    <TableCell>{row.released}</TableCell>
                    <TableCell>
                      {row.data_hold ? (
                        <Badge variant="destructive">Data hold</Badge>
                      ) : (
                        <Badge variant="secondary">Clear</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {row.ready_to_release > 0 && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={releaseManifest.isPending}
                          onClick={(e) => {
                            e.stopPropagation();
                            releaseManifest.mutate(row.ingestion_run_id);
                          }}
                        >
                          <PackageCheck className="h-4 w-4 mr-1" /> Release passing rows
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Manifest detail */}
      {selectedRun && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>{detail.data?.original_filename ?? 'Manifest detail'}</CardTitle>
            <CardDescription>
              SHA-256 {detail.data?.source_sha256?.slice(0, 16)}… — original bytes preserved verbatim
            </CardDescription>
            <div className="mt-3 max-w-md">
              <Input
                type="email"
                placeholder="supplier@company.com"
                value={supplierEmail}
                onChange={(e) => setSupplierEmail(e.target.value)}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Correction links are emailed here automatically when issued. Leave empty to deliver a link
                manually instead.
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {detail.isLoading ? (
              <Skeleton className="h-32" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Row</TableHead>
                    <TableHead>Validation</TableHead>
                    <TableHead>Release</TableHead>
                    <TableHead>Case</TableHead>
                    <TableHead>Due</TableHead>
                    <TableHead>Why blocked</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(detail.data?.records ?? []).map((record) => (
                    <TableRow key={record.record_id}>
                      <TableCell>{record.row_number}</TableCell>
                      <TableCell>
                        {record.validation_status === 'passed' ? (
                          <Badge variant="secondary">Passed</Badge>
                        ) : (
                          <Badge variant="destructive">Blocked</Badge>
                        )}
                      </TableCell>
                      <TableCell>{record.release_status}</TableCell>
                      <TableCell>
                        {record.case ? (
                          <span className="flex items-center gap-2 text-sm">
                            {CASE_STATUS_LABEL[record.case.case_status] ?? record.case.case_status}
                            {(() => {
                              const delivery = outboxByCase.get(record.case.case_id);
                              if (delivery) {
                                return <DeliveryBadge status={delivery.status} reason={delivery.last_error} />;
                              }
                              return record.case.notified ? (
                                <Mail className="h-3 w-3 text-muted-foreground" />
                              ) : null;
                            })()}
                          </span>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {record.case?.due_at ? new Date(record.case.due_at).toLocaleDateString() : '—'}
                      </TableCell>
                      <TableCell className="max-w-md text-sm text-muted-foreground">
                        {(record.failures ?? []).map((f) => f.why_failed).join('; ') || '—'}
                      </TableCell>
                      <TableCell>
                        {record.remediation_case_id &&
                          record.case &&
                          !['released'].includes(record.case.case_status) && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={issueLink.isPending}
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
                              <Link2 className="h-4 w-4 mr-1" /> Issue link
                            </Button>
                          )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {issued && (
              <div className="mt-4 space-y-1 rounded-md border border-re-warning bg-re-warning-muted p-3 text-sm">
                {issued.email ? (
                  <>
                    <p className="font-medium">
                      Link issued — being emailed to {issued.email} automatically (usually within a minute).
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Do not share the copy below: sending re-issues the link, so this copy stops working the
                      moment the email goes out. Only its hash is stored.
                    </p>
                  </>
                ) : (
                  <p className="font-medium">
                    No supplier email given — this link will NOT be emailed. Copy it now and deliver it
                    yourself (shown once — only its hash is stored):
                  </p>
                )}
                <code className="break-all">{issued.url}</code>
              </div>
            )}
            {issueLink.error ? (
              <p className="mt-3 text-sm text-re-danger">{(issueLink.error as Error).message}</p>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Notification outbox — queued link emails are delivered by the drainer */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" /> Notifications
          </CardTitle>
          <CardDescription>
            Correction-link emails send automatically for entries with a recipient. &ldquo;Preview&rdquo;
            entries predate automatic delivery or are buyer-facing and are never emailed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(outbox.data?.notifications ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No notifications queued.</p>
          ) : (
            <ul className="space-y-2">
              {(outbox.data?.notifications ?? []).slice(0, 10).map((n) => (
                <li key={n.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <DeliveryBadge status={n.status} reason={n.last_error} />
                  <span className="font-medium">{n.subject}</span>
                  {n.recipient && <span className="text-muted-foreground">→ {n.recipient}</span>}
                  <span className="text-xs text-muted-foreground">
                    {n.sent_at
                      ? `sent ${new Date(n.sent_at).toLocaleString()}`
                      : n.created_at
                        ? new Date(n.created_at).toLocaleString()
                        : ''}
                  </span>
                  {(n.status === 'failed' || n.status === 'skipped') && n.last_error && (
                    <span className="text-xs text-re-danger">{n.last_error}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
