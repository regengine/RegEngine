'use client';

import Link from 'next/link';
import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { useToast } from '@/components/ui/use-toast';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import {
  useRequestCases,
  useCreateRequestCase,
  useApproveScope,
  useCollectRecords,
  useRunGapAnalysis,
  useAssemblePackage,
} from '@/hooks/use-request-workflow';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  AlertTriangle,
  CheckCircle,
  FileText,
  Package,
  PlayCircle,
  Send,
  Timer,
} from 'lucide-react';

/**
 * Workflow status mapped onto the shared compliance-state vocabulary — the old
 * map painted Badge backgrounds with raw saturated palette classes (and a
 * non-existent `bg-re-surface-card0`) and white text.
 */
const STATUS_CONFIG: Record<string, { label: string; state: ComplianceState; progress: number }> = {
  intake: { label: 'Intake', state: 'pending', progress: 5 },
  scoping: { label: 'Scoping', state: 'pending', progress: 15 },
  collecting: { label: 'Collecting', state: 'in-progress', progress: 30 },
  gap_analysis: { label: 'Gap Analysis', state: 'in-progress', progress: 45 },
  exception_triage: { label: 'Exception Triage', state: 'at-risk', progress: 55 },
  assembling: { label: 'Assembling', state: 'in-progress', progress: 70 },
  internal_review: { label: 'Internal Review', state: 'pending', progress: 80 },
  ready: { label: 'Ready', state: 'compliant', progress: 90 },
  submitted: { label: 'Submitted', state: 'exported', progress: 100 },
  amended: { label: 'Amended', state: 'corrected', progress: 100 },
};

export default function RequestWorkflowPage() {
  const { tenantId, user } = useAuth();
  const tid = tenantId || '';
  const actor = user?.email || user?.id || 'unknown';
  const { toast } = useToast();

  // Review finding: the workflow mutations swallowed failures — react-query
  // captures the thrown cpFetch error in mutation.error, which nothing read,
  // so a failed action (stale-status race, network, auth) left the card
  // unchanged with zero feedback. Every action button passes this handler.
  const notifyActionError = (action: string) => (err: unknown) =>
    toast({
      title: `${action} failed`,
      description: err instanceof Error ? err.message : String(err),
      variant: 'destructive',
    });

  const [showCreate, setShowCreate] = useState(false);
  const [newRequestParty, setNewRequestParty] = useState('FDA');
  const [newRequestLots, setNewRequestLots] = useState('');

  const requests = useRequestCases(tid);
  const createRequest = useCreateRequestCase(tid);
  const approveScope = useApproveScope(tid);
  const collectRecords = useCollectRecords(tid);
  const runGapAnalysis = useRunGapAnalysis(tid);
  const assemblePackage = useAssemblePackage(tid);

  const cases = requests.data?.cases ?? [];
  const activeCases = cases.filter(c => !['submitted', 'amended'].includes(c.package_status));
  const completedCases = cases.filter(c => ['submitted', 'amended'].includes(c.package_status));

  const pageHeader = (
    <PageHeader
      title="Request-Response Workflow"
      description="24-hour FDA response readiness — from request intake to sealed package submission"
      primaryAction={
        <Button
          variant={showCreate ? 'secondary' : 'primary'}
          onClick={() => setShowCreate(!showCreate)}
          leadingIcon={<PlayCircle strokeWidth={1.75} aria-hidden="true" />}
        >
          New Request Case
        </Button>
      }
    />
  );

  if (requests.error) {
    return (
      <PageContainer>
        {pageHeader}
        <Callout
          tone="danger"
          role="alert"
          title="Unable to load data from the control plane API."
          action={
            <Button variant="secondary" size="sm" onClick={() => requests.refetch()}>
              Retry
            </Button>
          }
        >
          {(requests.error as Error).message}
        </Callout>
      </PageContainer>
    );
  }

  const handleCreate = async () => {
    const lots = newRequestLots.split(',').map(s => s.trim()).filter(Boolean);
    await createRequest.mutateAsync({
      requesting_party: newRequestParty,
      scope_type: 'tlc_trace',
      affected_lots: lots,
      response_hours: 24,
    });
    setShowCreate(false);
    setNewRequestLots('');
  };

  return (
    <PageContainer>
      {pageHeader}

      <DemoBanner visible={!!(requests.data?.__isDemo)} />

      {showCreate && (
        <Card className="mb-8 mt-6">
          <CardHeader>
            <CardTitle>Open New Request Case</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Requesting Party" htmlFor="new-request-party">
                <select
                  id="new-request-party"
                  className={fieldControlClasses}
                  value={newRequestParty}
                  onChange={e => setNewRequestParty(e.target.value)}
                >
                  <option value="FDA">FDA</option>
                  <option value="State DOH">State DOH</option>
                  <option value="Internal Drill">Internal Drill</option>
                  <option value="Customer Audit">Customer Audit</option>
                </select>
              </Field>
              <Field label="Affected Lot Codes (comma-separated)" htmlFor="new-request-lots">
                <Input
                  id="new-request-lots"
                  placeholder="TLC-001, TLC-002..."
                  value={newRequestLots}
                  onChange={e => setNewRequestLots(e.target.value)}
                />
              </Field>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={handleCreate} disabled={createRequest.isPending}>
                {createRequest.isPending ? 'Creating...' : 'Create Case (24h deadline)'}
              </Button>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Section
        spacing="app"
        className="mt-6"
        title={<>Active Cases ({activeCases.length})</>}
      >
        {requests.isLoading ? (
          <div className="space-y-3">
            {[1, 2].map(i => <Skeleton key={i} className="h-40 w-full" />)}
          </div>
        ) : activeCases.length === 0 ? (
          <EmptyState
            icon={CheckCircle}
            title="No active request cases"
            description="Create a new case to start a response workflow"
          />
        ) : (
          <div className="space-y-4">
            {activeCases.map(rc => {
              const config = STATUS_CONFIG[rc.package_status] || STATUS_CONFIG.intake;
              const isOverdue = rc.is_overdue;
              const hoursLeft = rc.hours_remaining ?? 0;

              return (
                <Card key={rc.request_case_id} padding="spacious">
                  <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
                    {/* Left: case info */}
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge state={config.state} label={config.label} size="sm" />
                        <span className="text-ui font-medium text-re-text-primary">
                          {rc.requesting_party}
                        </span>
                        <span className="text-small text-re-text-tertiary">
                          {rc.scope_type?.replace(/_/g, ' ')}
                        </span>
                      </div>

                      <div>
                        <Progress value={config.progress} className="h-2" />
                        <div className="mt-1 flex flex-wrap justify-between gap-2">
                          <span className="text-small text-re-text-tertiary">
                            {rc.total_records} records collected
                          </span>
                          <span className="text-small text-re-text-tertiary">
                            {rc.gap_count} gaps / {rc.active_exception_count} exceptions
                          </span>
                        </div>
                      </div>

                      {rc.affected_lots?.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {rc.affected_lots.slice(0, 5).map(lot => (
                            <Badge key={lot} size="sm" mono>{lot}</Badge>
                          ))}
                          {rc.affected_lots.length > 5 && (
                            <Badge size="sm">+{rc.affected_lots.length - 5} more</Badge>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Right: countdown + actions */}
                    <div className="flex flex-col items-start gap-2 md:min-w-[12rem] md:items-end">
                      <div className={cn('flex items-center gap-1.5 text-ui font-medium', isOverdue ? 'text-re-danger' : 'text-re-text-secondary')}>
                        <Timer className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        {rc.countdown_display || `${Math.max(0, hoursLeft).toFixed(1)}h remaining`}
                      </div>
                      {isOverdue && <Badge tone="danger" size="sm">OVERDUE</Badge>}

                      <div className="flex flex-wrap gap-1">
                        {['gap_analysis', 'assembling', 'internal_review', 'ready'].includes(rc.package_status) && (
                          <Button size="sm" variant="secondary" asChild><Link href={`/requests/${rc.request_case_id}`}>Review and sign off</Link></Button>
                        )}
                        {/* Status-aware next step. The card used to show
                            Assemble for every pre-ready status, but the
                            backend rejects assemble outside gap_analysis/
                            exception_triage/assembling/internal_review —
                            from intake the only offered action was a
                            guaranteed 400. Walk the state machine instead. */}
                        {rc.package_status === 'intake' && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={approveScope.isPending}
                            leadingIcon={<PlayCircle strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => approveScope.mutate({ requestCaseId: rc.request_case_id }, { onError: notifyActionError('Approve Scope') })}
                          >
                            Approve Scope
                          </Button>
                        )}
                        {['scoping'].includes(rc.package_status) && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={collectRecords.isPending}
                            leadingIcon={<FileText strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => collectRecords.mutate({ requestCaseId: rc.request_case_id }, { onError: notifyActionError('Collect Records') })}
                          >
                            Collect Records
                          </Button>
                        )}
                        {['collecting'].includes(rc.package_status) && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={runGapAnalysis.isPending}
                            leadingIcon={<AlertTriangle strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => runGapAnalysis.mutate({ requestCaseId: rc.request_case_id }, { onError: notifyActionError('Run Gap Analysis') })}
                          >
                            Run Gap Analysis
                          </Button>
                        )}
                        {['gap_analysis', 'exception_triage', 'assembling', 'internal_review'].includes(rc.package_status) && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={assemblePackage.isPending}
                            leadingIcon={<Package strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => assemblePackage.mutate({
                              requestCaseId: rc.request_case_id,
                              generatedBy: actor,
                            }, { onError: notifyActionError('Assemble') })}
                          >
                            Assemble
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </Section>

      {completedCases.length > 0 && (
        <Section
          spacing="app"
          className="mt-8"
          title={<>Completed ({completedCases.length})</>}
        >
          <div className="space-y-2">
            {completedCases.map(rc => (
              <Card key={rc.request_case_id} variant="inset" padding="compact">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusBadge
                      state={rc.package_status === 'amended' ? 'corrected' : 'exported'}
                      label={rc.package_status === 'amended' ? 'Amended' : 'Submitted'}
                      size="sm"
                    />
                    <span className="text-ui text-re-text-primary">{rc.requesting_party}</span>
                    <span className="text-small text-re-text-tertiary">{rc.total_records} records</span>
                  </div>
                  <Link href={`/requests/${rc.request_case_id}`}>View retained history</Link>
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}
    </PageContainer>
  );
}
