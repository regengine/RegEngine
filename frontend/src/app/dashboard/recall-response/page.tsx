'use client';

import React, { useState, useCallback } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { Spinner } from '@/components/ui/spinner';
import {
  AlertTriangle,
  Bell,
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

const STATUS_DISPLAY: Record<RequestStatus, { label: string; color: string; bg: string }> = {
  open: { label: 'Open', color: 'text-re-info', bg: 'bg-re-info-muted' },
  in_progress: { label: 'In Progress', color: 'text-re-warning', bg: 'bg-re-warning-muted' },
  completed: { label: 'Completed', color: 'text-re-success', bg: 'bg-re-success-muted' },
  overdue: { label: 'Overdue', color: 'text-re-danger', bg: 'bg-re-danger-muted' },
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
    <div className="space-y-6">
      <Breadcrumbs items={[
        { label: 'Dashboard', href: '/dashboard' },
        { label: 'Recall Response' },
      ]} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">FDA Recall Response</h1>
          <p className="text-muted-foreground">
            24-hour SLA tracking for FDA records requests
          </p>
        </div>
        <Button onClick={handleCreateRequest} disabled={createRequest.isPending}>
          <Plus className="w-4 h-4 mr-2" />
          {createRequest.isPending ? 'Creating...' : 'New Records Request'}
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Active Requests</p>
                <p className="text-3xl font-bold">{dashboard?.open_requests ?? 0}</p>
              </div>
              <Clock className="w-8 h-8 text-re-info" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Overdue</p>
                <p className="text-3xl font-bold text-re-danger">{dashboard?.overdue_requests ?? 0}</p>
              </div>
              <AlertTriangle className="w-8 h-8 text-re-danger" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Avg Response</p>
                <p className="text-3xl font-bold">
                  {dashboard?.avg_response_hours != null
                    ? `${dashboard.avg_response_hours.toFixed(1)}h`
                    : '--'}
                </p>
              </div>
              <FileText className="w-8 h-8 text-re-warning" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 flex items-center justify-center">
            <SLAGauge percentage={dashboard?.compliance_rate_pct ?? 100} />
          </CardContent>
        </Card>
      </div>

      {/* Main Content: Timer + Phase Gates */}
      {requestsLoading ? (
        <div className="flex justify-center py-12">
          <Spinner className="w-8 h-8" />
        </div>
      ) : focusedRequest ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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
          <div className="lg:col-span-2 space-y-6">
            {/* Phase Gates */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Response Timeline</CardTitle>
                <CardDescription>
                  FDA FSMA 204 requires records within 24 hours of request
                </CardDescription>
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
                <CardTitle className="text-lg">Quick Actions</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Button variant="outline" asChild>
                  <Link href="/ingest">
                    <FileText className="w-4 h-4 mr-2" />
                    Import Missing Records
                  </Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/dashboard/compliance">
                    <Shield className="w-4 h-4 mr-2" />
                    Check Compliance Score
                  </Link>
                </Button>
                <ExportAndCompleteButton request={focusedRequest} />
                <Button variant="outline" asChild>
                  <Link href="/dashboard/recall-drills">
                    <Clock className="w-4 h-4 mr-2" />
                    Run Mock Drill
                  </Link>
                </Button>
              </CardContent>
            </Card>

            {/* Alerts */}
            {alerts && alerts.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Bell className="w-5 h-5 text-re-warning" />
                    Active Alerts
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {alerts.map((alert) => (
                    <div
                      key={alert.id}
                      className={`flex items-start gap-3 p-3 rounded-lg ${
                        alert.alert_type === 'overdue' ? 'bg-re-danger-muted' : 'bg-re-warning-muted'
                      }`}
                    >
                      {alert.alert_type === 'overdue' ? (
                        <XCircle className="w-5 h-5 text-re-danger shrink-0 mt-0.5" />
                      ) : (
                        <AlertTriangle className="w-5 h-5 text-re-warning shrink-0 mt-0.5" />
                      )}
                      <div>
                        <p className="text-sm font-medium">{alert.message}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {new Date(alert.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      ) : (
        /* Empty State */
        <Card>
          <CardContent className="py-16">
            <div className="text-center">
              <Shield className="w-16 h-16 mx-auto mb-4 text-muted-foreground" />
              <h3 className="text-lg font-semibold mb-2">No Active Records Requests</h3>
              <p className="text-muted-foreground mb-6 max-w-md mx-auto">
                When FDA requests your traceability records, start a new request here
                to track your 24-hour response deadline.
              </p>
              <Button onClick={handleCreateRequest} disabled={createRequest.isPending}>
                <Plus className="w-4 h-4 mr-2" />
                Start New Request
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Request History */}
      {activeRequests.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Active Requests</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {activeRequests.map((req) => (
                <RequestRow
                  key={req.id}
                  request={req}
                  isSelected={req.id === focusedRequest?.id}
                  onSelect={() => setSelectedRequestId(req.id)}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {completedRequests.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Completed Requests</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {completedRequests.slice(0, 10).map((req) => (
                <RequestRow
                  key={req.id}
                  request={req}
                  isSelected={false}
                  onSelect={() => setSelectedRequestId(req.id)}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
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
  return (
    <button
      onClick={onSelect}
      className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors text-left ${
        isSelected ? 'border-[var(--re-brand)] bg-[var(--re-brand)]/5' : 'border-transparent hover:bg-muted/50'
      }`}
    >
      <div className="flex items-center gap-3">
        <Badge className={`${display.bg} ${display.color}`}>{display.label}</Badge>
        <div>
          <p className="text-sm font-medium">
            {request.request_type === 'records_request' ? 'FDA Records Request' : request.request_type}
          </p>
          <p className="text-xs text-muted-foreground">
            {new Date(request.requested_at).toLocaleString()}
          </p>
        </div>
      </div>
      <div className="text-right">
        {request.status === 'completed' && request.response_hours != null ? (
          <p className="text-sm font-mono">
            <CheckCircle className="w-3 h-3 inline mr-1 text-re-success" />
            {request.response_hours.toFixed(1)}h
          </p>
        ) : request.time_remaining_seconds != null ? (
          <p className={`text-sm font-mono ${
            request.time_remaining_seconds <= 3600 ? 'text-re-danger' : 'text-muted-foreground'
          }`}>
            {formatHoursRemaining(request.time_remaining_seconds)}
          </p>
        ) : null}
      </div>
    </button>
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
      className="bg-re-success hover:bg-re-success text-white"
    >
      <Download className="w-4 h-4 mr-2" />
      {complete.isPending ? 'Submitting...' : 'Export & Complete'}
    </Button>
  );
}

function formatHoursRemaining(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m remaining`;
}
