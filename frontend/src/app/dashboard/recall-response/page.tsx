'use client';

import React, { useState, useCallback } from 'react';
import Link from 'next/link';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Download,
  FileText,
  Plus,
  Shield,
  XCircle,
} from 'lucide-react';

import { useTenant } from '@/lib/tenant-context';
import {
  useSLARequests,
  useSLADashboard,
  useSLAAlerts,
  useCreateSLARequest,
  useCompleteSLARequest,
  type FDARequestData,
  type RequestStatus,
} from '@/hooks/use-sla';
import { RecallTimer } from '@/components/fsma/recall-timer';
import { SLAGauge } from '@/components/fsma/recall-timer';
import { PhaseGates } from '@/components/fsma/phase-gates';
import type { RecallDrill } from '@/types/fsma';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Request status as a compliance state, not a colour pair. The labels are
 * unchanged; a StatusBadge carries them with a glyph so the state survives
 * greyscale and forced-colours mode (SPEC §1.6/§4).
 */
const STATUS_DISPLAY: Record<RequestStatus, { label: string; state: ComplianceState }> = {
  open: { label: 'Open', state: 'pending' },
  in_progress: { label: 'In Progress', state: 'in-progress' },
  completed: { label: 'Completed', state: 'compliant' },
  overdue: { label: 'Overdue', state: 'non-compliant' },
};

/** Map an SLA request to the RecallDrill shape the RecallTimer component expects. */
function toRecallDrill(req: FDARequestData): RecallDrill {
  const initiated = new Date(req.requested_at).getTime();
  const now = Date.now();
  const elapsed = Math.floor((now - initiated) / 1000);
  const remaining = Math.max(0, (req.time_remaining_seconds ?? 0));

  let status: RecallDrill['status'] = 'IN_PROGRESS';
  if (req.status === 'completed') status = 'COMPLETED';
  else if (req.status === 'overdue') status = 'BREACHED';
  else if (remaining <= 3600) status = 'AT_RISK';
  else if (req.status === 'open') status = 'PENDING';

  return {
    id: req.id,
    type: 'FORWARD',
    status,
    target_tlc: req.notes?.split(':')[0] || 'All Records',
    initiated_at: req.requested_at,
    deadline: req.deadline_at,
    elapsed_seconds: elapsed,
    remaining_seconds: remaining,
    facilities_contacted: 0,
    total_facilities: 0,
    lots_traced: 0,
    total_quantity_affected: 0,
    created_by: 'system',
    notes: req.notes ?? undefined,
  };
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function RecallResponsePage() {
  const { tenantId } = useTenant();
  const { data: requests, isLoading: requestsLoading } = useSLARequests();
  const { data: dashboard } = useSLADashboard();
  const { data: alerts } = useSLAAlerts();
  const createRequest = useCreateSLARequest();

  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [renderedAt] = useState(() => Date.now());

  // Find the active (non-completed) request, or the selected one
  const activeRequests = (requests ?? []).filter(r => r.status !== 'completed');
  const completedRequests = (requests ?? []).filter(r => r.status === 'completed');
  const focusedRequest = selectedRequestId
    ? (requests ?? []).find(r => r.id === selectedRequestId) ?? activeRequests[0]
    : activeRequests[0];

  const handleCreateRequest = useCallback(() => {
    if (!tenantId) return;
    createRequest.mutate({ tenant_id: tenantId, request_type: 'records_request' });
  }, [tenantId, createRequest]);

  return (
    <PageContainer>
      {/* The dashboard shell owns the breadcrumb and the service-health badge;
          this page only renders its own header. */}
      <PageHeader
        title="FDA Recall Response"
        description="24-hour response-objective tracking for FDA records requests"
        primaryAction={
          <Button
            onClick={handleCreateRequest}
            disabled={createRequest.isPending}
            loading={createRequest.isPending}
            leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
          >
            {createRequest.isPending ? 'Creating...' : 'New Records Request'}
          </Button>
        }
      />

      <div className="space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
          <StatTile label="Active Requests" value={dashboard?.open_requests ?? 0} />
          <StatTile label="Overdue" value={dashboard?.overdue_requests ?? 0} />
          <StatTile
            label="Avg Response"
            value={
              dashboard?.avg_response_hours != null
                ? `${dashboard.avg_response_hours.toFixed(1)}h`
                : '--'
            }
          />
          <Card padding="compact">
            <div className="flex h-full items-center justify-center">
              <SLAGauge percentage={dashboard?.compliance_rate_pct ?? 100} />
            </div>
          </Card>
        </div>

        {/* Main Content: Timer + Phase Gates */}
        {requestsLoading ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3" aria-busy="true">
            <Skeleton className="h-[280px] w-full lg:col-span-1" />
            <Skeleton className="h-[280px] w-full lg:col-span-2" />
          </div>
        ) : focusedRequest ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Timer Column */}
            <div className="lg:col-span-1">
              <RecallTimer
                drill={toRecallDrill(focusedRequest)}
                onComplete={() => {
                  // Will be handled by the export + complete flow below
                }}
              />
            </div>

            {/* Details Column */}
            <div className="space-y-6 lg:col-span-2">
              {/* Phase Gates */}
              <Card>
                <CardHeader>
                  <div className="min-w-0">
                    <CardTitle>Response Timeline</CardTitle>
                    <CardDescription>
                      FDA FSMA 204 requires records within 24 hours of request
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  <PhaseGates
                    elapsedSeconds={
                      Math.floor((renderedAt - new Date(focusedRequest.requested_at).getTime()) / 1000)
                    }
                    isComplete={focusedRequest.status === 'completed'}
                  />
                </CardContent>
              </Card>

              {/* Actions */}
              <Card>
                <CardHeader>
                  <div className="min-w-0">
                    <CardTitle>Quick Actions</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Button variant="outline" asChild>
                    <Link href="/ingest">
                      <FileText className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Import Missing Records
                    </Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link href="/dashboard/compliance">
                      <Shield className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Check FSMA Readiness Score
                    </Link>
                  </Button>
                  <ExportAndCompleteButton request={focusedRequest} />
                  <Button variant="outline" asChild>
                    <Link href="/dashboard/recall-drills">
                      <Clock className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Run Recall Drill
                    </Link>
                  </Button>
                </CardContent>
              </Card>

              {/* Alerts */}
              {alerts && alerts.length > 0 && (
                <Card>
                  <CardHeader>
                    <div className="min-w-0">
                      <CardTitle>Active Alerts</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {alerts.map((alert) => (
                      <Callout
                        key={alert.id}
                        tone={alert.alert_type === 'overdue' ? 'danger' : 'warning'}
                        icon={alert.alert_type === 'overdue' ? XCircle : AlertTriangle}
                        title={alert.message}
                      >
                        <p className="font-mono text-small text-re-text-tertiary">
                          {new Date(alert.created_at).toLocaleString()}
                        </p>
                      </Callout>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        ) : (
          /* Empty State */
          <EmptyState
            icon={Shield}
            title="No Active Records Requests"
            description="When FDA requests your traceability records, start a new request here to track your 24-hour response deadline."
            action={
              <Button
                onClick={handleCreateRequest}
                disabled={createRequest.isPending}
                loading={createRequest.isPending}
                leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
              >
                Start New Request
              </Button>
            }
          />
        )}

        {/* Request History */}
        {activeRequests.length > 1 && (
          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>Active Requests</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y divide-re-border-subtle">
                {activeRequests.map((req) => (
                  <RequestRow
                    key={req.id}
                    request={req}
                    isSelected={req.id === focusedRequest?.id}
                    onSelect={() => setSelectedRequestId(req.id)}
                  />
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {completedRequests.length > 0 && (
          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>Completed Requests</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y divide-re-border-subtle">
                {completedRequests.slice(0, 10).map((req) => (
                  <RequestRow
                    key={req.id}
                    request={req}
                    isSelected={false}
                    onSelect={() => setSelectedRequestId(req.id)}
                  />
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RequestRow({
  request,
  isSelected,
  onSelect,
}: {
  request: FDARequestData;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const display = STATUS_DISPLAY[request.status];
  const isUrgent = request.time_remaining_seconds != null && request.time_remaining_seconds <= 3600;

  return (
    <li>
      <button
        onClick={onSelect}
        aria-pressed={isSelected}
        className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-120 motion-reduce:transition-none sm:px-5 ${
          isSelected ? 'bg-re-brand-muted' : 'hover:bg-re-surface-inset'
        }`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <StatusBadge state={display.state} label={display.label} size="sm" className="shrink-0" />
          <div className="min-w-0">
            <p className="truncate text-ui font-medium text-re-text-primary">
              {request.request_type === 'records_request' ? 'FDA Records Request' : request.request_type}
            </p>
            <p className="font-mono text-small text-re-text-tertiary">
              {new Date(request.requested_at).toLocaleString()}
            </p>
          </div>
        </div>
        <div className="shrink-0 text-right">
          {request.status === 'completed' && request.response_hours != null ? (
            <p className="flex items-center gap-1 font-mono text-[0.8125rem] text-re-text-secondary">
              <CheckCircle className="h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              {request.response_hours.toFixed(1)}h
            </p>
          ) : request.time_remaining_seconds != null ? (
            <p className="flex items-center gap-1 font-mono text-[0.8125rem] text-re-text-secondary">
              {isUrgent && (
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
              )}
              {formatHoursRemaining(request.time_remaining_seconds)}
            </p>
          ) : null}
        </div>
      </button>
    </li>
  );
}

function ExportAndCompleteButton({ request }: { request: FDARequestData }) {
  const complete = useCompleteSLARequest(request.id);

  const handleExportAndComplete = useCallback(() => {
    // Open export in new tab, then mark complete
    const exportUrl = `/api/ingestion/api/v1/fsma/audit/spreadsheet?start_date=2020-01-01&end_date=2099-12-31`;
    window.open(exportUrl, '_blank');
    complete.mutate({});
  }, [complete]);

  if (request.status === 'completed') return null;

  return (
    <Button
      onClick={handleExportAndComplete}
      disabled={complete.isPending}
      loading={complete.isPending}
      leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
    >
      {complete.isPending ? 'Submitting...' : 'Export & Complete'}
    </Button>
  );
}

function formatHoursRemaining(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m remaining`;
}
