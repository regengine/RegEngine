'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import {
  useRequestCases,
  usePackageHistory,
  useAssemblePackage,
  useSubmitPackage,
  type RequestCase,
} from '@/hooks/use-control-plane';

import {
  ArrowLeft,
  CheckCircle,
  Clock,
  Hash,
  Package,
  Send,
  User,
} from 'lucide-react';

interface ResponsePackage {
  package_id: string;
  version_number: number;
  generated_at: string;
  generated_by?: string;
  package_hash?: string;
  diff_from_previous?: Record<string, unknown>;
}

const STAGE_ORDER = [
  'intake', 'scoping', 'collecting', 'gap_analysis',
  'exception_triage', 'assembling', 'internal_review',
  'ready', 'submitted', 'amended',
];

const STAGE_LABELS: Record<string, string> = {
  intake: 'Intake',
  scoping: 'Scoping',
  collecting: 'Collecting',
  gap_analysis: 'Gap Analysis',
  exception_triage: 'Exception Triage',
  assembling: 'Assembling',
  internal_review: 'Internal Review',
  ready: 'Ready',
  submitted: 'Submitted',
  amended: 'Amended',
};

/** Key/value row shared by the Scope and Case Stats lists. */
function DetailRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-re-border-subtle py-2 last:border-0">
      <dt className="text-label text-re-text-muted">{term}</dt>
      <dd className="text-right text-ui text-re-text-primary">{children}</dd>
    </div>
  );
}

const BACK_LINK_CLASS =
  'inline-flex items-center gap-1.5 text-ui text-re-text-tertiary no-underline transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none';

export default function RequestCaseDetailPage() {
  const params = useParams();
  const requestCaseId = params.id as string;
  const { tenantId, user } = useAuth();
  const tid = tenantId || '';
  const actor = user?.email || user?.id || 'unknown';

  const requests = useRequestCases(tid);
  const packages = usePackageHistory(tid, requestCaseId);
  const assemblePackage = useAssemblePackage(tid);
  const submitPackage = useSubmitPackage(tid);

  const requestCase = requests.data?.cases?.find(
    (c: RequestCase) => c.request_case_id === requestCaseId
  );
  const packageList = (packages.data?.packages ?? []) as unknown as ResponsePackage[];

  if (requests.isLoading) {
    return (
      <PageContainer>
        <div className="space-y-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      </PageContainer>
    );
  }

  if (!requestCase) {
    return (
      <PageContainer>
        <EmptyState
          title="Request case not found"
          action={
            <Link href="/requests" className={BACK_LINK_CLASS}>
              <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              Back to Request Workflow
            </Link>
          }
        />
      </PageContainer>
    );
  }

  const currentStageIdx = STAGE_ORDER.indexOf(requestCase.package_status);
  const progress = Math.max(5, ((currentStageIdx + 1) / STAGE_ORDER.length) * 100);
  const isOverdue = requestCase.is_overdue;
  const hoursLeft = requestCase.hours_remaining ?? 0;

  return (
    <PageContainer>
      <PageHeader
        breadcrumbs={
          <Link href="/requests" className={BACK_LINK_CLASS}>
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            Back to Request Workflow
          </Link>
        }
        title="Request Case"
        description={`${requestCase.requesting_party} — ${requestCase.scope_type?.replace(/_/g, ' ')}`}
        meta={
          <>
            <span
              className={cn(
                'flex items-center gap-1.5 text-ui font-medium',
                isOverdue ? 'text-re-danger' : 'text-re-text-secondary'
              )}
            >
              <Clock className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
              {requestCase.countdown_display || `${Math.max(0, hoursLeft).toFixed(1)}h remaining`}
            </span>
            {isOverdue && <Badge tone="danger" size="sm">OVERDUE</Badge>}
          </>
        }
      />

      {/* Workflow Stage Pipeline */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Workflow Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <Progress value={progress} className="mb-4 h-3" />
          <ol className="flex flex-wrap gap-1">
            {STAGE_ORDER.map((stage, idx) => {
              const isCurrent = stage === requestCase.package_status;
              const isPast = idx < currentStageIdx;
              return (
                <li
                  key={stage}
                  aria-current={isCurrent ? 'step' : undefined}
                  className={cn(
                    'flex items-center gap-1 rounded-md border px-2 py-1 text-small',
                    isCurrent
                      ? 'border-re-info-border bg-re-info-bg font-medium text-re-info'
                      : isPast
                        ? 'border-re-success-border bg-re-success-bg text-re-success'
                        : 'border-transparent text-re-text-muted'
                  )}
                >
                  {isPast && (
                    <CheckCircle className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                  )}
                  {STAGE_LABELS[stage]}
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column: case details */}
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Scope</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
                <DetailRow term="Requesting Party">{requestCase.requesting_party}</DetailRow>
                <DetailRow term="Scope Type">{requestCase.scope_type?.replace(/_/g, ' ')}</DetailRow>
                <DetailRow term="Received">
                  {new Date(requestCase.request_received_at).toLocaleString()}
                </DetailRow>
                <DetailRow term="Due">
                  <span className={cn(isOverdue && 'font-medium text-re-danger')}>
                    {new Date(requestCase.response_due_at).toLocaleString()}
                  </span>
                </DetailRow>
              </dl>

              {requestCase.affected_lots?.length > 0 && (
                <div className="mt-4">
                  <p className="mb-1.5 text-label text-re-text-muted">Affected Lot Codes</p>
                  <div className="flex flex-wrap gap-1">
                    {requestCase.affected_lots.map((lot: string) => (
                      <Badge key={lot} size="sm" mono>{lot}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {requestCase.affected_facilities?.length > 0 && (
                <div className="mt-3">
                  <p className="mb-1.5 text-label text-re-text-muted">Affected Facilities</p>
                  <div className="flex flex-wrap gap-1">
                    {requestCase.affected_facilities.map((f: string) => (
                      <Badge key={f} size="sm">{f}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Package History */}
          <Card>
            <CardHeader>
              <CardTitle>Response Packages ({packageList.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {packages.isLoading ? (
                <div className="space-y-2">
                  {[1, 2].map(i => <Skeleton key={i} className="h-16 w-full" />)}
                </div>
              ) : packageList.length === 0 ? (
                <EmptyState bare size="sm" title="No packages assembled yet" />
              ) : (
                <div className="space-y-3">
                  {packageList.map((pkg: ResponsePackage) => (
                    <Card key={pkg.package_id} variant="inset" padding="compact">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Badge size="sm" mono>v{pkg.version_number}</Badge>
                          <span className="text-small text-re-text-tertiary">
                            {new Date(pkg.generated_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 font-mono text-small text-re-text-tertiary">
                          <Hash className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                          {pkg.package_hash?.slice(0, 12)}...
                        </div>
                      </div>
                      {pkg.generated_by && (
                        <div className="mt-1 flex items-center gap-1 text-small text-re-text-tertiary">
                          <User className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                          {pkg.generated_by}
                        </div>
                      )}
                      {pkg.diff_from_previous && (
                        <div className="mt-2 rounded-md border border-re-border-subtle bg-re-surface-card p-2 text-small">
                          <span className="font-medium text-re-text-primary">
                            Diff from v{pkg.version_number - 1}:
                          </span>
                          <pre className="mt-1 overflow-x-auto font-mono text-small text-re-text-secondary">
                            {JSON.stringify(pkg.diff_from_previous, null, 2).slice(0, 200)}
                          </pre>
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column: stats + actions */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Case Stats</CardTitle>
            </CardHeader>
            <CardContent>
              <dl>
                <DetailRow term="Records Collected">{requestCase.total_records}</DetailRow>
                <DetailRow term="Gaps Found">
                  <span className={requestCase.gap_count > 0 ? 'text-re-warning' : 'text-re-success'}>
                    {requestCase.gap_count}
                  </span>
                </DetailRow>
                <DetailRow term="Active Exceptions">
                  <span className={requestCase.active_exception_count > 0 ? 'text-re-danger' : 'text-re-success'}>
                    {requestCase.active_exception_count}
                  </span>
                </DetailRow>
                <DetailRow term="Package Versions">{packageList.length}</DetailRow>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {requestCase.package_status !== 'submitted' && (
                <Button
                  className="w-full"
                  variant="secondary"
                  leadingIcon={<Package strokeWidth={1.75} aria-hidden="true" />}
                  onClick={() => assemblePackage.mutate({
                    requestCaseId,
                    generatedBy: actor,
                  })}
                  disabled={assemblePackage.isPending}
                >
                  {assemblePackage.isPending ? 'Assembling...' : 'Assemble Package'}
                </Button>
              )}
              {requestCase.package_status === 'ready' && (
                <Button
                  className="w-full"
                  leadingIcon={<Send strokeWidth={1.75} aria-hidden="true" />}
                  onClick={() => submitPackage.mutate({
                    requestCaseId,
                    submitted_by: actor,
                    submitted_to: requestCase.requesting_party,
                  })}
                  disabled={submitPackage.isPending}
                >
                  {submitPackage.isPending ? 'Submitting...' : 'Submit to ' + requestCase.requesting_party}
                </Button>
              )}
              {requestCase.package_status === 'submitted' && (
                <div className="py-3">
                  <StatusBadge state="exported" label="Package Submitted" />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
